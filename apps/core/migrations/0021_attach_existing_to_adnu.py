"""Attach legacy data without assigning domains, changing roles or college text."""
import hashlib
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import migrations


OWNERS = (
    ('core', 'College'), ('core', 'User'), ('core', 'FacultyInvite'),
    ('core', 'DeptHeadInvite'), ('core', 'OfficeClosure'),
    ('core', 'CollegeAnnouncement'), ('depthead', 'CollegeAIInsight'),
)


def fingerprint(obj, omit_school=False):
    values = {
        field.attname: getattr(obj, field.attname)
        for field in obj._meta.concrete_fields
        if not (omit_school and field.name == 'school')
    }
    return hashlib.sha256(json.dumps(values, cls=DjangoJSONEncoder, sort_keys=True).encode()).hexdigest()


def unchanged_manifests(apps, alias, omit_school):
    """Only re-sign genuinely unchanged owned samples, never modified records."""
    batches = apps.get_model('core', 'DemoDataBatch').objects.using(alias)
    result = []
    for batch in batches.all().iterator():
        owned = []
        for label, snapshots in batch.manifest.items():
            try:
                model = apps.get_model(label)
            except LookupError:
                continue
            for obj in model.objects.using(alias).filter(pk__in=snapshots).iterator():
                if fingerprint(obj, omit_school) == snapshots[str(obj.pk)]:
                    owned.append((label, obj.pk))
        result.append((batch, owned))
    return result


def refresh_manifests(apps, alias, batches, omit_school):
    for batch, owned in batches:
        for label, pk in owned:
            obj = apps.get_model(label).objects.using(alias).get(pk=pk)
            batch.manifest[label][str(pk)] = fingerprint(obj, omit_school)
        batch.save(using=alias, update_fields=['manifest'])


def validate_legacy(apps, alias):
    College = apps.get_model('core', 'College')
    codes, names = set(), set()
    for college in College.objects.using(alias).all().iterator():
        code = (college.code or '').strip().casefold()
        name = college.name.strip().casefold()
        if not code or code in codes or name in names:
            raise RuntimeError('ADNU backfill refused: blank or case-insensitive duplicate college code/name. Resolve legacy colleges explicitly.')
        codes.add(code)
        names.add(name)
    references = (
        ('core', 'User', 'college'), ('core', 'FacultyInvite', 'college'),
        ('core', 'DeptHeadInvite', 'college'), ('core', 'OfficeClosure', 'college'),
        ('core', 'CollegeAnnouncement', 'college'), ('depthead', 'CollegeAIInsight', 'college_code'),
        ('faculty', 'FacultyProfile', 'college_id'),
    )
    for app, label, field in references:
        for pk, value in apps.get_model(app, label).objects.using(alias).values_list('pk', field).iterator():
            if value and value.strip().casefold() not in codes:
                raise RuntimeError(f'ADNU backfill refused: unresolved college in {app}.{label} record {pk}. No code was guessed or overwritten.')
    profiles = apps.get_model('faculty', 'FacultyProfile').objects.using(alias).select_related('user')
    for profile in profiles.iterator():
        user_code = (profile.user.college or '').strip().casefold()
        if user_code and user_code != (profile.college_id or '').strip().casefold():
            raise RuntimeError(f'ADNU backfill refused: faculty/user college disagreement for profile {profile.pk}.')


def forwards(apps, schema_editor):
    alias = schema_editor.connection.alias
    School = apps.get_model('core', 'School')
    if School.objects.using(alias).exists():
        raise RuntimeError('ADNU backfill refused: schools already exist; inspect before adopting legacy records.')
    validate_legacy(apps, alias)
    samples = unchanged_manifests(apps, alias, omit_school=True)
    adnu = School.objects.using(alias).create(name='Ateneo de Naga University', code='ADNU', is_active=True)
    for app, label in OWNERS:
        rows = apps.get_model(app, label).objects.using(alias).all()
        if label == 'User':
            rows = rows.exclude(role='systemadmin')
        rows.update(school_id=adnu.pk)
    refresh_manifests(apps, alias, samples, omit_school=False)
    # Domain assignment is exclusively a future System Admin action.


def backwards(apps, schema_editor):
    alias = schema_editor.connection.alias
    School = apps.get_model('core', 'School')
    schools = School.objects.using(alias)
    if (schools.count() != 1 or not schools.filter(code='ADNU').exists()
            or apps.get_model('core', 'SchoolDomain').objects.using(alias).exists()
            or apps.get_model('core', 'SchoolChangeLog').objects.using(alias).exists()
            or apps.get_model('core', 'User').objects.using(alias).filter(role='systemadmin').exists()):
        raise RuntimeError('School rollback refused: additional schools, assigned domains, audit history or System Admin accounts exist. Use a reviewed forward repair or verified backup.')
    samples = unchanged_manifests(apps, alias, omit_school=False)
    for app, label in OWNERS:
        apps.get_model(app, label).objects.using(alias).update(school_id=None)
    refresh_manifests(apps, alias, samples, omit_school=True)
    schools.get(code='ADNU').delete(using=alias)


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0020_school_foundation'),
        ('depthead', '0002_collegeaiinsight_school_and_more'),
        ('faculty', '0029_statusemaildelivery_html_body'),
    ]
    operations = [migrations.RunPython(forwards, backwards)]
