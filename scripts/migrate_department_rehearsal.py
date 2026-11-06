"""Rehearse the department migrations on a verified restored copy, never production."""
import argparse
import hashlib
import json
import sys

from check_department_rehearsal import ROOT, configure_rehearsal

ALLOWED = {
    ('core', '0026_department_foundation'),
    ('faculty', '0034_department_foundation'),
    ('core', '0027_attach_adnu_departments'),
    ('core', '0028_head_title_labels'),
    ('core', '0029_department_closure_scope'),
    ('core', '0030_educational_levels'),
    ('core', '0031_classify_existing_students'),
}


def snapshot(connection, schema=None):
    """Compare all original application fields, without storing personal data."""
    with connection.cursor() as cursor:
        if schema is None:
            schema = {}
            for table in connection.introspection.table_names(cursor):
                if table.startswith(('core_', 'faculty_', 'depthead_', 'students_')):
                    columns = [column.name for column in connection.introspection.get_table_description(cursor, table)]
                    # These ownership fingerprints intentionally track the new columns.
                    schema[table] = [c for c in columns if not (table == 'core_demodatabatch' and c == 'manifest')]
        result = {}
        quote = connection.ops.quote_name
        for table, columns in schema.items():
            selected = ', '.join(quote(c) for c in columns)
            cursor.execute(f'SELECT to_jsonb(t) FROM (SELECT {selected} FROM {quote(table)}) t')
            hashes = sorted(hashlib.sha256(json.dumps(row[0], sort_keys=True, default=str).encode()).hexdigest()
                            for row in cursor.fetchall())
            result[table] = {'count': len(hashes), 'sha256': hashlib.sha256(''.join(hashes).encode()).hexdigest()}
    return schema, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-ref', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    configure_rehearsal(args.project_ref, read_only=not args.apply)
    from django.core.management import call_command
    from django.db import connection, transaction
    from django.db.migrations.executor import MigrationExecutor
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    pending = {(m.app_label, m.name) for m, backwards in plan}
    if any(backwards for _, backwards in plan) or pending - ALLOWED:
        raise ValueError('Unexpected migration plan. Restore/review the current production copy first.')
    if not pending:
        raise ValueError('No pending restructuring migrations. Do not treat a repeat as a fresh rehearsal.')
    print('Pending restructuring migrations:', len(pending), flush=True)
    if not args.apply:
        print('Preview only. Add --apply to rehearse on this verified copy.')
        return
    report_dir = ROOT / '.staging-backups' / 'department-rehearsal'
    report_dir.mkdir(parents=True, exist_ok=True)
    # PostgreSQL supports transactional DDL: validation or preservation failure
    # rolls back the entire rehearsal, including earlier schema migrations.
    with transaction.atomic():
        schema, before = snapshot(connection)
        (report_dir / 'before.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
        call_command('migrate', interactive=False, verbosity=1)
        _, after = snapshot(connection, schema)
        changed = [table for table in before if before[table] != after[table]]
        if changed:
            raise ValueError('Original records changed unexpectedly; transaction rolled back: ' + ', '.join(changed))
        from apps.core.models import Department, DepartmentHeadAssignment, User
        from apps.faculty.models import ConsultationRequest, FacultyProfile
        from django.db.models import F
        if User.objects.filter(department__isnull=False).exclude(school_id=F('department__school_id')).exists():
            raise ValueError('User department school mismatch; transaction rolled back.')
        if DepartmentHeadAssignment.objects.exclude(user__school_id=F('department__school_id')).exists():
            raise ValueError('Head assignment school mismatch; transaction rolled back.')
        department_ids = {(school, code.upper()): pk for school, code, pk in
                          Department.objects.values_list('school_id', 'college__code', 'pk') if code}
        # Former faculty may now be Super Admins and have no current home
        # department. Historical consultations follow the preserved profile's
        # original unit, not the owner's current administrative assignment.
        for school, code, assigned in ConsultationRequest.objects.values_list(
                'faculty__user__school_id', 'faculty__college_id', 'department_id'):
            if assigned != department_ids.get((school, str(code or '').strip().upper())):
                raise ValueError('Historical consultation department mismatch; transaction rolled back.')
        students = User.objects.filter(role='student')
        if students.exclude(educational_level='college').exists():
            raise ValueError('Legacy student classification mismatch; transaction rolled back.')
        report = {
            'original_records_preserved': before == after,
            'tables_checked': len(before), 'before': before, 'after': after,
            'departments': list(Department.objects.order_by('school_id', 'code').values('school_id', 'code', 'name')),
            'head_assignments': DepartmentHeadAssignment.objects.count(),
            'college_students': students.count(),
            'faculty_profiles': FacultyProfile.objects.count(),
            'pending_migrations': len(MigrationExecutor(connection).migration_plan(executor.loader.graph.leaf_nodes())),
        }
    (report_dir / 'migration-result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key not in ('before', 'after')}, indent=2))
    print('Rehearsal migration committed on the separate copy. Production was not changed.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        message = str(error) if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__
        print(f'Rehearsal migration stopped: {message}', file=sys.stderr)
        sys.exit(1)
