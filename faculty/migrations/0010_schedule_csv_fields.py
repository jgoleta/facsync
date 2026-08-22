from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faculty', '0009_consultationrequest_approved_at_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='facultyprofile',
            name='schedule_last_updated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='scheduleevent',
            name='location',
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name='scheduleevent',
            name='schedule_status',
            field=models.CharField(blank=True, max_length=32),
        ),
    ]
