"""Preview/rehearse a selective consultation recovery. Production writes require explicit flags.

No Django startup, signals, email delivery or Google Calendar calls are involved.
The source must be a disposable rehearsal copy of the selected backup.
"""
import argparse
from collections import Counter
from datetime import date, datetime, time
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json, RealDictCursor
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
TABLES = {'users': 'core_user', 'faculty': 'faculty_facultyprofile',
          'schools': 'core_school', 'departments': 'core_department',
          'requests': 'faculty_consultationrequest'}


def config(path):
    values = dotenv_values(path, interpolate=False)
    mapping = {'host': 'DB_HOST', 'port': 'DB_PORT', 'dbname': 'DB_NAME', 'user': 'DB_USER', 'password': 'DB_PASSWORD'}
    if not all(values.get(key) for key in mapping.values()):
        raise ValueError('Missing database connection settings')
    return {key: values[value] for key, value in mapping.items()}


def reference(settings):
    # Supabase direct host or session-pooler user. Never infer identity from password.
    host_match = re.fullmatch(r'db\.([a-z0-9]+)\.supabase\.co', settings['host'])
    if host_match:
        return host_match[1]
    user_match = re.fullmatch(r'postgres\.([a-z0-9]+)', settings['user'])
    if user_match and settings['host'].endswith('.pooler.supabase.com'):
        return user_match[1]
    raise ValueError('Cannot verify Supabase project identity')


def connect(settings, readonly=True):
    conn = psycopg2.connect(**settings, sslmode='require', connect_timeout=15,
                           options='-c statement_timeout=30000 -c lock_timeout=5000'
                           + (' -c default_transaction_read_only=on' if readonly else ''))
    conn.set_session(readonly=readonly, isolation_level='REPEATABLE READ')
    return conn


def snapshot(conn, schema='public'):
    result = {}
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        for key, table in TABLES.items():
            cursor.execute(sql.SQL('SELECT * FROM {}.{}').format(sql.Identifier(schema), sql.Identifier(table)))
            result[key] = [dict(row) for row in cursor.fetchall()]
    return result


def canonical(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return value


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=canonical).encode()).hexdigest()


def backup_rows(path, pg_restore):
    result = subprocess.run([str(pg_restore), '--data-only', '--no-owner', '--no-acl', '--file=-',
                             '--table=faculty_consultationrequest', str(path)], capture_output=True)
    if result.returncode:
        raise ValueError('Could not inspect the selected backup')
    columns, rows = None, []
    def unescape(value):
        if value == r'\N':
            return None
        escapes = {'n': '\n', 'r': '\r', 't': '\t', 'b': '\b', 'f': '\f', 'v': '\v', '\\': '\\'}
        return re.sub(r'\\([0-7]{1,3}|x[0-9a-fA-F]{1,2}|.)',
                      lambda m: chr(int(m[1], 8)) if re.fullmatch('[0-7]{1,3}', m[1]) else
                      chr(int(m[1][1:], 16)) if m[1].startswith('x') and len(m[1]) > 1 else escapes.get(m[1], m[1]), value)
    for line in result.stdout.decode('utf-8').splitlines():
        if line.startswith('COPY public.faculty_consultationrequest '):
            columns = line.split('(', 1)[1].split(')', 1)[0].split(', ')
        elif columns and line == r'\.':
            break
        elif columns:
            rows.append(dict(zip(columns, map(unescape, line.split('\t')))))
    if not columns:
        raise ValueError('No consultation COPY data found in backup')
    return rows


def verify_backup(source, rows):
    originals = {row['request_id']: row for row in rows}
    if len(originals) != len(source['requests']):
        raise ValueError('Rehearsal consultation count differs from the selected backup')
    for item in source['requests']:
        original = originals.get(item['request_id'])
        if original is None:
            raise ValueError('Rehearsal has a consultation absent from the backup')
        for field, expected in original.items():
            current = item.get(field)
            if isinstance(current, datetime):
                equal = current == datetime.fromisoformat(expected)
            elif isinstance(current, (date, time)):
                equal = current.isoformat() == expected
            elif current is None:
                equal = expected is None
            else:
                equal = str(current) == expected
            # Backup predates department backfill: only fields actually in it are compared.
            if not equal:
                raise ValueError(f'Rehearsal consultation differs from backup: {field}')


def plan(source, target):
    def index(data, kind):
        return {row['faculty_id' if kind == 'faculty' else 'request_id' if kind == 'requests' else 'id']: row for row in data[kind]}
    src = {key: index(source, key) for key in TABLES}
    dst = {key: index(target, key) for key in TABLES}
    def school_matches(pk):
        return pk in src['schools'] and pk in dst['schools'] and all(
            src['schools'][pk][key] == dst['schools'][pk][key] for key in ('code', 'name'))
    def same_user(original, existing):
        return (original['email'].strip().casefold() == existing['email'].strip().casefold()
                and original['role'] == existing['role'] and original['school_id'] == existing['school_id']
                and school_matches(original['school_id']))
    archives, restored, remaps = {}, [], {}
    for old in source['requests']:
        if old['request_id'] in dst['requests']:
            # Existing requests are never overwritten, even when later legitimately edited.
            continue
        row = old.copy()
        student = src['users'][row['user_id']]
        if student['role'] != 'student' or not school_matches(student['school_id']):
            raise ValueError('Student school/role cannot be verified')
        current_student = dst['users'].get(student['id'])
        if current_student:
            if not same_user(student, current_student):
                raise ValueError('Student ID now belongs to a different identity')
        else:
            if any(u['email'].casefold() == student['email'].casefold() or u['username'].casefold() == student['username'].casefold()
                   for u in target['users']):
                raise ValueError('Student has an existing replacement; explicit mapping is required')
            archive = student.copy()
            archive.update(password='!', is_active=False, account_status='deactivated',
                           is_staff=False, is_superuser=False, last_login=None)
            archives[archive['id']] = archive
        original_profile = src['faculty'][old['faculty_id']]
        original_owner = src['users'][original_profile['user_id']]
        candidate = dst['faculty'].get(old['faculty_id'])
        if candidate is None:
            owners = [u for u in target['users'] if same_user(original_owner, u)]
            profiles = [p for p in target['faculty'] if any(p['user_id'] == u['id'] for u in owners)]
            if len(profiles) != 1:
                raise ValueError('Cannot uniquely match the replacement faculty profile')
            candidate = profiles[0]
            remaps[old['faculty_id']] = candidate['faculty_id']
        owner = dst['users'][candidate['user_id']]
        if (not same_user(original_owner, owner) or owner['school_id'] != student['school_id']
                or candidate['college_id'] != original_profile['college_id']
                or owner['department_id'] != original_owner['department_id']):
            raise ValueError('Faculty identity, school or unit does not match')
        row['faculty_id'] = candidate['faculty_id']
        for department_id in {row['department_id'], student['department_id']} - {None}:
            original_dept = src['departments'][department_id]
            current_dept = dst['departments'].get(department_id)
            if (not current_dept or original_dept['school_id'] != student['school_id']
                    or any(original_dept[k] != current_dept[k] for k in ('code', 'name', 'school_id'))):
                raise ValueError('Historical department no longer matches')
        # Historical scope can differ from the faculty's current home. Preserve
        # the backup/backfill snapshot rather than rewriting reporting history.
        restored.append(row)
    # Reusing an old ID must never move the normal account sequence backwards.
    if archives and max(archives) >= max(dst['users'], default=0):
        raise ValueError('Archived account ID requires explicit sequence review')
    return {'archived_students': list(archives.values()), 'requests': restored, 'faculty_remaps': remaps}


def insert_rows(conn, schema, table, rows):
    if not rows:
        return
    with conn.cursor() as cursor:
        cursor.execute(sql.SQL('SELECT * FROM {}.{} LIMIT 0').format(sql.Identifier(schema), sql.Identifier(table)))
        columns = [column.name for column in cursor.description]
        for row in rows:
            if set(columns) != set(row):
                raise ValueError('Source and target columns differ')
            cursor.execute(sql.SQL('INSERT INTO {}.{} SELECT * FROM json_populate_record(NULL::{}.{}, %s)').format(
                sql.Identifier(schema), sql.Identifier(table), sql.Identifier(schema), sql.Identifier(table)),
                [Json(row, dumps=lambda x: json.dumps(x, default=canonical))])


def execute_recovery(conn, schema, recovery):
    insert_rows(conn, schema, TABLES['users'], recovery['archived_students'])
    insert_rows(conn, schema, TABLES['requests'], recovery['requests'])


def rehearse(source_config, target, recovery):
    conn = connect(source_config, readonly=False)
    try:
        with conn.cursor() as cursor:
            # Temporary tables hold a production-shaped copy. Permanent rehearsal
            # tables, credentials and sequences are never modified.
            for key in ('schools', 'departments', 'users', 'faculty', 'requests'):
                table = TABLES[key]
                cursor.execute(sql.SQL('CREATE TEMP TABLE {} (LIKE public.{} INCLUDING CONSTRAINTS) ON COMMIT DROP').format(
                    sql.Identifier(table), sql.Identifier(table)))
                pk = 'faculty_id' if key == 'faculty' else 'request_id' if key == 'requests' else 'id'
                cursor.execute(sql.SQL('ALTER TABLE pg_temp.{} ADD PRIMARY KEY ({})').format(sql.Identifier(table), sql.Identifier(pk)))
                insert_rows(conn, 'pg_temp', table, target[key])
            for table, field, parent, parent_field in (
                ('core_user', 'school_id', 'core_school', 'id'),
                ('core_user', 'department_id', 'core_department', 'id'),
                ('faculty_facultyprofile', 'user_id', 'core_user', 'id'),
                ('faculty_consultationrequest', 'user_id', 'core_user', 'id'),
                ('faculty_consultationrequest', 'faculty_id', 'faculty_facultyprofile', 'faculty_id'),
                ('faculty_consultationrequest', 'department_id', 'core_department', 'id'),
            ):
                cursor.execute(sql.SQL('ALTER TABLE pg_temp.{} ADD FOREIGN KEY ({}) REFERENCES pg_temp.{} ({})').format(
                    *map(sql.Identifier, (table, field, parent, parent_field))))
            for field in ('username', 'email'):
                cursor.execute(sql.SQL("CREATE UNIQUE INDEX ON pg_temp.core_user (lower({})) WHERE {} <> ''").format(sql.Identifier(field), sql.Identifier(field)))
        before = digest(snapshot(conn))
        execute_recovery(conn, 'pg_temp', recovery)
        mirrored = snapshot(conn, 'pg_temp')
        if len(mirrored['requests']) != len(target['requests']) + len(recovery['requests']):
            raise ValueError('Unexpected recovery count')
        for original in target['requests']:
            if original not in mirrored['requests']:
                raise ValueError('An existing consultation changed')
        if digest(snapshot(conn)) != before:
            raise ValueError('Permanent rehearsal tables changed')
        conn.rollback()
        return True
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup', type=Path, required=True)
    parser.add_argument('--pg-restore', type=Path, default=Path(r'C:\Program Files\PostgreSQL\18\bin\pg_restore.exe'))
    parser.add_argument('--rehearse', action='store_true')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--expected-project')
    parser.add_argument('--approved-plan')
    parser.add_argument('--fresh-production-backup', type=Path)
    args = parser.parse_args()
    if args.apply and args.rehearse:
        raise ValueError('Choose rehearsal or production apply, never both')
    source_config, target_config = config(ROOT / '.env.rehearsal'), config(ROOT / '.env')
    if reference(source_config) == reference(target_config):
        raise ValueError('Rehearsal and production must be separate projects')
    with connect(source_config) as conn:
        source = snapshot(conn)
    with connect(target_config) as conn:
        target = snapshot(conn)
    verify_backup(source, backup_rows(args.backup, args.pg_restore))
    recovery = plan(source, target)
    fingerprint = digest(recovery)
    report = {'backup': args.backup.name, 'backup_verified': True,
              'production_before': len(target['requests']), 'requests_to_restore': len(recovery['requests']),
              'students_to_restore_deactivated': len(recovery['archived_students']),
              'faculty_profiles_to_remap': len(recovery['faculty_remaps']),
              'statuses_to_restore': dict(Counter(r['status'] for r in recovery['requests'])),
              'requests_with_no_department': sum(r['department_id'] is None for r in recovery['requests']),
              'production_after_if_applied': len(target['requests']) + len(recovery['requests']),
              'plan_sha256': fingerprint, 'production_changed': False, 'emails_sent': 0}
    if args.rehearse:
        report['rehearsal_passed'] = rehearse(source_config, target, recovery)
    if args.apply:
        if args.expected_project != reference(target_config) or args.approved_plan != fingerprint:
            raise ValueError('Production project or approved plan does not match')
        backup = args.fresh_production_backup
        if not backup or not backup.is_file() or backup.stat().st_size == 0:
            raise ValueError('A fresh production backup is required')
        # Verify the supplied fresh backup actually contains current consultation rows.
        verify_backup(target, backup_rows(backup, args.pg_restore))
        conn = connect(target_config, readonly=False)
        try:
            with conn.cursor() as cursor:
                cursor.execute('LOCK TABLE public.core_user, public.faculty_facultyprofile, public.core_school, public.core_department, public.faculty_consultationrequest IN SHARE ROW EXCLUSIVE MODE')
            if digest(plan(source, snapshot(conn))) != fingerprint:
                raise ValueError('Production changed after preview; prepare a new plan')
            execute_recovery(conn, 'public', recovery)
            conn.commit()
            report['production_changed'] = True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Connection exceptions may include credentials or personal data.
        print('Recovery stopped:', str(error) if isinstance(error, ValueError) else type(error).__name__)
        sys.exit(1)
