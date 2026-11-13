"""One educational-level boundary for student browsing and new requests.

Existing appointments and queue entries are authorized by ownership separately.
"""
from dataclasses import dataclass
from functools import wraps
from hashlib import sha256

from django.db.models import Q, Value
from django.db.models.functions import Coalesce, Lower, NullIf
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from .education import YEAR_CHOICES
from apps.depthead.scope import DepartmentScope


def profile_ready(student):
    level = student.educational_level
    return bool(student.role == 'student' and student.profile_completed and student.school_id
        and level in (student.school.educational_levels or [])
        and str(student.year_level or '') in dict(YEAR_CHOICES.get(level, []))
        and str(student.student_id or '').strip()
        and (level != 'college' or student.department_id))


def profile_response(request):
    url = reverse('core:student_profile_setup')
    if '/api/' in request.path or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'error': 'Complete your student profile and select your educational level before browsing faculty or making new requests.',
            'profile_required': True, 'profile_url': url}, status=403)
    return redirect(url)


def student_profile_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not profile_ready(request.user):
            return profile_response(request)
        return view(request, *args, **kwargs)
    return wrapped


class StudentEligibility:
    def __init__(self, student):
        from .models import Department, Office
        self.student = student
        self.departments, self.offices = [], []
        if (not profile_ready(student) or not student.is_active or student.account_status != 'active'
                or not student.school.is_active):
            return
        level = student.educational_level
        self.departments = [unit for unit in Department.objects.filter(school_id=student.school_id, is_active=True)
            .filter(Q(college__isnull=True) | Q(college__is_active=True)).select_related('college')
            if isinstance(unit.student_levels, list) and level in unit.student_levels]
        self.offices = [unit for unit in Office.objects.filter(school_id=student.school_id, is_active=True)
            if isinstance(unit.student_levels, list) and level in unit.student_levels]

    @property
    def department_ids(self):
        return tuple(unit.pk for unit in self.departments)

    @property
    def office_codes(self):
        return tuple(unit.code.strip().lower() for unit in self.offices)

    def faculty(self, queryset=None):
        from apps.faculty.models import FacultyProfile
        queryset = queryset if queryset is not None else FacultyProfile.objects.all()
        return queryset.filter(user__school_id=self.student.school_id, user__is_active=True,
            user__account_status='active', user__role__in=['faculty', 'officeadmin']).annotate(
                _access_office=Lower(Coalesce(NullIf('user__college', Value('')), 'college_id'))).filter(
                    Q(user__department_id__in=self.department_ids)
                    | Q(user__department__isnull=True, _access_office__in=self.office_codes))

    def allows(self, faculty):
        return self.faculty().filter(pk=faculty.pk).exists()

    def closures(self):
        from .models import OfficeClosure
        return OfficeClosure.objects.filter(school_id=self.student.school_id).annotate(_access_office=Lower('college')).filter(
            Q(department_id__in=self.department_ids)
            | Q(department__isnull=True, _access_office__in=self.office_codes))

    def scope(self):
        ids = tuple(self.faculty().values_list('pk', flat=True))
        return StudentAccessScope(self.student.school_id, self.department_ids,
            tuple(unit.name for unit in self.departments), bool(self.offices), ids)


@dataclass(frozen=True)
class StudentAccessScope(DepartmentScope):
    student_faculty_ids: tuple = ()

    @property
    def key(self):
        return 'STUDENT:' + sha256(f'{self.school_id}:{sorted(self.student_faculty_ids)}'.encode()).hexdigest().upper()


def student_can_access_faculty(student, faculty):
    return StudentEligibility(student).allows(faculty)
