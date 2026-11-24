from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0039_user_roles')]

    operations = [
        migrations.AddField('deptheadinvite', 'faculty_id', models.CharField(blank=True, default='', max_length=64)),
        migrations.AddField('officeadmininvite', 'faculty_id', models.CharField(blank=True, default='', max_length=64)),
    ]
