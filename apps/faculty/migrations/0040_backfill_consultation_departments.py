from django.db import migrations


def backfill_consultation_departments(apps, schema_editor):
    ConsultationRequest = apps.get_model('faculty', 'ConsultationRequest')
    consultations = ConsultationRequest.objects.filter(
        department__isnull=True,
        faculty__user__department__isnull=False,
    ).select_related('faculty__user')
    for consultation in consultations.iterator():
        consultation.department_id = consultation.faculty.user.department_id
        consultation.save(update_fields=['department'])


class Migration(migrations.Migration):
    dependencies = [
        ('faculty', '0039_consultation_rating_scale'),
    ]

    operations = [
        migrations.RunPython(backfill_consultation_departments, migrations.RunPython.noop),
    ]
