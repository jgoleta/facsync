"""Add Faculty access without using invitations as an assignment transfer."""
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.models import Department, Office, School, User, UserRole
from apps.core.role_access import has_role
from apps.faculty.models import FacultyProfile


@transaction.atomic
def add_faculty_access(actor, user_id, department=None):
    School.objects.select_for_update().get(pk=actor.school_id, is_active=True)
    if department is not None:
        from .scope import managed_departments
        if not has_role(actor, 'depthead') or not managed_departments(actor).filter(pk=department.pk).exists():
            raise ValidationError('Choose an active department that you manage.')
        department = Department.objects.select_for_update().get(pk=department.pk, school_id=actor.school_id, is_active=True)
        code = department.college.code if department.college_id else ''
        label = department.name
    else:
        office = Office.objects.select_for_update().filter(school_id=actor.school_id,
            code__iexact=actor.college or '', is_active=True).first()
        if not has_role(actor, 'officeadmin') or office is None:
            raise ValidationError('Choose an active office that you manage.')
        code, label = office.code, office.name

    target = User.objects.select_for_update().get(pk=user_id, school_id=actor.school_id)
    if has_role(target, 'faculty'):
        raise ValidationError('This account already has Faculty access. Use Edit Faculty Assignment to change its department.')
    if target.role in {'student', 'superadmin'} or not any(has_role(target, role) for role in ('depthead', 'officeadmin')):
        raise ValidationError('Faculty access can only be added to Department Head or Office Admin accounts. Student and School Admin accounts must remain single-role accounts.')
    if not target.is_active or target.account_status != 'active':
        raise ValidationError('Reactivate this account before adding Faculty access.')
    if ((target.department_id is not None and target.department_id != (department.pk if department else None))
            or (target.college and target.college.casefold() != code.casefold())):
        raise ValidationError('This account has a different existing assignment. Contact your School Admin to review it; Invite Faculty cannot transfer accounts.')
    profile = FacultyProfile.objects.filter(user=target).first()
    if profile and (profile.college_id or '').casefold() != code.casefold():
        raise ValidationError('This account has a different Faculty profile assignment. Contact your School Admin; its existing profile and history must be preserved.')

    role, created = UserRole.objects.get_or_create(user=target, role='faculty', defaults={'assigned_by': actor})
    if not created:
        role.is_active = True
        role.assigned_by = actor
        role.save(update_fields=['is_active', 'assigned_by'])
    changed = []
    if target.department_id is None and department is not None:
        target.department = department
        changed.append('department')
    if not target.college and code:
        target.college = code
        changed.append('college')
    if changed:
        target.save(update_fields=changed)
    FacultyProfile.objects.get_or_create(user=target,
        defaults={'faculty_id': f'FAC-{target.pk}', 'college_id': code})
    return target, label
