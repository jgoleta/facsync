"""One recipient policy for student feeds, chat answers and notifications."""
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from .education import LEVELS
from .school_scope import require_school


def student_recipients(department, levels):
    basic = [level for level in levels if level in LEVELS and level != 'college']
    query = Q(role='student', educational_level__in=basic)
    if 'college' in levels:
        query |= Q(role='student', educational_level='college', department=department)
    return query


def student_announcement_queryset(student, queryset):
    school = require_school(student.school)
    if student.role != 'student' or student.school_id != school.pk or student.educational_level not in LEVELS:
        return queryset.none()
    # Fixed-size JSON arrays work on both PostgreSQL and local SQLite tests.
    levels = Q()
    for index in range(len(LEVELS)):
        levels |= Q(**{f'student_levels__{index}': student.educational_level})
    queryset = queryset.filter(levels, school_id=school.pk, audience__in=['students', 'both'])
    if student.educational_level == 'college':
        if student.department_id is None:
            return queryset.none()
        queryset = queryset.filter(department_id=student.department_id)
    return queryset
