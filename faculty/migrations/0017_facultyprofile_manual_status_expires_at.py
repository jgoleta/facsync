from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('faculty', '0016_consultationrequest_agenda'),
    ]

    operations = [
        migrations.AddField(
            model_name='facultyprofile',
            name='manual_status_expires_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
