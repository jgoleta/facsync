from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faculty', '0010_schedule_csv_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='scheduleevent',
            name='date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='scheduleevent',
            name='day_of_week',
            field=models.CharField(
                blank=True,
                choices=[
                    ('monday', 'Monday'),
                    ('tuesday', 'Tuesday'),
                    ('wednesday', 'Wednesday'),
                    ('thursday', 'Thursday'),
                    ('friday', 'Friday'),
                    ('saturday', 'Saturday'),
                    ('sunday', 'Sunday'),
                ],
                max_length=9,
            ),
        ),
    ]
