from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faculty', '0005_calendar_sync_and_consultation_events'),
    ]

    operations = [
        migrations.AddField(
            model_name='facultyprofile',
            name='walk_ins_enabled',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='walkinqueue',
            name='notified_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='walkinqueue',
            name='status',
            field=models.CharField(
                choices=[
                    ('waiting', 'Waiting'),
                    ('called', 'Called to Office'),
                    ('completed', 'Completed'),
                    ('cancelled', 'Cancelled'),
                ],
                default='waiting',
                max_length=16,
            ),
        ),
    ]
