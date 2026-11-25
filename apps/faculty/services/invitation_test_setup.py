"""Prepare opt-in batches without making sign-in depend on test data creation."""
import logging
from datetime import timedelta

from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone

from apps.core.models import School, User
from apps.core.school_scope import school_scope
from apps.faculty.models import FacultyTestSetup
from .test_requests import TestRequestBuilder, ZONE

logger = logging.getLogger(__name__)


def _prepare(user, *, retry=False):
    with school_scope(user.school), transaction.atomic():
        # Same ordering as invitation activation and the command-line preparer.
        School.objects.select_for_update().get(pk=user.school_id, is_active=True)
        owner = User.objects.select_for_update().get(pk=user.pk)
        setup = FacultyTestSetup.objects.select_for_update().filter(user=owner).first()
        if setup is None or setup.status == 'ready' or (setup.status == 'blocked' and not retry):
            return
        if not owner.profile_completed:
            return
        try:
            with transaction.atomic():
                builder = TestRequestBuilder()
                faculty = builder._faculty(owner.email)
                student = builder._student(faculty)
                start = timezone.now().astimezone(ZONE).date() + timedelta(days=1)
                slots = builder._plan(faculty, start, 21)
                builder.create_requests(faculty, student, slots)
                setup.status = 'ready'
                setup.last_error = ''
                setup.prepared_at = timezone.now()
                setup.save(update_fields=['status', 'last_error', 'prepared_at'])
        except Exception as error:
            # Savepoint rolls back student and all requests if any part fails.
            setup.status = 'blocked'
            setup.last_error = (str(error)[:240] if isinstance(error, CommandError)
                else 'Test requests could not be prepared. Please retry or contact the research team.')
            setup.prepared_at = None
            setup.save(update_fields=['status', 'last_error', 'prepared_at'])
            logger.warning('faculty_test_preparation_failed user_id=%s category=%s', owner.pk, type(error).__name__)


def prepare_invitation_test_requests(user, *, retry=False):
    """Safe dashboard hook; no work for ordinary accounts or already prepared batches."""
    try:
        if not user.school_id:
            return
        statuses = ['pending', 'blocked'] if retry else ['pending']
        if FacultyTestSetup.objects.filter(user=user, status__in=statuses).exists():
            _prepare(user, retry=retry)
    except Exception as error:
        # Database/provider issues must never prevent access to the dashboard.
        logger.warning('faculty_test_setup_unavailable user_id=%s category=%s', user.pk, type(error).__name__)
