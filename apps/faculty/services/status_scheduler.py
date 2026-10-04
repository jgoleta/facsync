"""Bounded automatic-status checks and durable, private email deliveries."""
import logging
import secrets
from datetime import timedelta
from time import monotonic

import requests
from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from django.core.mail import EmailMessage

from apps.core.email_backends import BrevoEmailBackend
from apps.students.models import FacultyStatusSubscription
from apps.faculty.models import FacultyProfile, StatusEmailDelivery, StatusSchedulerState
from .google_calendar import refresh_faculty_status

logger = logging.getLogger(__name__)
LEASE_SECONDS = 120
MAX_FACULTY = 10
MAX_EMAILS = 30


def database_budget():
    # Called inside atomic blocks. A contested profile must not consume the
    # scheduler's entire HTTP budget. These limits reset at transaction end.
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '1000ms'")
            cursor.execute("SET LOCAL statement_timeout = '3000ms'")


def acquire_lease():
    with transaction.atomic():
        database_budget()
        state, _ = StatusSchedulerState.objects.get_or_create(name='automatic-status')
        token = secrets.token_hex(16)
        now = timezone.now()
        won = StatusSchedulerState.objects.filter(pk=state.pk).filter(
            Q(lease_until__isnull=True) | Q(lease_until__lte=now),
        ).update(lease_token=token, lease_until=now + timedelta(seconds=LEASE_SECONDS))
        return token if won else None


def submit_batch(deliveries):
    """One HTTPS call, one private recipient per version. Never log payloads."""
    backend = BrevoEmailBackend()
    try:
        payloads = [backend._payload(EmailMessage(
            row.subject, row.body, settings.DEFAULT_FROM_EMAIL, [row.email],
        )) for row in deliveries]
    except Exception:
        return 'failed', 'invalid_message'
    first = payloads[0]
    payload = {
        'sender': first['sender'], 'subject': first['subject'],
        'textContent': first['textContent'],
        'messageVersions': [{k: v for k, v in item.items() if k != 'sender'} for item in payloads],
    }
    try:
        with requests.post(
            backend.endpoint, json=payload,
            headers={'api-key': settings.BREVO_API_KEY, 'Accept': 'application/json'},
            timeout=(2, 5), allow_redirects=False,
        ) as response:
            if response.status_code == 201:
                try:
                    result = response.json()
                except ValueError:
                    return 'unknown', 'invalid_acceptance_response'
                ids = result.get('messageIds') if isinstance(result, dict) else None
                if isinstance(ids, list) and len(ids) == len(deliveries) and all(isinstance(i, str) and i for i in ids):
                    return 'accepted', 'provider_accepted'
                return 'unknown', 'incomplete_acceptance'
            if response.status_code == 429:
                return 'pending', 'rate_limited'
            if 400 <= response.status_code < 500 and response.status_code != 408:
                return 'failed', f'provider_{response.status_code}'
            return 'unknown', 'uncertain_provider_response'
    except requests.ConnectTimeout:
        return 'pending', 'connect_timeout'
    except requests.RequestException:
        return 'unknown', 'transport_uncertain'


def claim_deliveries():
    with transaction.atomic():
        database_budget()
        now = timezone.now()
        # A killed invocation may have submitted email before it disappeared.
        # Never automatically retry abandoned claims.
        StatusEmailDelivery.objects.filter(
            state='sending', claimed_at__lte=now - timedelta(seconds=LEASE_SECONDS),
        ).update(state='unknown', reason='interrupted_delivery', finished_at=now)
        rows = list(StatusEmailDelivery.objects.select_for_update().filter(
            state='pending', next_attempt_at__lte=now,
        ).select_related('history__faculty__user', 'recipient').order_by('created_at', 'pk')[:MAX_EMAILS])
        subscriptions = set(FacultyStatusSubscription.objects.filter(
            student_id__in=[r.recipient_id for r in rows],
            faculty_id__in=[r.history.faculty_id for r in rows],
        ).values_list('student_id', 'faculty_id'))
        claimed = []
        for row in rows:
            faculty_user = row.history.faculty.user
            valid = (
                row.recipient.is_active and row.recipient.account_status == 'active'
                and row.recipient.role == 'student' and row.recipient.email == row.email
                and faculty_user.is_active and faculty_user.account_status == 'active'
                and faculty_user.role == 'faculty'
                and (row.recipient_id, row.history.faculty_id) in subscriptions
            )
            if not valid:
                row.state, row.reason, row.finished_at = 'cancelled', 'recipient_no_longer_eligible', now
            else:
                row.state, row.claimed_at = 'sending', now
                row.attempts += 1
                claimed.append(row)
        StatusEmailDelivery.objects.bulk_update(rows, ['state', 'reason', 'finished_at', 'claimed_at', 'attempts'])
        return claimed


def run_status_scheduler():
    start = monotonic()
    token = acquire_lease()
    if not token:
        return {'skipped': 'already_running'}
    result = {'checked': 0, 'changed': 0, 'check_errors': 0, 'email_claimed': 0}
    try:
        cursor = StatusSchedulerState.objects.get(pk='automatic-status').faculty_cursor
        eligible = FacultyProfile.objects.filter(
            user__role='faculty', user__account_status='active', user__is_active=True,
        ).filter(Q(manual_status_override=False) | Q(manual_status_expires_at__lte=timezone.now()))
        profiles = list(eligible.filter(pk__gt=cursor).order_by('pk')[:MAX_FACULTY])
        if not profiles:
            profiles = list(eligible.order_by('pk')[:MAX_FACULTY])
        for profile in profiles:
            if monotonic() - start >= 10:
                break
            try:
                with transaction.atomic():
                    database_budget()
                    before = profile.current_status
                    refresh_faculty_status(profile)
                    result['changed'] += int(before != profile.current_status)
                    result['checked'] += 1
            except Exception:
                result['check_errors'] += 1
                logger.warning('Scheduled status check failed; retry on a later cycle.')
            # Advance even on a failed profile so one bad record cannot starve others.
            StatusSchedulerState.objects.filter(pk='automatic-status', lease_token=token).update(faculty_cursor=profile.pk)
        if monotonic() - start < 15:
            rows = claim_deliveries()
            result['email_claimed'] = len(rows)
            if rows:
                state, reason = submit_batch(rows)
                now = timezone.now()
                with transaction.atomic():
                    database_budget()
                    for row in rows:
                        final_state = 'failed' if state == 'pending' and row.attempts >= 3 else state
                        row.state = final_state
                        row.reason = reason
                        row.next_attempt_at = now + timedelta(minutes=5 * row.attempts)
                        row.finished_at = None if final_state == 'pending' else now
                    StatusEmailDelivery.objects.bulk_update(rows, ['state', 'reason', 'next_attempt_at', 'finished_at'])
                result['email_outcome'] = state
                result['email_failed'] = sum(row.state == 'failed' for row in rows)
                result['email_unknown'] = sum(row.state == 'unknown' for row in rows)
        return result
    finally:
        StatusSchedulerState.objects.filter(pk='automatic-status', lease_token=token).update(
            lease_token='', lease_until=None, last_finished_at=timezone.now(),
        )
