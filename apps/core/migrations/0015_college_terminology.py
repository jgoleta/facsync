from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_deptheadinvite_title'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Department',
            new_name='College',
        ),
        migrations.RenameModel(
            old_name='DepartmentAnnouncement',
            new_name='CollegeAnnouncement',
        ),
        migrations.RenameField(
            model_name='user',
            old_name='department',
            new_name='college',
        ),
        migrations.RenameField(
            model_name='facultyinvite',
            old_name='department',
            new_name='college',
        ),
        migrations.RenameField(
            model_name='deptheadinvite',
            old_name='department',
            new_name='college',
        ),
        migrations.RenameField(
            model_name='officeclosure',
            old_name='department',
            new_name='college',
        ),
        migrations.RenameField(
            model_name='collegeannouncement',
            old_name='department',
            new_name='college',
        ),
    ]
