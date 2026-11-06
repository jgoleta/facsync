"""Classify legacy students without inventing a new department or changing history."""
import hashlib
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import migrations, models


def fingerprint(item, omit_level=False):
    values = {field.attname: getattr(item, field.attname) for field in item._meta.concrete_fields
              if not (omit_level and field.name == 'educational_level')}
    return hashlib.sha256(json.dumps(values, cls=DjangoJSONEncoder, sort_keys=True).encode()).hexdigest()


def manifests(apps, alias, omit_level):
    result = []
    User = apps.get_model('core', 'User')
    for batch in apps.get_model('core', 'DemoDataBatch')._base_manager.using(alias).all():
        hashes = batch.manifest.get('core.User', {})
        owned = [item.pk for item in User._base_manager.using(alias).filter(pk__in=hashes)
                 if fingerprint(item, omit_level) == hashes[str(item.pk)]]
        result.append((batch, owned))
    return result


def update_manifests(apps, alias, snapshots, omit_level):
    User = apps.get_model('core', 'User')
    for batch, owned in snapshots:
        if owned:
            for item in User._base_manager.using(alias).filter(pk__in=owned):
                batch.manifest['core.User'][str(item.pk)] = fingerprint(item, omit_level)
            batch.save(using=alias, update_fields=['manifest'])


def forwards(apps, schema_editor):
    alias = schema_editor.connection.alias
    User = apps.get_model('core', 'User')
    students = User._base_manager.using(alias).filter(role='student')
    if students.exclude(educational_level__in=['', 'college']).exists() or any(
            school.educational_levels != ['college'] for school in apps.get_model('core', 'School')._base_manager.using(alias).all()):
        raise RuntimeError('Educational-level configuration already changed before classification. Review the partial rollout rather than overwriting it.')
    invalid = students.filter(profile_completed=True).filter(
        models.Q(department__isnull=True) | ~models.Q(year_level__in=['1', '2', '3', '4', '5', '6']))
    if invalid.exists():
        raise RuntimeError('Completed student profiles need a valid department and college year before educational-level migration. Review these records on the disposable copy first.')
    if students.exclude(year_level__in=['', '1', '2', '3', '4', '5', '6']).exclude(year_level__isnull=True).exists():
        raise RuntimeError('An existing student has an invalid college year. Review the profile on the disposable copy before migration.')
    snapshots = manifests(apps, alias, omit_level=True)
    students.update(educational_level='college')
    update_manifests(apps, alias, snapshots, omit_level=False)


def backwards(apps, schema_editor):
    alias = schema_editor.connection.alias
    School = apps.get_model('core', 'School')
    User = apps.get_model('core', 'User')
    if any(s.educational_levels != ['college'] for s in School._base_manager.using(alias).all()):
        raise RuntimeError('Cannot remove educational levels after a school changes its offered levels.')
    students = User._base_manager.using(alias).filter(role='student')
    if students.exclude(educational_level__in=['', 'college']).exists() or students.exclude(year_level__in=['', '1', '2', '3', '4']).exclude(year_level__isnull=True).exists():
        raise RuntimeError('Cannot remove educational levels: current student profiles cannot fit the previous schema.')
    if apps.get_model('core', 'SchoolChangeLog')._base_manager.using(alias).filter(field='educational_levels').exists():
        raise RuntimeError('Cannot shrink school history while educational-level audit entries exist. Preserve the audit log and use a forward repair or verified backup.')
    snapshots = manifests(apps, alias, omit_level=False)
    update_manifests(apps, alias, snapshots, omit_level=True)


class Migration(migrations.Migration):
    dependencies = [('core', '0030_educational_levels')]
    operations = [migrations.RunPython(forwards, backwards)]
