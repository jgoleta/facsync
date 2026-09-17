from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('faculty', '0019_not_set_status')]

    operations = [
        migrations.AddField(model_name='scheduleevent', name='offering_id', field=models.CharField(blank=True, max_length=128)),
        migrations.AddField(model_name='scheduleevent', name='subject_code', field=models.CharField(blank=True, max_length=64)),
        migrations.AddField(model_name='scheduleevent', name='section', field=models.CharField(blank=True, max_length=64)),
        migrations.AddField(model_name='scheduleevent', name='units', field=models.CharField(blank=True, max_length=32)),
        migrations.AddField(model_name='scheduleevent', name='lecture', field=models.CharField(blank=True, max_length=32)),
        migrations.AddField(model_name='scheduleevent', name='lab', field=models.CharField(blank=True, max_length=32)),
        migrations.AddField(model_name='scheduleevent', name='teacher', field=models.CharField(blank=True, max_length=128)),
    ]
