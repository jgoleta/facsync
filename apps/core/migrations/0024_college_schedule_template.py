from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0023_alter_user_role_superadmininvite'),
    ]

    operations = [
        migrations.AddField(
            model_name='college',
            name='schedule_template',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
