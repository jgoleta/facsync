from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faculty', '0004_alter_facultyprofile_biography'),
    ]

    operations = [
        migrations.AddField(
            model_name='facultyprofile',
            name='manual_status',
            field=models.CharField(
                choices=[
                    ('available', 'Available'),
                    ('busy', 'Busy'),
                    ('virtual_only', 'Virtual Only'),
                    ('on_leave', 'On Leave'),
                    ('unavailable', 'Unavailable'),
                ],
                default='available',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='facultyprofile',
            name='sync_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='googlecalendarconnection',
            name='last_sync_error',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='scheduleevent',
            name='managed_by_facsync',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='scheduleevent',
            name='sync_error',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='scheduleevent',
            name='sync_state',
            field=models.CharField(default='local', max_length=16),
        ),
        migrations.AddField(
            model_name='consultationrequest',
            name='calendar_sync_error',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='consultationrequest',
            name='calendar_sync_status',
            field=models.CharField(default='not_configured', max_length=16),
        ),
        migrations.AddField(
            model_name='consultationrequest',
            name='end_time',
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='consultationrequest',
            name='google_calendar_id',
            field=models.CharField(blank=True, max_length=1024, null=True),
        ),
        migrations.AddField(
            model_name='consultationrequest',
            name='google_event_id',
            field=models.CharField(blank=True, db_index=True, max_length=1024, null=True),
        ),
        migrations.AddField(
            model_name='consultationrequest',
            name='last_calendar_sync_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='consultationrequest',
            name='start_time',
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='consultationrequest',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('approved', 'Approved'),
                    ('declined', 'Declined'),
                    ('cancelled', 'Cancelled'),
                    ('completed', 'Completed'),
                ],
                default='pending',
                max_length=16,
            ),
        ),
    ]
