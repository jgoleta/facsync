"""Restore a public-schema backup only into an empty, verified rehearsal target."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

from check_department_rehearsal import ROOT, validate_target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-ref', required=True)
    parser.add_argument('--backup', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    from dotenv import dotenv_values
    import psycopg2
    values = dotenv_values(ROOT / '.env.rehearsal', interpolate=False)
    production = dotenv_values(ROOT / '.env', interpolate=False)
    validate_target(values, production, args.project_ref)
    backup = args.backup.resolve(strict=True)
    restore = Path(r'C:\Program Files\PostgreSQL\18\bin\pg_restore.exe')
    listing = subprocess.run([str(restore), '--list', str(backup)],
                             capture_output=True, text=True, check=True).stdout
    if 'TABLE DATA public core_user ' not in listing or 'TABLE DATA public core_school ' not in listing:
        raise ValueError('Expected a current FacSync public-schema production backup.')
    with psycopg2.connect(host=values['DB_HOST'], port=values['DB_PORT'],
                          dbname=values['DB_NAME'], user=values['DB_USER'],
                          password=values['DB_PASSWORD'], sslmode='require',
                          connect_timeout=15,
                          options='-c default_transaction_read_only=on -c statement_timeout=30000') as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                           "WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','S','f')")
            if cursor.fetchone()[0]:
                raise ValueError('Destination public schema contains relations. Restore refused.')
    if not args.apply:
        print('Preview: verified separate, empty rehearsal target. Add --apply to restore.')
        return
    output = ROOT / '.staging-backups' / 'department-rehearsal'
    output.mkdir(parents=True, exist_ok=True)
    # Supabase already provides public. Keep its ownership and permissions.
    lines = [line for line in listing.splitlines()
             if ' SCHEMA - public ' not in line and ' COMMENT - SCHEMA public ' not in line]
    restore_list = output / 'restore-list.txt'
    restore_list.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith('PG')}
    env.update(PGPASSWORD=values['DB_PASSWORD'], PGSSLMODE='require', PGCONNECT_TIMEOUT='15')
    command = [str(restore), '--host', values['DB_HOST'], '--port', values['DB_PORT'],
               '--username', values['DB_USER'], '--dbname', values['DB_NAME'],
               '--no-password', '--no-owner', '--no-acl', '--exit-on-error',
               '--single-transaction', '--use-list', str(restore_list), str(backup)]
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    (output / 'restore.log').write_text(result.stderr, encoding='utf-8')
    if result.returncode:
        raise ValueError('Restore failed and its transaction rolled back. Review the private restore.log.')
    print('Production backup restored into the separate rehearsal database. Production was not changed.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        message = str(error) if isinstance(error, ValueError) else type(error).__name__
        print(f'Restore stopped: {message}', file=sys.stderr)
        sys.exit(1)
