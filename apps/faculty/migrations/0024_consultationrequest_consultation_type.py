from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('faculty', '0023_remove_consultation_meet_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='consultationrequest',
            name='consultation_type',
            field=models.CharField(
                choices=[('face_to_face', 'Face-to-Face'), ('online', 'Online')],
                default='face_to_face',
                max_length=16,
            ),
        ),
    ]
