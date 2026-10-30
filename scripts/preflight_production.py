"""Inspect legacy production data in one read-only transaction; never migrate."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
from unittest.mock import patch

from dotenv import dotenv_values
import psycopg2
from psycopg2 import sql

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    ('core', '0020_school_foundation'),
    ('depthead', '0002_collegeaiinsight_school_and_more'),
    ('core', '0021_attach_existing_to_adnu'),
    ('core', '0022_alter_user_managers'),
    ('core', '0023_alter_user_role_superadmininvite'),
}
REFERENCES = (
    ('core_user', 'college'), ('core_facultyinvite', 'college'),
    ('core_deptheadinvite', 'college'), ('core_officeclosure', 'college'),
    ('core_collegeannouncement', 'college'),
    ('depthead_collegeaiinsight', 'college_code'),
    ('faculty_facultyprofile', 'college_id'),
)


class Refused(Exception):
    """A safe-to-display preflight refusal, containing no credentials."""


def project_reference(host, username):
    host = (host or '').strip().lower()
    match = re.fullmatch(r'db\.([a-z0-9]+)\.supabase\.co', host)
    if match:
        return match.group(1)
    if host.endswith('.pooler.supabase.com'):
        match = re.fullmatch(r'[a-z_][a-z0-9_]*\.([a-z0-9]+)', (username or '').strip())
        if match:
            return match.group(1)
    return None


def configuration(root=ROOT):
    # Read these files explicitly; environment variables cannot redirect the target.
    primary = dotenv_values(root / '.env', interpolate=False)
    staging = dotenv_values(root / '.env.staging', interpolate=False)
    rehearsal = dotenv_values(root / '.env.rehearsal', interpolate=False)
    required = ('NAME', 'USER', 'PASSWORD', 'HOST', 'PORT')
    if any(not primary.get('DB_' + key) for key in required):
        raise Refused('The main .env must contain all five DB_* connection values.')
    reference = project_reference(primary['DB_HOST'], primary['DB_USER'])
    other_refs = [project_reference(values.get(prefix + 'HOST'), values.get(prefix + 'USER'))
                  for values, prefix in ((staging, 'STAGING_DB_'), (rehearsal, 'REHEARSAL_DB_'))]
    if not reference or any(not value for value in other_refs):
        raise Refused('Cannot identify production, staging and rehearsal projects from the local files.')
    if reference in other_refs:
        raise Refused('The main .env points to staging or rehearsal; production preflight refused.')
    if primary['DB_NAME'].strip() != 'postgres' or primary['DB_PORT'].strip() != '5432':
        raise Refused('Use database postgres and the direct/session connection on port 5432.')
    return reference, {
        'dbname': primary['DB_NAME'].strip(), 'user': primary['DB_USER'].strip(),
        'password': primary['DB_PASSWORD'], 'host': primary['DB_HOST'].strip(),
        'port': 5432, 'sslmode': 'require', 'connect_timeout': 8,
        'application_name': 'facsync_production_preflight_readonly',
    }


def migration_graph():
    # Django supplies the migration graph only. Its database is disposable SQLite;
    # production access below uses a separate, explicitly read-only connection.
    sys.path.insert(0, str(ROOT))
    import decouple
    import django
    dummy = {key: 'unused' for key in ('DB_NAME', 'DB_USER', 'DB_PASSWORD', 'DB_HOST')}
    dummy.update(DB_PORT='5432', DJANGO_SETTINGS_MODULE='config.settings.test')
    with patch.dict(os.environ, dummy), patch('dotenv.load_dotenv', return_value=False), patch(
        'decouple.config', decouple.Config(decouple.RepositoryEmpty())
    ):
        django.setup()
    from django.conf import settings
    if settings.DATABASES['default']['ENGINE'] != 'django.db.backends.sqlite3':
        raise Refused('Local migration-graph inspection must use SQLite.')
    from django.db.migrations.loader import MigrationLoader
    return MigrationLoader(None).graph


def pending_migrations(graph, applied):
    for key in applied & set(graph.nodes):
        if any(parent.key not in applied for parent in graph.node_map[key].parents):
            raise Refused('Production migration history has an unapplied dependency; review it first.')
    ordered = []
    for leaf in sorted(graph.leaf_nodes()):
        for key in graph.forwards_plan(leaf):
            if key not in applied and key not in ordered:
                ordered.append(key)
    if set(ordered) != EXPECTED:
        raise Refused('Pending migrations differ from the five rehearsed migrations. No changes made.')
    return ['.'.join(key) for key in ordered]


def inspect_database(cursor, graph, email):
    cursor.execute('SHOW transaction_read_only')
    if cursor.fetchone()[0] != 'on':
        raise Refused('The server did not enforce a read-only transaction.')
    cursor.execute("SET LOCAL statement_timeout = '15s'")
    cursor.execute("SET LOCAL lock_timeout = '3s'")
    cursor.execute('SELECT current_database()')
    if cursor.fetchone()[0] != 'postgres':
        raise Refused('Unexpected connected database.')
    cursor.execute("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public'")
    tables = {row[0] for row in cursor.fetchall()}
    required = {'django_migrations', 'core_college', 'core_user', *(table for table, _ in REFERENCES)}
    if not required.issubset(tables):
        raise Refused('Required legacy FacSync public tables are missing.')
    if 'core_school' in tables:
        raise Refused('School tables already exist; this preflight only supports the unmigrated database.')
    cursor.execute('SELECT app, name FROM public.django_migrations')
    pending = pending_migrations(graph, set(cursor.fetchall()))
    report = {'mode': 'read-only', 'pending_migrations': pending, 'issues': []}
    issues = report['issues']
    report['record_counts'] = {}
    for table in sorted(tables):
        if table.startswith(('core_', 'faculty_', 'students_', 'depthead_')):
            cursor.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier('public', table)))
            report['record_counts'][table] = cursor.fetchone()[0]
    cursor.execute('SELECT code, name FROM public.core_college')
    colleges = cursor.fetchall()
    codes = [(code or '').strip().casefold() for code, _ in colleges]
    names = [(name or '').strip().casefold() for _, name in colleges]
    if not codes or any(not value for value in codes) or len(set(codes)) != len(codes) or len(set(names)) != len(names):
        issues.append('Blank/duplicate college codes, duplicate names, or no colleges.')
    known = set(codes)
    report['unresolved_college_references'] = {}
    for table, field in REFERENCES:
        cursor.execute(sql.SQL('SELECT {} FROM {}').format(sql.Identifier(field), sql.Identifier('public', table)))
        bad = sum(1 for (value,) in cursor.fetchall() if value and value.strip().casefold() not in known)
        report['unresolved_college_references'][table] = bad
        if bad:
            issues.append(f'{table}: {bad} unresolved college references; no repair performed.')
    cursor.execute("SELECT count(*) FROM public.depthead_collegeaiinsight WHERE lower(trim(college_code))='ccs2'")
    report['ccs2_insight_rows'] = cursor.fetchone()[0]
    cursor.execute('SELECT u.college, f.college_id FROM public.faculty_facultyprofile f JOIN public.core_user u ON u.id=f.user_id')
    disagreements = sum(1 for user_code, profile_code in cursor.fetchall()
                        if (user_code or '').strip() and user_code.strip().casefold() != (profile_code or '').strip().casefold())
    report['faculty_college_disagreements'] = disagreements
    if disagreements:
        issues.append(f'{disagreements} faculty/user college disagreements.')
    cursor.execute('SELECT role, count(*) FROM public.core_user GROUP BY role')
    report['roles'] = dict(cursor.fetchall())
    cursor.execute('SELECT id, role, is_active, account_status FROM public.core_user WHERE lower(email)=%s', (email.strip().lower(),))
    candidates = cursor.fetchall()
    report['conversion_candidate_matches'] = len(candidates)
    if len(candidates) != 1:
        issues.append('The intended System Admin email must match exactly one existing account.')
    else:
        user_id, role, is_active, status = candidates[0]
        valid = role == 'superadmin' and is_active and status == 'active'
        report['conversion_candidate_is_active_superadmin'] = bool(valid)
        if not valid:
            issues.append('The conversion candidate is not an active Super Admin.')
        cursor.execute("SELECT count(*) FROM public.core_user WHERE role='superadmin' AND is_active AND account_status='active' AND id<>%s", (user_id,))
        replacements = cursor.fetchone()[0]
        report['other_active_superadmins'] = replacements
        if not replacements:
            issues.append('No other active Super Admin would remain for ADNU.')
    report['ready_for_migration_review'] = not issues
    return report


def run_check(config, graph, email, connect=psycopg2.connect):
    connection = connect(**config)
    try:
        connection.set_session(readonly=True, isolation_level='REPEATABLE READ', autocommit=False)
        with connection.cursor() as cursor:
            return inspect_database(cursor, graph, email)
    finally:
        try:
            connection.rollback()
        finally:
            connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-ref', help='Exact production project reference copied from Supabase settings.')
    parser.add_argument('--system-admin-email', help='Existing Super Admin email intended for later conversion; never printed.')
    args = parser.parse_args()
    reference, config = configuration()
    if not args.project_ref:
        print('Configuration preview only. No database connection attempted.')
        print('Project reference from the main .env:', reference)
        print('Verify it against your REAL production project, then rerun with --project-ref and --system-admin-email.')
        return 0
    if args.project_ref != reference:
        raise Refused('The supplied project reference does not match the main .env. No connection attempted.')
    if not args.system_admin_email or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', args.system_admin_email):
        raise Refused('Provide the exact existing account email with --system-admin-email.')
    # No application request, mail transport, job, migration or account conversion runs.
    with patch('requests.sessions.Session.request', side_effect=Refused('External HTTP is disabled.')), patch(
        'httpx.Client.send', side_effect=Refused('External HTTP is disabled.')
    ), patch('httpx.AsyncClient.send', side_effect=Refused('External HTTP is disabled.')):
        report = run_check(config, migration_graph(), args.system_admin_email)
    print(json.dumps(report, indent=2))
    print('Read-only transaction rolled back. No records changed, migrations applied, emails sent or accounts converted.')
    return 0 if report['ready_for_migration_review'] else 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Refused as error:
        print('Preflight stopped:', error, file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        # Database/driver errors may contain connection information. Never print them.
        print(f'Preflight stopped ({type(error).__name__}). Check local configuration, connectivity and permissions. No migrations or repairs were attempted.', file=sys.stderr)
        sys.exit(1)
