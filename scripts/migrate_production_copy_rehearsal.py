"""Rehearsal-only migration/rollback test, then verified application of the plan.

The fixed rehearsal settings reject production and staging. Writes are enabled
only inside explicitly approved transactions; normal rehearsal sessions remain
read-only. No record contents or credentials are exported.
"""
import argparse
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

from django.core.management import call_command
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor

from preflight_rehearsal import main as preflight

EXPECTED = [
    ('core', '0020_school_foundation'),
    ('depthead', '0002_collegeaiinsight_school_and_more'),
    ('core', '0021_attach_existing_to_adnu'),
    ('core', '0022_alter_user_managers'),
    ('core', '0023_alter_user_role_superadmininvite'),
]
OWNED = ('core_college', 'core_user', 'core_facultyinvite', 'core_deptheadinvite',
         'core_officeclosure', 'core_collegeannouncement', 'depthead_collegeaiinsight')
NEW_TABLES = {'core_school', 'core_schooldomain', 'core_schoolchangelog', 'core_superadmininvite'}
METADATA = {'django_content_type', 'auth_permission', 'django_migrations'}
NEW_MODELS = {'school', 'schooldomain', 'schoolchangelog', 'superadmininvite'}


def query(sql, params=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall() if cursor.description else []


def table_names():
    return set(connection.introspection.table_names())


def column_names(table):
    return [row[0] for row in query('SELECT column_name FROM information_schema.columns '
        'WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position', ['public', table])]


def digest(table, columns, ids=None):
    quote = connection.ops.quote_name
    selected = ', '.join(map(quote, columns))
    source = f'SELECT {selected} FROM public.{quote(table)}'
    params = []
    if ids is not None:
        source += ' WHERE id = ANY(%s)'
        params.append(ids)
    return query('SELECT count(*), md5(COALESCE(jsonb_agg(to_jsonb(t) '
        'ORDER BY to_jsonb(t)::text)::text, \'[]\')) FROM (' + source + ') t', params)[0]


def baseline():
    result = {}
    for table in sorted(table_names()):
        columns = column_names(table)
        result[table] = {'columns': columns, 'digest': digest(table, columns)}
        if table in METADATA:
            result[table]['ids'] = [row[0] for row in query('SELECT id FROM public.' + connection.ops.quote_name(table))]
    return result


def constraints():
    # Compare semantics, not generated constraint names or relation OIDs.
    return query("SELECT c.relname, p.contype, pg_get_constraintdef(p.oid) "
        "FROM pg_constraint p JOIN pg_class c ON c.oid=p.conrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' "
        "ORDER BY c.relname, p.contype, pg_get_constraintdef(p.oid)")


def other_relations():
    return query("SELECT n.nspname,c.relname,c.relkind,c.oid,c.relowner,c.relacl::text "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname NOT IN ('public','information_schema') AND n.nspname NOT LIKE 'pg_%%' "
        "ORDER BY n.nspname,c.relname")


def verify_original(base, *, metadata_added=False):
    for table, data in base.items():
        ids = data.get('ids') if table == 'django_migrations' or (metadata_added and table in METADATA) else None
        if digest(table, data['columns'], ids) != data['digest']:
            raise RuntimeError(f'Original records changed in {table}; transaction will roll back.')


def verify_forward(base):
    if table_names() != set(base) | NEW_TABLES:
        raise RuntimeError('Unexpected table additions/removals.')
    schools = query('SELECT id,code,name,is_active FROM public.core_school')
    if len(schools) != 1 or schools[0][1:] != ('ADNU', 'Ateneo de Naga University', True):
        raise RuntimeError('Unexpected ADNU bootstrap state.')
    school_id = schools[0][0]
    for table in OWNED:
        if query('SELECT count(*) FROM public.' + connection.ops.quote_name(table) +
                 ' WHERE school_id IS DISTINCT FROM %s', [school_id])[0][0]:
            raise RuntimeError(f'Unassigned/misassigned records in {table}.')
    for table in ('core_schooldomain', 'core_schoolchangelog', 'core_superadmininvite'):
        if query('SELECT count(*) FROM public.' + table)[0][0]:
            raise RuntimeError('Migration unexpectedly assigned domains, logged edits or created invitations.')
    return {'school': 'ADNU', 'school_count': len(schools),
        'users': query('SELECT count(*) FROM public.core_user')[0][0],
        'colleges': query('SELECT count(*) FROM public.core_college')[0][0],
        'consultations': query('SELECT count(*) FROM public.faculty_consultationrequest')[0][0],
        'roles': dict(query('SELECT role,count(*) FROM public.core_user GROUP BY role')),
        'active_superadmins': query("SELECT count(*) FROM public.core_user WHERE role='superadmin' AND is_active AND account_status='active'")[0][0],
        'assigned_domains': 0, 'systemadmins_created': 0}


def verify_metadata(base, old_nodes):
    new_types = query('SELECT id,app_label,model FROM public.django_content_type WHERE NOT (id=ANY(%s))',
                      [base['django_content_type']['ids']])
    if {(app, model) for pk, app, model in new_types} != {('core', model) for model in NEW_MODELS}:
        raise RuntimeError('Unexpected content type changes.')
    new_permissions = query('SELECT content_type_id,codename FROM public.auth_permission WHERE NOT (id=ANY(%s))',
                            [base['auth_permission']['ids']])
    expected = {(pk, action + '_' + model) for pk, app, model in new_types for action in ('add','change','delete','view')}
    if set(new_permissions) != expected:
        raise RuntimeError('Unexpected permission changes.')
    applied = set(query('SELECT app,name FROM public.django_migrations'))
    if applied != old_nodes | set(EXPECTED):
        raise RuntimeError('Unexpected migration history changes.')


def progress(action, *args):
    if action in ('apply_success', 'unapply_success'):
        # Flush deferred FK triggers before a following migration changes tables.
        query('SET CONSTRAINTS ALL IMMEDIATE')


def executor():
    return MigrationExecutor(connection, progress_callback=progress)


def main(apply):
    if preflight() != 0:
        raise RuntimeError('Preflight has unresolved issues; no migrations attempted.')
    initial = executor()
    targets = initial.loader.graph.leaf_nodes()
    plan = initial.migration_plan(targets)
    if [(migration.app_label, migration.name) for migration, backwards in plan] != EXPECTED or any(backwards for migration, backwards in plan):
        raise RuntimeError('Migration plan differs from the five reviewed migrations.')
    if not apply:
        print('Preview only. No migrations ran. Add --apply only for the approved rehearsal copy.')
        return
    old_nodes = set(initial.loader.applied_migrations)
    old_targets = sorted(node for node in old_nodes if node in initial.loader.graph.node_map and not any(
        child.key in old_nodes for child in initial.loader.graph.node_map[node].children))
    base, original_constraints, unrelated = baseline(), constraints(), other_relations()
    print('PASS: recorded in-memory fingerprints for all existing rows; no data export created.', flush=True)

    with transaction.atomic():
        query('SET TRANSACTION READ WRITE')
        executor().migrate(targets)
        verify_original(base)
        verify_forward(base)
        if set(query('SELECT app,name FROM public.django_migrations')) != old_nodes | set(EXPECTED):
            raise RuntimeError('Forward migration history mismatch.')
        print('PASS: forward migration attaches existing records to ADNU and preserves all original fields.', flush=True)
        executor().migrate(old_targets)
        if table_names() != set(base) or constraints() != original_constraints:
            raise RuntimeError('Reverse migration did not restore the original table/constraint definitions.')
        verify_original(base)
        if set(query('SELECT app,name FROM public.django_migrations')) != old_nodes:
            raise RuntimeError('Reverse migration history mismatch.')
        transaction.set_rollback(True)
    if table_names() != set(base) or constraints() != original_constraints:
        raise RuntimeError('Original schema differs after rollback rehearsal.')
    verify_original(base)
    if other_relations() != unrelated:
        raise RuntimeError('Unrelated schema inventory changed.')
    print('PASS: reverse migration restores original records/history/constraints; rehearsal transaction rolled back.', flush=True)

    # Commit only after the entire forward/reverse rehearsal succeeded. This is
    # the normal migrate command, including new content types and permissions.
    with transaction.atomic():
        query('SET TRANSACTION READ WRITE')
        executor().migrate(targets)
        # The verified executor flushes deferred constraints between migrations;
        # the normal command then creates model permissions/content types.
        call_command('migrate', interactive=False, verbosity=1)
        verify_original(base, metadata_added=True)
        summary = verify_forward(base)
        verify_metadata(base, old_nodes)
        if other_relations() != unrelated:
            raise RuntimeError('Unrelated schema inventory changed; rolling back final migration.')
    if executor().migration_plan(targets):
        raise RuntimeError('Pending migrations remain after application.')
    verify_original(base, metadata_added=True)
    report = {'result': 'passed', 'target': 'production-copy rehearsal only',
        'forward_and_reverse_verified': True, 'migrations_applied': [list(node) for node in EXPECTED],
        'original_fields_preserved': True, 'other_schemas_unchanged': True, **summary}
    folder = ROOT / '.staging-backups' / 'production-copy-rehearsal'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'migration-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)
    print('PASS: rehearsal copy left migrated. Production/staging untouched; no accounts converted or domains assigned.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        with (
            patch('requests.sessions.Session.request', side_effect=RuntimeError('External HTTP disabled')),
            patch('httpx.Client.send', side_effect=RuntimeError('External HTTP disabled')),
        ):
            main(args.apply)
    finally:
        connection.close()
