"""Frozen, explicit ADNU mapping. Legacy columns and record IDs are retained."""
import hashlib
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import migrations


# These are approved initial migration labels, not a university-wide directory.
ADNU_DEPARTMENTS = (
    ('CBA', 'DA', 'Department of Accountancy'),
    ('CCS', 'DCS', 'Department of Computer Science'),
    ('CED', 'DEE', 'Department of Elementary Education'),
    ('CHSS', 'DMS', 'Department of Media Studies'),
    ('CON', 'DN', 'Department of Nursing'),
    ('CSEA', 'DCE', 'Department of Civil Engineering'),
    ('COL', 'DL', 'Department of Law'),
)


def rows(apps, alias, app, name):
    # Historical base managers avoid current request scopes and model hooks.
    return apps.get_model(app, name)._base_manager.using(alias)


def fingerprint(item, omit_department=False):
    values = {field.attname: getattr(item, field.attname) for field in item._meta.concrete_fields
              if not (omit_department and field.name == 'department')}
    return hashlib.sha256(json.dumps(values, cls=DjangoJSONEncoder, sort_keys=True).encode()).hexdigest()


def unchanged_manifests(apps, alias, omit_department):
    result = []
    for batch in rows(apps, alias, 'core', 'DemoDataBatch').all():
        owned = []
        for label, snapshots in batch.manifest.items():
            try:
                model = apps.get_model(label)
            except LookupError:
                continue
            for item in model._base_manager.using(alias).filter(pk__in=snapshots):
                if fingerprint(item, omit_department) == snapshots[str(item.pk)]:
                    owned.append((label, item.pk))
        result.append((batch, owned))
    return result


def refresh_manifests(apps, alias, batches, omit_department):
    # Never re-sign a record edited after seeding: that would make undo unsafe.
    for batch, owned in batches:
        for label, pk in owned:
            item = apps.get_model(label)._base_manager.using(alias).get(pk=pk)
            batch.manifest[label][str(pk)] = fingerprint(item, omit_department)
        batch.save(using=alias, update_fields=['manifest'])


def plan(apps, alias):
    """Resolve every reference before making a single data change."""
    schools = {item.pk: item for item in rows(apps, alias, 'core', 'School').all()}
    mapping = {code: (department_code, name) for code, department_code, name in ADNU_DEPARTMENTS}
    colleges, offices = {}, {}
    for name, lookup in (('College', colleges), ('Office', offices)):
        for unit in rows(apps, alias, 'core', name).all():
            key = (unit.school_id, unit.code.strip().upper())
            if unit.school_id not in schools or not key[1] or key in lookup:
                raise RuntimeError(f'Department backfill refused: unresolved/duplicate {name} school or code (id={unit.pk}).')
            lookup[key] = unit

    def resolve(school_id, code, source, kind=None):
        key = (school_id, str(code or '').strip().upper())
        if school_id not in schools or not key[1]:
            raise RuntimeError(f'Department backfill refused: missing school or unit in {source}.')
        college, office = colleges.get(key), offices.get(key)
        if kind == 'office':
            college = None
        elif kind == 'college':
            office = None
        if college and office:
            raise RuntimeError(f'Department backfill refused: ambiguous college/office code in {source}.')
        if office:
            return None
        if not college:
            raise RuntimeError(f'Department backfill refused: unknown unit in {source}. No code was guessed.')
        if schools[school_id].code.upper() != 'ADNU' or key[1] not in mapping:
            raise RuntimeError(f'Department backfill refused: an explicit school/college mapping is required for {source}.')
        return key

    users = {item.pk: item for item in rows(apps, alias, 'core', 'User').all()}
    profiles = {}
    profiles_by_user = {}
    profile_owners = {}
    for profile in rows(apps, alias, 'faculty', 'FacultyProfile').all():
        user = users[profile.user_id]
        kind = 'office' if user.role == 'officeadmin' else None
        key = resolve(user.school_id, profile.college_id, f'FacultyProfile {profile.pk}', kind)
        if user.college and user.college.strip().upper() != profile.college_id.strip().upper():
            raise RuntimeError(f'Department backfill refused: User/FacultyProfile unit disagreement (user={user.pk}).')
        profiles[profile.pk] = key
        profiles_by_user[user.pk] = key
        profile_owners[profile.pk] = user

    updates = []
    heads = []
    invite_heads = []
    for user in users.values():
        if user.role in {'systemadmin', 'superadmin'}:
            continue
        if user.role == 'officeadmin':
            resolve(user.school_id, user.college, f'Office Admin {user.pk}', 'office')
            continue
        code = user.college
        if code:
            key = resolve(user.school_id, code, f'User {user.pk}', 'college' if user.role == 'depthead' else None)
        elif user.role == 'faculty' and user.pk in profiles_by_user:
            key = profiles_by_user[user.pk]
        elif user.role == 'student' and not user.profile_completed:
            continue
        else:
            raise RuntimeError(f'Department backfill refused: an assignment is required for User {user.pk}.')
        if user.role == 'depthead':
            if key is None:
                raise RuntimeError('Department backfill refused: an academic head has no academic department.')
            heads.append((user.pk, key))
        else:
            updates.append(('core', 'User', user.pk, key))

    for model, field, kind in (
        ('FacultyInvite', 'college', None), ('DeptHeadInvite', 'college', 'college'),
        ('OfficeAdminInvite', 'office', 'office'), ('OfficeClosure', 'college', None),
        ('CollegeAnnouncement', 'college', None),
    ):
        for item in rows(apps, alias, 'core', model).all():
            key = resolve(item.school_id, getattr(item, field), f'{model} {item.pk}', kind)
            if model == 'DeptHeadInvite':
                invite_heads.append((item.pk, key))
            elif model != 'OfficeAdminInvite':
                updates.append(('core', model, item.pk, key))

    for model in ('ConsultationRequest', 'WalkInQueue'):
        for item in rows(apps, alias, 'faculty', model).all():
            student = users[item.user_id]
            if student.school_id != profile_owners[item.faculty_id].school_id:
                raise RuntimeError(f'Department backfill refused: cross-school participants in {model} {item.pk}.')
            updates.append(('faculty', model, item.pk, profiles[item.faculty_id]))

    # Preserve old AI records, including their hashes/content, but reject orphan codes.
    for item in rows(apps, alias, 'depthead', 'CollegeAIInsight').all():
        resolve(item.school_id, item.college_code, f'CollegeAIInsight {item.pk}')

    departments = {key: college for key, college in colleges.items()
                   if schools[key[0]].code.upper() == 'ADNU' and key[1] in mapping}
    return departments, mapping, updates, heads, invite_heads


def forwards(apps, schema_editor):
    alias = schema_editor.connection.alias
    departments, mapping, updates, heads, invite_heads = plan(apps, alias)
    if (rows(apps, alias, 'core', 'Department').exists()
            or rows(apps, alias, 'core', 'DepartmentHeadAssignment').exists()
            or rows(apps, alias, 'core', 'DepartmentInviteAssignment').exists()):
        raise RuntimeError('Department backfill refused: department data already exists; review it before adoption.')
    manifests = unchanged_manifests(apps, alias, omit_department=True)
    ids = {}
    for key, college in departments.items():
        code, name = mapping[key[1]]
        item = rows(apps, alias, 'core', 'Department').create(
            school_id=key[0], college_id=college.pk, code=code, name=name,
            description=college.description, schedule_template=college.schedule_template,
        )
        ids[key] = item.pk
    for app, model, pk, key in updates:
        rows(apps, alias, app, model).filter(pk=pk).update(department_id=ids[key] if key else None)
    for model, field, assignments in (
        ('DepartmentHeadAssignment', 'user_id', heads),
        ('DepartmentInviteAssignment', 'invite_id', invite_heads),
    ):
        for pk, key in assignments:
            rows(apps, alias, 'core', model).create(**{field: pk, 'department_id': ids[key]})
    refresh_manifests(apps, alias, manifests, omit_department=False)


def backwards(apps, schema_editor):
    """Only reverse a mapping still representable by the preserved old fields."""
    alias = schema_editor.connection.alias
    departments, mapping, updates, heads, invite_heads = plan(apps, alias)
    ids = {}
    existing = list(rows(apps, alias, 'core', 'Department').all())
    for key, college in departments.items():
        code, name = mapping[key[1]]
        matches = [item for item in existing if item.school_id == key[0] and item.code == code
                   and item.college_id == college.pk and item.name == name and item.is_active
                   and item.description == college.description and item.schedule_template == college.schedule_template]
        if len(matches) != 1:
            raise RuntimeError('Department rollback refused: department definitions changed. Use a reviewed repair or backup.')
        ids[key] = matches[0].pk
    if len(existing) != len(ids):
        raise RuntimeError('Department rollback refused: additional departments exist.')
    for app, model, pk, key in updates:
        if rows(apps, alias, app, model).get(pk=pk).department_id != (ids[key] if key else None):
            raise RuntimeError('Department rollback refused: department memberships/history changed.')
    mapped_users = {pk for app, model, pk, _ in updates if app == 'core' and model == 'User'}
    if rows(apps, alias, 'core', 'User').exclude(pk__in=mapped_users).filter(department__isnull=False).exists():
        raise RuntimeError('Department rollback refused: new memberships have no legacy college representation.')
    for model, field, assignments in (
        ('DepartmentHeadAssignment', 'user_id', heads),
        ('DepartmentInviteAssignment', 'invite_id', invite_heads),
    ):
        actual = set(rows(apps, alias, 'core', model).values_list(field, 'department_id'))
        if actual != {(pk, ids[key]) for pk, key in assignments}:
            raise RuntimeError('Department rollback refused: head assignments changed.')
    # No writes occur until every rollback check above has passed.
    manifests = unchanged_manifests(apps, alias, omit_department=False)
    for model in ('DepartmentHeadAssignment', 'DepartmentInviteAssignment'):
        rows(apps, alias, 'core', model).all().delete()
    for app, model in (('core', 'User'), ('core', 'FacultyInvite'), ('core', 'OfficeClosure'),
                       ('core', 'CollegeAnnouncement'), ('faculty', 'ConsultationRequest'), ('faculty', 'WalkInQueue')):
        rows(apps, alias, app, model).all().update(department_id=None)
    rows(apps, alias, 'core', 'Department').all().delete()
    refresh_manifests(apps, alias, manifests, omit_department=True)


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0026_department_foundation'),
        ('faculty', '0034_department_foundation'),
        ('depthead', '0002_collegeaiinsight_school_and_more'),
    ]
    operations = [migrations.RunPython(forwards, backwards)]
