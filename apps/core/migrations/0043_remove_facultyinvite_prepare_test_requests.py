from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0042_facultyinvite_prepare_test_requests'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='facultyinvite',
            name='prepare_test_requests',
        ),
    ]
