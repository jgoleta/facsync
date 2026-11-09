from django.db import migrations, models
from django.db.models import Count


def check_existing_domains(apps, schema_editor):
    domains = apps.get_model('core', 'SchoolDomain').objects.using(schema_editor.connection.alias)
    if domains.values('school_id').annotate(total=Count('pk')).filter(total__gt=1).exists():
        raise RuntimeError('Domain migration stopped: a school has multiple domains. Choose its one retained domain before retrying. No domains were removed automatically.')


class Migration(migrations.Migration):
    dependencies = [('core', '0032_school_registration_request')]
    operations = [
        migrations.RunPython(check_existing_domains, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name='schooldomain', name='school_domain_edu_ph'),
        migrations.AddConstraint(model_name='schooldomain', constraint=models.UniqueConstraint(
            fields=('school',), name='school_domain_one_per_school')),
    ]
