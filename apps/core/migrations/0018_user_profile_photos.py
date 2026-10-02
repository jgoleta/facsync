from django.db import migrations, models


def preserve_faculty_photos(apps, schema_editor):
    User = apps.get_model('core', 'User')
    FacultyProfile = apps.get_model('faculty', 'FacultyProfile')
    alias = schema_editor.connection.alias
    for profile in FacultyProfile.objects.using(alias).exclude(photo_url='').iterator():
        User.objects.using(alias).filter(pk=profile.user_id, uploaded_photo_url='').update(
            uploaded_photo_url=profile.photo_url,
        )


class Migration(migrations.Migration):
    dependencies = [('core', '0017_collegeannouncement_audience'), ('faculty', '0027_scheduleevent_occurrence_parent')]
    operations = [
        migrations.AddField(model_name='user', name='google_photo_url', field=models.URLField(blank=True, max_length=2048)),
        migrations.AddField(model_name='user', name='uploaded_photo_url', field=models.URLField(blank=True, max_length=2048)),
        migrations.RunPython(preserve_faculty_photos, migrations.RunPython.noop),
    ]
