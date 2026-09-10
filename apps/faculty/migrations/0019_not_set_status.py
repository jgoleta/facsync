from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('faculty', '0018_scheduleevent_uploaded_by'),
        ('faculty', '0018_scheduleevent_recurrence_excluded_dates'),
    ]

    operations = [
        migrations.AlterField(
            model_name='facultyprofile',
            name='current_status',
            field=models.CharField(
                choices=[
                    ('not_set', 'Not Set (Default Status)'),
                    ('available', 'Available'),
                    ('busy', 'Busy'),
                    ('virtual_only', 'Virtual Only'),
                    ('on_leave', 'On Leave'),
                    ('unavailable', 'Unavailable'),
                ],
                default='not_set',
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name='facultyprofile',
            name='manual_status',
            field=models.CharField(
                choices=[
                    ('not_set', 'Not Set (Default Status)'),
                    ('available', 'Available'),
                    ('busy', 'Busy'),
                    ('virtual_only', 'Virtual Only'),
                    ('on_leave', 'On Leave'),
                    ('unavailable', 'Unavailable'),
                ],
                default='not_set',
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name='statushistory',
            name='status',
            field=models.CharField(
                choices=[
                    ('not_set', 'Not Set (Default Status)'),
                    ('available', 'Available'),
                    ('busy', 'Busy'),
                    ('virtual_only', 'Virtual Only'),
                    ('on_leave', 'On Leave'),
                    ('unavailable', 'Unavailable'),
                ],
                max_length=16,
            ),
        ),
    ]
