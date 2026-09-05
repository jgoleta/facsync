from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faculty', '0002_scheduleevent_google_calendar_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='facultyprofile',
            name='biography',
            field=models.TextField(blank=True),
        ),
    ]
