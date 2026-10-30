"""Legacy single-school fixtures now explicitly run in an ADNU tenant context.

Only fixture ownership changes; assertions and application behavior remain under
test. Isolation tests use ordinary TestCase with two explicitly assigned schools.
No production defaults or database configuration are changed here.
"""
from django.test import TestCase

from apps.core.models import School
from apps.core.school_scope import school_scope


class SchoolTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.school = School.objects.get(code='ADNU')
        cls._school_context = school_scope(cls.school)
        cls._school_context.__enter__()
        cls.addClassCleanup(cls._school_context.__exit__, None, None, None)
