from django.db import migrations, models
import django.db.models.deletion


def preserve_pending_faculty_access(apps, schema_editor):
    Invite = apps.get_model('core', 'DeptHeadInvite')
    alias = schema_editor.connection.alias
    for invite in Invite.objects.using(alias).filter(used=False).exclude(faculty_id='').iterator():
        ids = list(invite.departments.using(alias).filter(school_id=invite.school_id, is_active=True)
                   .values_list('pk', flat=True))
        # Multiple homes require a deliberate selection through Edit and email.
        Invite.objects.using(alias).filter(pk=invite.pk).update(include_faculty_access=True,
            faculty_department_id=ids[0] if len(ids) == 1 else None)


class Migration(migrations.Migration):
    dependencies = [('core', '0040_admin_invite_faculty_id')]
    operations = [
        migrations.AddField('deptheadinvite', 'include_faculty_access', models.BooleanField(default=False)),
        migrations.AddField('deptheadinvite', 'faculty_department', models.ForeignKey(
            to='core.department', on_delete=django.db.models.deletion.PROTECT, null=True, blank=True,
            related_name='faculty_head_invites')),
        migrations.RunPython(preserve_pending_faculty_access, migrations.RunPython.noop),
    ]
