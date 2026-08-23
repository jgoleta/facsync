from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faculty', '0011_recurring_schedule_days'),
    ]

    operations = [
        migrations.AddField(
            model_name='scheduleevent',
            name='start_month',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='scheduleevent',
            name='end_month',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
    ]
