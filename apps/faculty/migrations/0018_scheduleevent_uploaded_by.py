from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('faculty', '0017_facultyprofile_manual_status_expires_at'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='scheduleevent',
            name='uploaded_by',
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL,
                null=True,
                blank=True,
                on_delete=models.SET_NULL,
                related_name='uploaded_schedule_events',
            ),
        ),
    ]
