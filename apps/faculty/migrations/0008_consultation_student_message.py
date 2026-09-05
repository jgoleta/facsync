from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faculty', '0007_manual_status_override'),
    ]

    operations = [
        migrations.AddField(
            model_name='consultationrequest',
            name='student_message',
            field=models.TextField(blank=True, default=''),
        ),
    ]
