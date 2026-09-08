from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('faculty', '0017_facultyprofile_manual_status_expires_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='scheduleevent',
            name='recurrence_excluded_dates',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
