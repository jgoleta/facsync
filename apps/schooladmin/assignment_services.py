"""Validated assignments shared by School Admin forms and first-login activation."""
from django.core.exceptions import ValidationError

from django.db import transaction

from apps.core.models import Department, DeptHeadInvite, School, User, UserRole
from apps.core.role_access import has_role
from apps.faculty.models import ConsultationRequest, ScheduleEvent, StatusHistory, WalkInQueue


def lock_departments(departments, school):
    ids = {item.pk for item in departments}
    locked = list(Department.objects.select_for_update().filter(pk__in=ids, school=school, is_active=True).order_by('pk'))
    if not ids or len(locked) != len(ids):
        raise ValidationError('A selected department is no longer active or available. Please refresh and try again.')
    return locked


def faculty_has_activity(user):
    return (ConsultationRequest.objects.filter(faculty__user=user).exists()
            or WalkInQueue.objects.filter(faculty__user=user).exists()
            or StatusHistory.objects.filter(faculty__user=user).exists()
            or ScheduleEvent.objects.filter(faculty__user=user).exists())


@transaction.atomic
def add_head_access_to_faculty(actor, user_id, departments, title):
    """Promote a same-school Faculty account while preserving its Faculty data."""
    School.objects.select_for_update().get(pk=actor.school_id, is_active=True)
    target = User.objects.select_for_update().get(pk=user_id, school_id=actor.school_id)
    if not has_role(target, 'faculty'):
        raise ValidationError('Only an active Faculty account in this school can receive Head access directly.')
    if has_role(target, 'depthead'):
        raise ValidationError('This account already has Head access. Use Edit to change its assignments.')
    if not target.is_active or target.account_status != 'active':
        raise ValidationError('Reactivate this Faculty account before adding Head access.')
    locked_departments = lock_departments(departments, actor.school)

    faculty_role, created = UserRole.objects.get_or_create(
        user=target, role='faculty', defaults={'assigned_by': actor},
    )
    if not created and not faculty_role.is_active:
        faculty_role.is_active = True
        faculty_role.assigned_by = actor
        faculty_role.save(update_fields=['is_active', 'assigned_by'])

    target.role = 'depthead'
    target.title = title
    # ``department`` and ``college`` remain the Faculty home assignment.
    target.save(update_fields=['role', 'title'])
    target.managed_departments.set(locked_departments)
    DeptHeadInvite.objects.filter(
        school_id=actor.school_id, email__iexact=target.email, used=False,
    ).delete()
    return target, locked_departments
