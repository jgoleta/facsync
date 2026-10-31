from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faculty', '0029_statusemaildelivery_html_body'),
    ]

    operations = [
        migrations.AddField(
            model_name='scheduleevent',
            name='extra_attributes',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
