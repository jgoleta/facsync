from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('faculty', '0020_schedule_offering_fields')]

    operations = [
        migrations.RemoveField(model_name='scheduleevent', name='teacher'),
    ]
