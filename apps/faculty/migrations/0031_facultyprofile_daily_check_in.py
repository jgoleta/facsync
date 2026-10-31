from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faculty', '0030_scheduleevent_extra_attributes'),
    ]

    operations = [
        migrations.AddField(
            model_name='facultyprofile',
            name='daily_check_in_at_office',
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='facultyprofile',
            name='daily_check_in_date',
            field=models.DateField(blank=True, null=True),
        ),
    ]
