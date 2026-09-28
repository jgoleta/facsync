from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('faculty', '0022_consultation_mode_and_meet_link')]

    operations = [
        migrations.RemoveField(model_name='consultationrequest', name='mode'),
        migrations.RemoveField(model_name='consultationrequest', name='google_meet_link'),
    ]
