from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('faculty', '0032_enable_two_way_sync')]

    operations = [
        migrations.AddField(
            model_name='consultationrequest',
            name='google_meet_link',
            field=models.URLField(blank=True, max_length=2048),
        ),
    ]
