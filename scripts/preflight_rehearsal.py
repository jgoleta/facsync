"""Read-only legacy-data check. Never migrates, repairs or displays user records."""
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.rehearsal'

import django
django.setup()

from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor


def main():
    report = {'mode': 'read-only', 'production_and_staging_targets_rejected': True, 'issues': []}
    issues = report['issues']
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute('SET TRANSACTION READ ONLY')
        cursor.execute('SHOW transaction_read_only')
        if cursor.fetchone()[0] != 'on':
            raise RuntimeError('The connection is not read-only. Check rehearsal settings.')
        cursor.execute('SELECT current_schema(), current_database()')
        if cursor.fetchone() != ('public', 'postgres'):
            raise RuntimeError('Unexpected rehearsal schema/database.')
        tables = set(connection.introspection.table_names(cursor))
        if not {'core_user', 'core_college', 'django_migrations'}.issubset(tables):
            raise RuntimeError('Required restored FacSync tables are missing.')
        if 'core_school' in tables:
            raise RuntimeError('School tables already exist. This preflight is for the unmigrated restored copy.')
        executor = MigrationExecutor(connection)
        executor.loader.check_consistent_history(connection)
        report['pending_migrations'] = [f'{migration.app_label}.{migration.name}' for migration, backwards
            in executor.migration_plan(executor.loader.graph.leaf_nodes()) if not backwards]
        app_tables = sorted(table for table in tables if table.startswith(
            ('core_', 'faculty_', 'students_', 'depthead_')))
        report['record_counts'] = {}
        for table in app_tables:
            cursor.execute(f'SELECT count(*) FROM {connection.ops.quote_name(table)}')
            report['record_counts'][table] = cursor.fetchone()[0]
        cursor.execute('SELECT code, name FROM public.core_college')
        colleges = cursor.fetchall()
        codes = [(code or '').strip().casefold() for code, name in colleges]
        names = [(name or '').strip().casefold() for code, name in colleges]
        if not codes or any(not code for code in codes) or len(codes) != len(set(codes)) or len(names) != len(set(names)):
            issues.append('Blank/duplicate college codes, duplicate names, or no colleges; review before migration.')
        known = set(codes)
        references = [('core_user', 'college'), ('core_facultyinvite', 'college'),
            ('core_deptheadinvite', 'college'), ('core_officeclosure', 'college'),
            ('core_collegeannouncement', 'college'), ('depthead_collegeaiinsight', 'college_code'),
            ('faculty_facultyprofile', 'college_id')]
        report['unresolved_college_references'] = {}
        for table, field in references:
            if table not in tables:
                continue  # A pending migration may create a currently absent table.
            cursor.execute(f'SELECT {connection.ops.quote_name(field)} FROM {connection.ops.quote_name(table)}')
            bad = sum(1 for (value,) in cursor.fetchall() if value and value.strip().casefold() not in known)
            report['unresolved_college_references'][table] = bad
            if bad:
                issues.append(f'{table}: {bad} unresolved college references. No values were repaired.')
        if 'faculty_facultyprofile' in tables:
            cursor.execute('SELECT u.college, f.college_id FROM public.faculty_facultyprofile f JOIN public.core_user u ON u.id=f.user_id')
            disagreements = sum(1 for user_code, profile_code in cursor.fetchall()
                if (user_code or '').strip() and user_code.strip().casefold() != (profile_code or '').strip().casefold())
            report['faculty_college_disagreements'] = disagreements
            if disagreements:
                issues.append(f'{disagreements} faculty/user college disagreements. No values were repaired.')
        cursor.execute('SELECT role, count(*) FROM public.core_user GROUP BY role')
        report['roles'] = dict(cursor.fetchall())
        cursor.execute("SELECT count(*) FROM public.core_user WHERE role='superadmin' AND is_active AND account_status='active'")
        report['active_superadmins'] = cursor.fetchone()[0]
        if not report['active_superadmins']:
            issues.append('No active Super Admin exists in the restored copy.')
        # Only counts are reported; no names, emails, tokens or credentials.
        report['ready_for_migration_review'] = not issues
    print(json.dumps(report, indent=2))
    print('No migrations ran. No database records changed. No emails or external HTTP requests were sent.')
    return 0 if not issues else 2


if __name__ == '__main__':
    try:
        with (
            patch('requests.sessions.Session.request', side_effect=RuntimeError('External HTTP disabled for rehearsal')),
            patch('httpx.Client.send', side_effect=RuntimeError('External HTTP disabled for rehearsal')),
        ):
            result = main()
    finally:
        connection.close()
    sys.exit(result)
