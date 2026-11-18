from django.db import migrations, models
import django.db.models.deletion


ROLE_CHOICES = [
    ('student', 'Student'),
    ('faculty', 'Faculty'),
    ('depthead', 'College Head'),
    ('officeadmin', 'Office Admin'),
    ('superadmin', 'School Admin'),
    ('systemadmin', 'Super Admin'),
]


def copy_primary_roles(apps, schema_editor):
    User = apps.get_model('core', 'User')
    UserRole = apps.get_model('core', 'UserRole')
    UserRole.objects.using(schema_editor.connection.alias).bulk_create(
        [UserRole(user_id=user.pk, role=user.role) for user in User.objects.using(schema_editor.connection.alias).only('pk', 'role')],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0038_student_served_levels'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserRole',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=ROLE_CHOICES, max_length=20)),
                ('is_active', models.BooleanField(default=True)),
                ('assigned_at', models.DateTimeField(auto_now_add=True)),
                ('assigned_by', models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name='roles_assigned', to='core.user')),
                ('user', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='role_assignments', to='core.user')),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('user', 'role'), name='user_role_unique')],
            },
        ),
        migrations.RunPython(copy_primary_roles, migrations.RunPython.noop),
    ]
