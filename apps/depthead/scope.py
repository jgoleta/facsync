"""Explicit assigned-department scopes; legacy strings remain for office/school reports."""
from dataclasses import dataclass
from hashlib import sha256

from django.core.exceptions import PermissionDenied
from django.db.models import Q

from apps.core.models import Department
from apps.core.school_scope import require_school


@dataclass(frozen=True)
class DepartmentScope:
    school_id: int
    department_ids: tuple
    names: tuple
    include_offices: bool = False

    def __bool__(self):
        return bool(self.department_ids) or self.include_offices

    @property
    def key(self):
        identity = ','.join(map(str, sorted(set(self.department_ids))))
        if self.include_offices:
            identity += ':offices'
        return 'DEPARTMENTS:' + sha256(f'{self.school_id}:{identity}'.encode()).hexdigest().upper()

    @property
    def name(self):
        return ', '.join(self.names) or 'No departments assigned'

    def __str__(self):
        return self.key

    def check(self):
        if require_school().pk != self.school_id:
            raise PermissionDenied('Department reports must stay within the assigned school.')


def head_scope(user):
    if user.role == 'officeadmin':
        return user.college or ''
    departments = list(managed_departments(user).order_by('pk'))
    return DepartmentScope(user.school_id, tuple(d.pk for d in departments), tuple(d.name for d in departments))


def managed_departments(user):
    return Department.objects.filter(school_id=user.school_id, is_active=True, heads=user)


def member_scope(user):
    if user.department_id:
        return DepartmentScope(user.school_id, (user.department_id,), (user.department.name,))
    return user.college or ''


def faculty_q(scope, prefix=''):
    if isinstance(scope, DepartmentScope):
        scope.check()
        departments = Q(**{prefix + 'user__department_id__in': scope.department_ids})
        if scope.include_offices:
            departments |= Q(**{prefix + 'user__department__isnull': True})
        return departments & Q(**{prefix + 'user__school_id': scope.school_id})
    return Q(**{prefix + 'college_id__iexact': str(scope or '').strip()})


def history_q(scope):
    if isinstance(scope, DepartmentScope):
        scope.check()
        return Q(department_id__in=scope.department_ids, faculty__user__school_id=scope.school_id)
    return faculty_q(scope, 'faculty__')
