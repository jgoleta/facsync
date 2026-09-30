from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('faculty', '0024_consultationrequest_consultation_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='consultationrequest',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('approved', 'Approved'),
                    ('cancellation_requested', 'Cancellation Requested'),
                    ('declined', 'Declined'),
                    ('cancelled', 'Cancelled'),
                    ('completed', 'Completed'),
                ],
                default='pending',
                max_length=24,
            ),
        ),
    ]
