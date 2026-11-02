"""Best-effort consultation email dispatch, separate from the booking response."""
import logging

from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse

from apps.faculty.constants import CONSULTATION_NOTE_MAX_LENGTH
from apps.faculty.models import ConsultationRequest
from .models import School
from .school_scope import require_school, school_scope
from .services import _send_html_email

logger = logging.getLogger(__name__)
TOPIC = 'facsync-consultation-emails'
EVENTS = {
    'requested': ('pending', 'New consultation request — FacSync', 'New consultation request',
                  'A student has requested a consultation. Review the request in FacSync to approve or decline it.'),
    'approved': ('approved', 'Your consultation was approved — FacSync', 'Consultation approved',
                 'Your faculty member approved your consultation. You can review the details in FacSync.'),
    'completed': ('completed', 'Your consultation is complete — FacSync', 'Consultation completed',
                  'Your faculty member marked your consultation as completed. You can review it in FacSync.'),
}


def _recipient(consultation, event):
    student, faculty = consultation.user, consultation.faculty.user
    school = require_school(student.school)
    if faculty.school_id != school.pk or student.role != 'student' or faculty.role != 'faculty':
        raise ValueError('Consultation participants do not match the school and roles.')
    recipient = faculty if event == 'requested' else student
    if any(not user.is_active or user.account_status != 'active' for user in (student, faculty)):
        return None
    return recipient if (recipient.email or '').strip() else None


def _publish(job):
    # Import lazily: an unavailable queue must not prevent Django from starting.
    from vercel.queue.sync import QueueClient
    queue = QueueClient(region=settings.CONSULTATION_EMAIL_QUEUE_REGION, timeout=2)
    return queue.send(TOPIC, job, retention=86400,
                      idempotency_key=f"consultation:{job['request_id']}:{job['event']}")


def queue_consultation_email(consultation, event):
    """Schedule IDs only after commit. Never send email or raise into a view."""
    safe_event = event if isinstance(event, str) and event in EVENTS else 'unknown'
    try:
        if safe_event == 'unknown':
            raise ValueError('Unknown consultation email event.')
        if _recipient(consultation, event) is None:
            return
        if not settings.CONSULTATION_EMAILS_ENABLED:
            logger.info('consultation_email_skipped event=%s reason=disabled', event)
            return
        job = {'request_id': consultation.pk, 'school_id': consultation.user.school_id, 'event': event}

        def publish():
            try:
                _publish(job)
            except Exception as error:
                # Never print addresses, student notes, backend responses or secrets.
                logger.warning('consultation_email_dispatch_failed request=%s event=%s category=%s',
                               consultation.pk, event, type(error).__name__)

        transaction.on_commit(publish, robust=True)
    except Exception as error:
        logger.warning('consultation_email_dispatch_failed request=%s event=%s category=%s',
                       consultation.pk, safe_event, type(error).__name__)


def send_consultation_email(job):
    """Re-fetch participants under explicit school scope before sending once."""
    try:
        if (not isinstance(job, dict) or set(job) != {'request_id', 'school_id', 'event'}
                or job.get('event') not in EVENTS or type(job.get('school_id')) is not int
                or not isinstance(job.get('request_id'), str) or len(job['request_id']) > 64):
            raise ValueError('Invalid consultation email job.')
        event = job['event']
        school = School.objects.filter(pk=job['school_id'], is_active=True).first()
        if school is None or not settings.CONSULTATION_EMAILS_ENABLED:
            return False
        with school_scope(school):
            consultation = ConsultationRequest.objects.select_related('user__school', 'faculty__user__school').filter(
                pk=job['request_id'],
            ).first()
            if consultation is None or consultation.status != EVENTS[event][0]:
                return False  # Removed or superseded requests must not send stale messages.
            recipient = _recipient(consultation, event)
            if recipient is None:
                return False
            requested = event == 'requested'
            context = {
                'heading': EVENTS[event][2], 'intro': EVENTS[event][3],
                'name': recipient.get_full_name() or recipient.username,
                'student_name': consultation.user.get_full_name() or consultation.user.username,
                'faculty_name': consultation.faculty.user.get_full_name() or consultation.faculty.user.username,
                'agenda': consultation.get_agenda_display(),
                'consultation_type': consultation.get_consultation_type_display(),
                'date': consultation.date, 'start_time': consultation.start_time, 'end_time': consultation.end_time,
                'timezone': settings.GOOGLE_CALENDAR_TIME_ZONE,
                'message_label': 'Student message' if requested else 'Faculty note',
                'message': (consultation.student_message if requested else consultation.faculty_note)[:CONSULTATION_NOTE_MAX_LENGTH],
                'show_empty_message': requested,
                'button_label': 'View in dashboard' if requested else 'View consultation',
                'button_url': settings.SITE_URL.rstrip('/') + reverse(
                    'faculty:dashboard' if requested else 'students:consultation_requests'),
            }
            # HTML autoescaping stays enabled; the text alternative includes the URL.
            text = render_to_string('emails/consultation_notification.txt', context)
            if not _send_html_email(EVENTS[event][1], 'consultation_notification.html', context,
                                    [recipient.email.strip()], text_content=text):
                raise RuntimeError('Email backend did not accept the message.')
            return True
    except Exception as error:
        logger.warning('consultation_email_delivery_failed category=%s', type(error).__name__)
        return False  # No blind retries after an uncertain provider acceptance.
