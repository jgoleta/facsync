from django.db import migrations, models


def normalize_legacy_ratings(apps, schema_editor):
    """Keep existing ratings valid when the product moves to a five-point scale."""
    ConsultationRequest = apps.get_model('faculty', 'ConsultationRequest')
    ConsultationRequest.objects.filter(satisfaction_rating__gt=5).update(
        satisfaction_rating=5,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('faculty', '0038_facultytestsetup'),
    ]

    operations = [
        migrations.RunPython(normalize_legacy_ratings, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='consultationrequest',
            name='consultation_rating_valid',
        ),
        migrations.AddConstraint(
            model_name='consultationrequest',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        satisfaction_rating__isnull=True,
                        rating_submitted_at__isnull=True,
                        rating_updated_at__isnull=True,
                    )
                    | models.Q(
                        satisfaction_rating__isnull=False,
                        satisfaction_rating__gte=1,
                        satisfaction_rating__lte=5,
                        rating_submitted_at__isnull=False,
                        rating_updated_at__isnull=False,
                    )
                ),
                name='consultation_rating_valid',
            ),
        ),
    ]
