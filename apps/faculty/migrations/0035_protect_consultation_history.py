import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('faculty', '0034_department_foundation'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AlterField(
            model_name='consultationrequest', name='user',
            field=models.ForeignKey(db_column='user_id', on_delete=django.db.models.deletion.PROTECT,
                                    related_name='student_consultation_requests', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='consultationrequest', name='faculty',
            field=models.ForeignKey(db_column='faculty_id', on_delete=django.db.models.deletion.PROTECT,
                                    related_name='consultation_requests', to='faculty.facultyprofile'),
        ),
    ]
