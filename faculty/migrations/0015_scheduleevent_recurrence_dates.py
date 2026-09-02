from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faculty', '0014_alter_facultyprofile_college_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='scheduleevent',
            name='recurrence_end_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='scheduleevent',
            name='recurrence_start_date',
            field=models.DateField(blank=True, null=True),
        ),
    ]
