from django.db import migrations


def enable_two_way_sync(apps, schema_editor):
    FacultyProfile = apps.get_model('faculty', 'FacultyProfile')
    FacultyProfile.objects.all().update(sync_enabled=True)


class Migration(migrations.Migration):
    dependencies = [('faculty', '0031_facultyprofile_daily_check_in')]

    operations = [migrations.RunPython(enable_two_way_sync, migrations.RunPython.noop)]
