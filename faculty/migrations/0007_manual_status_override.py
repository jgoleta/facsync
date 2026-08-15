from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faculty', '0006_walk_in_controls'),
    ]

    operations = [
        migrations.AddField(
            model_name='facultyprofile',
            name='manual_status_override',
            field=models.BooleanField(default=False),
        ),
    ]
