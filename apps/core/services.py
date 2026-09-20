import logging
from .colleges import get_college_label
from django.utils import timezone
from .models import CollegeAnnouncement, Notification, User
from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.urls import reverse


def create_notification(recipient, notification_type, title, message, url=''):
    return Notification.objects.create(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        message=message,
        url=url,
    )


def notify_college_users(college, notification_type, title, message, url='', exclude_user_id=None, roles=('student', 'faculty')):
    recipients = User.objects.filter(
        college=college,
        role__in=roles,
        account_status='active',
    )
    if exclude_user_id:
        recipients = recipients.exclude(pk=exclude_user_id)
    return Notification.objects.bulk_create([
        Notification(
            recipient=recipient,
            notification_type=notification_type,
            title=title,
            message=message,
            url=url,
        )
        for recipient in recipients
    ])


def notify_faculty_status_subscribers(faculty, status):
    """Create an in-app notification and send an email for students following a faculty member."""
    from apps.students.models import FacultyStatusSubscription

    status_label = dict(faculty.STATUS_CHOICES).get(status, status)
    faculty_name = faculty.user.get_full_name() or faculty.user.username
    url = f'/student/view-schedule/?faculty_id={faculty.faculty_id}'
    subscriptions = FacultyStatusSubscription.objects.filter(
        faculty=faculty,
    ).select_related('student')

    notifications = Notification.objects.bulk_create([
        Notification(
            recipient=subscription.student,
            notification_type='faculty_status_update',
            title='Faculty status updated',
            message=f'{faculty_name} is now {status_label}.',
            url=url,
        )
        for subscription in subscriptions
    ])

    for subscription in subscriptions:
        if subscription.student.email:
            try:
                send_faculty_status_email(subscription.student, faculty_name, status_label, url)
            except Exception:
                pass  #change status regardless if the email notification is successful or not

    return notifications


def send_faculty_status_email(student, faculty_name, status_label, url):
    send_mail(
        f"{faculty_name} is now {status_label}",
        f"Hi {student.get_full_name() or student.username},\n\n"
        f"{faculty_name}, a faculty member you're following on FacSync, is now {status_label}.\n\n"
        f"View their schedule: {settings.SITE_URL}{url}",
        settings.DEFAULT_FROM_EMAIL, [student.email], fail_silently=True,
    )

def active_announcement_queryset(college=None, *, audience='both'):
    audiences = {'faculty': ('faculty', 'both'), 'students': ('students', 'both'), 'both': ('both',)}
    qs = CollegeAnnouncement.objects.filter(
        expiry__gt=timezone.now(), audience__in=audiences[audience],
    )
    if audience != 'both' and not college:
        return qs.none()
    if college is not None:
        qs = qs.filter(college__iexact=college)
    return qs


def get_active_announcements(college=None, *, audience='both'):
    qs = active_announcement_queryset(college, audience=audience)
    return [
        {
            'college': a.get_college_display(),
            'message': a.message,
            'posted_at': a.posted_at.strftime('%b %d, %Y'),
        }
        for a in qs
    ]

def _send_html_email(subject, template_name, context, recipient_list, fail_silently=False):
    context['site_url'] = settings.SITE_URL
    html_content = render_to_string(f'emails/{template_name}', context)
    text_content = strip_tags(html_content)
    msg = EmailMultiAlternatives(subject, text_content, settings.DEFAULT_FROM_EMAIL, recipient_list)
    msg.attach_alternative(html_content, "text/html")
    return msg.send(fail_silently=fail_silently)


def send_schedule_uploaded_email(faculty_user, uploaded_events, uploaded_by):
    """Notify the recipient about only the newly saved College Head upload."""
    email = (faculty_user.email or '').strip()
    if not email:
        return False
    entries = []
    for event in uploaded_events:
        start_date = event.recurrence_start_date or event.date
        end_date = event.recurrence_end_date or event.date or start_date
        entries.append({
            'event': event,
            'start_date': start_date,
            'end_date': end_date if end_date != start_date else None,
        })
    return bool(_send_html_email(
        'Your College Head uploaded your schedule — FacSync',
        'schedule_uploaded.html',
        {
            'name': faculty_user.get_full_name() or faculty_user.username,
            'uploader_name': uploaded_by.get_full_name() or uploaded_by.username,
            'entries': entries,
            'entry_count': len(entries),
            'schedule_url': settings.SITE_URL.rstrip('/') + reverse('faculty:schedule'),
        },
        [email],
    ))


def send_faculty_invite_email(email, college):
    _send_html_email(
        "You've been invited to FacSync",
        'faculty_invite.html',
        {'college': college},
        [email],
    )


def send_faculty_removed_email(email, name):
    _send_html_email(
        "Your FacSync faculty account was removed",
        'faculty_removed.html',
        {'name': name},
        [email],
    )


def send_faculty_status_email(student, faculty_name, status_label, url):
    _send_html_email(
        f"{faculty_name} is now {status_label}",
        'faculty_status_update.html',
        {
            'student_name': student.get_full_name() or student.username,
            'faculty_name': faculty_name,
            'status_label': status_label,
            'url': url,
        },
        [student.email],
        fail_silently=True,
    )

def send_depthead_invite_email(email, college, title):
    title_label = dict(User.TITLE_CHOICES).get(title, 'College Head')
    _send_html_email(
        "You've been invited to FacSync",
        'depthead_invite.html',
        {'college': college, 'title_label': title_label},
        [email],
    )


def send_depthead_deactivated_email(user):
    _send_html_email(
        "Your FacSync College Head account was deactivated",
        'depthead_deactivated.html',
        {'name': user.get_full_name() or user.username},
        [user.email],
    )

logger = logging.getLogger(__name__)


def _email_college_faculty(college, subject, template, context):
    if not college:
        return
    recipients = User.objects.filter(
        role='faculty', account_status='active', college__iexact=college,
    ).exclude(email='')
    for faculty in recipients:
        if not faculty.email.strip():
            continue
        try:
            _send_html_email(subject, template, {
                **context, 'name': faculty.get_full_name() or faculty.username,
                'college': get_college_label(college),
            }, [faculty.email])
        except Exception:
            logger.exception('Failed to send %s to faculty %s', template, faculty.pk)


def send_announcement_email_to_faculty(announcement):
    if announcement.audience not in ('faculty', 'both'):
        return
    _email_college_faculty(
        announcement.college, 'New college announcement', 'college_announcement.html',
        {'message': announcement.message, 'expiry': announcement.expiry},
    )


def send_closure_email_to_faculty(closure):
    if not closure.is_closed:
        return
    _email_college_faculty(
        closure.college, 'College closed for new consultation requests', 'college_closure.html',
        {'reason': closure.reason, 'closure_start': closure.closure_start, 'closure_end': closure.closure_end},
    )
