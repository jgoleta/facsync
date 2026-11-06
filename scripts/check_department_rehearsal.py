"""Read-only inspection of an explicitly identified disposable production copy.

Does not apply migrations, send email, or call Google/Gemini. Credentials are
read from .env.rehearsal only; database settings never fall back to .env.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def project_reference(values):
    host = values.get('DB_HOST', '').strip().lower()
    direct = re.fullmatch(r'db\.([a-z0-9]+)\.supabase\.co', host)
    if direct:
        return direct.group(1)
    user = values.get('DB_USER', '').strip().lower()
    pooled = re.fullmatch(r'postgres\.([a-z0-9]+)', user)
    if host.endswith('.pooler.supabase.com') and pooled:
        return pooled.group(1)
    return None


def validate_target(values, production, expected):
    required = ('DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD')
    if any(not values.get(key) for key in required):
        raise ValueError('Fill all five DB fields in .env.rehearsal first.')
    target = project_reference(values)
    if not target or target != expected:
        raise ValueError('Rehearsal connection does not match the supplied project reference.')
    production_ref = project_reference(production)
    if not production_ref:
        raise ValueError('Cannot identify production from .env; target safety check refused.')
    storage_ref = urlparse(production.get('SUPABASE_URL', '')).hostname
    if target == production_ref or storage_ref == f'{target}.supabase.co':
        raise ValueError('Rehearsal target matches production. No connection attempted.')
    if str(values['DB_PORT']) == '6543':
        raise ValueError('Use a direct connection or session pooler on port 5432.')


def configure_rehearsal(expected, *, read_only=True):
    """Isolate settings after rejecting production and unexpected targets."""
    import dotenv
    import decouple
    path = ROOT / '.env.rehearsal'
    if not path.is_file():
        raise ValueError('Missing .env.rehearsal. Copy .env.rehearsal.example and fill the disposable project connection.')
    # Disable interpolation, including accidental fallback to shell secrets.
    values = dotenv.dotenv_values(path, interpolate=False)
    production = dotenv.dotenv_values(ROOT / '.env', interpolate=False)
    validate_target(values, production, expected)
    # Isolate this short-lived process from ambient settings and provider keys.
    # Windows needs SystemRoot (including while importing asyncio). Preserve OS
    # runtime paths, but never inherit database or application/provider settings.
    runtime_keys = {'SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'COMSPEC',
                    'USERPROFILE', 'APPDATA', 'LOCALAPPDATA'}
    runtime = {key: value for key, value in os.environ.items()
               if key.upper() in runtime_keys}
    os.environ.clear()
    os.environ.update(runtime)
    os.environ.update({key: values[key] for key in
                       ('DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD')})
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.base'
    dotenv.load_dotenv = lambda *a, **k: False
    decouple.config = decouple.Config(decouple.RepositoryEmpty())
    sys.path.insert(0, str(ROOT))
    from django.conf import settings
    settings.DATABASES['default']['OPTIONS'] = {
        'sslmode': 'require', 'connect_timeout': 15,
        'options': ('-c default_transaction_read_only=on ' if read_only else '')
                   + '-c statement_timeout=60000 -c lock_timeout=10000',
    }
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    import django
    django.setup()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-ref', required=True)
    args = parser.parse_args()
    configure_rehearsal(args.project_ref)
    from django.db import connection, transaction
    from django.db.migrations.executor import MigrationExecutor
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION READ ONLY')
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        report = {
            'mode': 'read-only',
            'pending_migrations': [f'{migration.app_label}.{migration.name}'
                                   for migration, backwards in plan],
            'record_counts': {},
        }
        with connection.cursor() as cursor:
            tables = connection.introspection.table_names(cursor)
            for table in tables:
                if table.startswith(('core_', 'faculty_', 'depthead_', 'students_')):
                    cursor.execute(f'SELECT count(*) FROM {connection.ops.quote_name(table)}')
                    report['record_counts'][table] = cursor.fetchone()[0]
            if 'core_user' in tables:
                cursor.execute('SELECT role, count(*) FROM core_user GROUP BY role ORDER BY role')
                report['roles'] = dict(cursor.fetchall())
                cursor.execute("SELECT count(*) FROM core_user WHERE role = 'student' "
                               "AND profile_completed AND (college IS NULL OR college = '' "
                               "OR year_level IS NULL OR year_level NOT IN ('1','2','3','4','5','6'))")
                report['completed_student_profiles_needing_review'] = cursor.fetchone()[0]
        transaction.set_rollback(True)
    print(json.dumps(report, indent=2))
    print('Read-only inspection finished. No migrations, records, emails or accounts changed.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Provider connection exceptions can contain host/user details. Do not dump them.
        message = str(error) if isinstance(error, ValueError) else type(error).__name__
        print(f'Rehearsal inspection stopped: {message}', file=sys.stderr)
        sys.exit(1)
