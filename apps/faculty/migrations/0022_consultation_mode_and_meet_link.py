from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('faculty', '0021_remove_scheduleevent_teacher')]

    operations = [
        migrations.AddField(
            model_name='consultationrequest',
            name='mode',
            field=models.CharField(
                choices=[('face_to_face', 'Face-to-face'), ('online', 'Online')],
                default='face_to_face',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='consultationrequest',
            name='google_meet_link',
            field=models.URLField(blank=True, max_length=2048),
        ),
    ]
