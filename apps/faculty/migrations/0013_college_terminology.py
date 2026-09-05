from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('faculty', '0012_schedule_month_range'),
        ('core', '0015_college_terminology'),
    ]

    operations = [
        migrations.RenameField(
            model_name='facultyprofile',
            old_name='department_id',
            new_name='college_id',
        ),
    ]
