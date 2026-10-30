"""Provision only a new isolated staging schema/login; never run migrations.

Without --apply, inspect the target and report whether provisioning is possible.
Never print credentials, connection details, or application records.
"""

import argparse
import os
from pathlib import Path
import re
import secrets
import sys

import psycopg2
from psycopg2 import sql
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SCHEMA = 'facsync_staging'
ROLE = 'facsync_staging_login'


def project_reference(host, username):
    direct = re.fullmatch(r'db\.([a-z0-9]+)\.supabase\.co', host)
    if direct:
        return direct.group(1)
    if host.endswith('.pooler.supabase.com'):
        pooled = re.fullmatch(r'[a-z_][a-z0-9_]*\.([a-z0-9]+)', username)
        if pooled:
            return pooled.group(1)
    return None


def connect(values, *, user=None, password=None, options=''):
    return psycopg2.connect(
        dbname=values['STAGING_DB_NAME'].strip(),
        user=user or values['STAGING_DB_USER'].strip(),
        password=password if password is not None else values['STAGING_DB_PASSWORD'],
        host=values['STAGING_DB_HOST'].strip().lower(),
        port=5432, sslmode='require', connect_timeout=8, options=options,
    )


def relation_inventory(cursor):
    cursor.execute("""
        SELECT n.nspname, c.relname, c.relkind, c.oid
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname <> %s AND n.nspname <> 'information_schema'
          AND n.nspname NOT LIKE 'pg_%%'
        ORDER BY n.nspname,c.relname,c.relkind
    """, (SCHEMA,))
    return cursor.fetchall()


def check_permissions(cursor):
    cursor.execute("""
        SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls
        FROM pg_roles WHERE rolname=%s
    """, (ROLE,))
    if any(cursor.fetchone()):
        raise RuntimeError('The staging role has elevated privileges.')
    cursor.execute('SELECT 1 FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=%s)', (ROLE,))
    if cursor.fetchone():
        raise RuntimeError('The staging role unexpectedly has role memberships.')
    cursor.execute("""
        SELECT nspname FROM pg_namespace
        WHERE nspname <> %s AND nspname <> 'information_schema'
          AND nspname NOT LIKE 'pg_%%' AND has_schema_privilege(%s,oid,'CREATE')
    """, (SCHEMA, ROLE))
    if cursor.fetchall():
        raise RuntimeError('PUBLIC grants allow creation outside staging; no existing grants will be changed.')
    cursor.execute("""
        SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname <> %s AND n.nspname <> 'information_schema'
          AND n.nspname NOT LIKE 'pg_%%' AND c.relkind IN ('r','p','v','m','f')
          AND has_schema_privilege(%s,n.oid,'USAGE')
          AND has_table_privilege(%s,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
    """, (SCHEMA, ROLE, ROLE))
    if cursor.fetchall():
        raise RuntimeError('PUBLIC grants expose existing tables to new roles; provisioning refused without changing existing grants.')


def save_credentials(path, original, username, password):
    replacements = {
        'STAGING_DB_USER': username,
        'STAGING_DB_PASSWORD': password,
        'STAGING_DB_SCHEMA': SCHEMA,
    }
    lines = []
    for line in original.splitlines():
        match = re.match(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=', line)
        key = match.group(1) if match else None
        if key in replacements:
            lines.append(key + '=' + replacements.pop(key))
        else:
            lines.append(line)
    lines.extend(key + '=' + value for key, value in replacements.items())
    temporary = path.with_name('.env.staging.tmp')
    try:
        temporary.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    path = ROOT / '.env.staging'
    original = path.read_text(encoding='utf-8')
    values = dotenv_values(path, interpolate=False)
    if any(not values.get('STAGING_DB_' + key) for key in ('NAME','USER','PASSWORD','HOST','PORT')):
        raise RuntimeError('Missing STAGING_DB_* values.')
    host = values['STAGING_DB_HOST'].strip().lower()
    username = values['STAGING_DB_USER'].strip()
    reference = project_reference(host, username)
    if not reference or username.split('.')[0] != 'postgres' or values['STAGING_DB_PORT'].strip() != '5432':
        raise RuntimeError('Provisioning requires Supabase admin credentials on the direct/session connection.')

    from config.settings import base
    primary = base.DATABASES['default']
    primary_reference = project_reference(str(primary['HOST']).strip().lower(), str(primary['USER']).strip())
    storage = re.fullmatch(r'https://([a-z0-9]+)\.supabase\.co', base.SUPABASE_URL)
    if reference == primary_reference or (storage and reference == storage.group(1)):
        raise RuntimeError('Refusing to provision the main configured Supabase project.')

    connection = connect(values)
    try:
        connection.set_session(readonly=not args.apply)
        with connection.cursor() as cursor:
            cursor.execute('SET LOCAL statement_timeout=8000')
            cursor.execute('SET LOCAL lock_timeout=3000')
            cursor.execute('SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=%s), EXISTS(SELECT 1 FROM pg_roles WHERE rolname=%s)', (SCHEMA, ROLE))
            if any(cursor.fetchone()):
                raise RuntimeError('The staging schema or role already exists; refusing to modify existing objects.')
            cursor.execute('SELECT rolcreaterole FROM pg_roles WHERE rolname=current_user')
            if not cursor.fetchone()[0]:
                raise RuntimeError('The provisioning account cannot create roles.')
            before = relation_inventory(cursor)
            print('Verified separate project; staging schema/login names are unused.')
            if not args.apply:
                print('Read-only preflight complete. No changes made. Use --apply only when authorized.')
                return
            password = secrets.token_urlsafe(40)
            cursor.execute(sql.SQL('CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %s').format(sql.Identifier(ROLE)), (password,))
            # Do not change grants, schemas or objects belonging to the existing app.
            cursor.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(SCHEMA)))
            cursor.execute(sql.SQL('REVOKE ALL ON SCHEMA {} FROM PUBLIC').format(sql.Identifier(SCHEMA)))
            cursor.execute(sql.SQL('GRANT USAGE, CREATE ON SCHEMA {} TO {}').format(sql.Identifier(SCHEMA), sql.Identifier(ROLE)))
            cursor.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(values['STAGING_DB_NAME'].strip()), sql.Identifier(ROLE)))
            cursor.execute(sql.SQL('ALTER ROLE {} SET search_path TO {}').format(sql.Identifier(ROLE), sql.Identifier(SCHEMA)))
            check_permissions(cursor)
            if relation_inventory(cursor) != before:
                raise RuntimeError('Existing relation inventory changed; rolling back provisioning.')
        connection.commit()
        new_username = ROLE + '.' + reference if host.endswith('.pooler.supabase.com') else ROLE
        save_credentials(path, original, new_username, password)
        print('Created isolated schema/login; .env.staging now contains the restricted credentials.')
        restricted = connect(values, user=new_username, password=password, options='-c search_path=' + SCHEMA)
        try:
            restricted.set_session(readonly=True)
            with restricted.cursor() as cursor:
                cursor.execute('SELECT current_user,current_schema(),current_schemas(false)')
                role, schema, search = cursor.fetchone()
                if (role, schema, search) != (ROLE, SCHEMA, [SCHEMA]):
                    raise RuntimeError('Restricted connection did not resolve only the staging schema.')
                cursor.execute("SELECT to_regclass('django_migrations'),to_regclass('auth_user'),to_regclass('account_emailaddress')")
                if any(cursor.fetchone()):
                    raise RuntimeError('Restricted connection resolves tables from the other application.')
                cursor.execute('SHOW transaction_read_only')
                print('Restricted login verified; schema=facsync_staging; read-only verification=' + cursor.fetchone()[0])
            restricted.rollback()
        finally:
            restricted.close()
        print('Existing relation inventory preserved. No FacSync migrations or sample data were applied.')
    finally:
        connection.close()


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except psycopg2.Error as exc:
        # Server diagnostics can echo connection details or passwords from SQL.
        print('Database operation failed (' + type(exc).__name__ + ', SQLSTATE ' + str(exc.pgcode) + '); credentials omitted.', file=sys.stderr)
        sys.exit(1)
    except OSError:
        print('Local file operation failed. Check .env.staging before retrying; no credentials printed.', file=sys.stderr)
        sys.exit(1)
