from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('faculty', '0036_consultation_satisfaction'),
    ]

    operations = [
        migrations.AddField(
            model_name='facultyprofile',
            name='consultation_note',
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
