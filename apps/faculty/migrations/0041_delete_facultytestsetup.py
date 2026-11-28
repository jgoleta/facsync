from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('faculty', '0040_backfill_consultation_departments'),
    ]

    operations = [
        migrations.DeleteModel(
            name='FacultyTestSetup',
        ),
    ]
