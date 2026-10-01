from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('faculty', '0026_scheduleevent_is_csv_upload')]

    operations = [
        migrations.AddField(
            model_name='scheduleevent', name='recurring_parent',
            field=models.ForeignKey(null=True, blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='edited_occurrences', to='faculty.scheduleevent'),
        ),
        migrations.AddField(
            model_name='scheduleevent', name='original_occurrence_date',
            field=models.DateField(null=True, blank=True),
        ),
    ]
