from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faculty', '0015_scheduleevent_recurrence_dates'),
    ]

    operations = [
        migrations.AddField(
            model_name='consultationrequest',
            name='agenda',
            field=models.CharField(
                choices=[
                    ('grade_consultation', 'Grade Consultation'),
                    ('project_consultation', 'Project Consultation'),
                    ('general_concern', 'General Concern / Talk'),
                    ('academic_advising', 'Academic Advising'),
                ],
                default='general_concern',
                max_length=32,
            ),
        ),
    ]
