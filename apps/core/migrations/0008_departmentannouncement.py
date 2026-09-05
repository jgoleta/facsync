import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_department'),
    ]

    operations = [
        migrations.CreateModel(
            name='DepartmentAnnouncement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('department', models.CharField(choices=[('chss', 'College of Humanities and Social Sciences'), ('cba', 'College of Business and Accountancy'), ('ccs', 'College of Computer Studies'), ('ced', 'College of Education'), ('csea', 'College of Science, Engineering, and Architecture'), ('con', 'College of Nursing'), ('col', 'College of Law')], max_length=20)),
                ('message', models.TextField()),
                ('posted_at', models.DateTimeField(auto_now_add=True)),
                ('expiry', models.DateTimeField()),
                ('posted_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-posted_at'],
            },
        ),
    ]