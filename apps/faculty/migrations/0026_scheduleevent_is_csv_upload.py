from django.db import migrations, models


def mark_existing_uploads(apps, schema_editor):
    ScheduleEvent = apps.get_model('faculty', 'ScheduleEvent')
    ScheduleEvent.objects.using(schema_editor.connection.alias).filter(
        uploaded_by__isnull=False,
    ).update(is_csv_upload=True)


class Migration(migrations.Migration):
    dependencies = [('faculty', '0025_consultation_cancellation_requested')]

    operations = [
        migrations.AddField(
            model_name='scheduleevent',
            name='is_csv_upload',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(mark_existing_uploads, migrations.RunPython.noop),
    ]
