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


def has_role(user, role):
    if not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'role', None) == role:
        return True
    return user.role_assignments.filter(role=role, is_active=True).exists()


def available_roles(user):
    roles = []
    legacy_role = getattr(user, 'role', None)
    if legacy_role in ROLE_LABELS:
        roles.append(legacy_role)
    if getattr(user, 'pk', None):
        assigned = user.role_assignments.filter(is_active=True).values_list('role', flat=True)
        roles.extend(role for role in assigned if role not in roles)
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
    """Return a queryset filter matching legacy or explicitly assigned roles."""
    return Q(**{f'{prefix}role': role}) | Q(
        **{f'{prefix}role_assignments__role': role,
           f'{prefix}role_assignments__is_active': True}
    )


def roles_filter(roles, prefix=''):
    combined = Q()
    for role in roles:
        combined |= role_filter(role, prefix)
    return combined

