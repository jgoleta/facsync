"""Role assignment and active-role helpers.

The legacy ``User.role`` field remains the primary-role compatibility field while
accounts are migrated to explicit role assignments.
"""

from django.core.exceptions import PermissionDenied
from django.db.models import Q


ROLE_LABELS = {
    'student': 'Student',
    'faculty': 'Faculty',
    'depthead': 'Department Head',
    'officeadmin': 'Office Admin',
    'superadmin': 'School Admin',
    'systemadmin': 'Super Admin',
}

SINGLE_ROLES = {'student', 'superadmin'}


def validate_role_combination(primary, assigned):
    from django.core.exceptions import ValidationError
    roles = {primary, *assigned}
    if roles & SINGLE_ROLES and len(roles) > 1:
        raise ValidationError('Student and School Admin accounts must have only their own role.')


def has_role(user, role):
    if not getattr(user, 'is_authenticated', False):
        return False
    primary = getattr(user, 'role', None)
    if (primary in SINGLE_ROLES or role in SINGLE_ROLES) and primary != role:
        return False
    assignment = user.role_assignments.filter(role=role).values_list('is_active', flat=True).first() if user.pk else None
    return assignment if assignment is not None else primary == role


def can_access_role(user, role):
    if has_role(user, role):
        return True
    # Preserve Office Admin's original combined workspace, unless an explicit
    # assignment has deliberately disabled this capability.
    return (role in {'depthead', 'faculty'} and has_role(user, 'officeadmin')
            and not user.role_assignments.filter(role=role).exists())


def available_roles(user):
    if not getattr(user, 'is_authenticated', False):
        return []
    roles = []
    legacy_role = getattr(user, 'role', None)
    assignments = dict(user.role_assignments.values_list('role', 'is_active')) if getattr(user, 'pk', None) else {}
    if legacy_role in ROLE_LABELS and assignments.get(legacy_role, True):
        roles.append(legacy_role)
    if legacy_role not in SINGLE_ROLES:
        roles.extend(role for role, enabled in assignments.items()
                     if enabled and role not in roles and role not in SINGLE_ROLES and role in ROLE_LABELS)
    return [(role, ROLE_LABELS[role]) for role in roles]


def active_role(request):
    selected = request.session.get('active_role')
    if selected and any(role == selected for role, _ in available_roles(request.user)):
        return selected
    roles = available_roles(request.user)
    return roles[0][0] if roles else None


def require_role(user, role):
    if not has_role(user, role):
        raise PermissionDenied


def role_filter(role, prefix=''):
    """Match role membership without multiplying outer rows by assignments."""
    from .models import UserRole

    explicit_users = UserRole.objects.filter(role=role).values('user_id')
    fallback = Q(**{f'{prefix}role': role}) & ~Q(**{f'{prefix}pk__in': explicit_users})
    if role in SINGLE_ROLES:
        assigned_users = UserRole.objects.filter(role=role, is_active=True, user__role=role).values('user_id')
    else:
        assigned_users = UserRole.objects.filter(role=role, is_active=True).exclude(user__role__in=SINGLE_ROLES).values('user_id')
    return fallback | Q(**{f'{prefix}pk__in': assigned_users})


def roles_filter(roles, prefix=''):
    combined = Q()
    for role in roles:
        combined |= role_filter(role, prefix)
    return combined

