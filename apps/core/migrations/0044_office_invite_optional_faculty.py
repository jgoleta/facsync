from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0043_remove_facultyinvite_prepare_test_requests')]
    operations = [
        # Existing invitations promised combined access; preserve that promise.
        migrations.AddField(
            model_name='officeadmininvite', name='include_faculty_access',
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name='officeadmininvite', name='include_faculty_access',
            field=models.BooleanField(default=False),
        ),
    ]
