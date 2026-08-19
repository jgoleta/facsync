from django.db import migrations

DEPARTMENTS = [
    ('CHSS', 'College of Humanities and Social Sciences'),
    ('CBA', 'College of Business and Accountancy'),
    ('CCS', 'College of Computer Studies'),
    ('CED', 'College of Education'),
    ('CSEA', 'College of Science, Engineering, and Architecture'),
    ('CON', 'College of Nursing'),
    ('COL', 'College of Law'),
]

def seed_departments(apps, schema_editor):
    Department = apps.get_model('core', 'Department')
    for code, name in DEPARTMENTS:
        Department.objects.get_or_create(code=code, defaults={'name': name})

def reverse_seed(apps, schema_editor):
    Department = apps.get_model('core', 'Department')
    Department.objects.filter(code__in=[c for c, _ in DEPARTMENTS]).delete()

class Migration(migrations.Migration):
    dependencies = [
        ('core', '0008_departmentannouncement'), 
    ]
    operations = [
        migrations.RunPython(seed_departments, reverse_seed),
    ]