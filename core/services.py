from django.utils import timezone
from .models import DepartmentAnnouncement, Notification, User
from django.core.mail import send_mail
from django.conf import settings

def send_faculty_invite_email(email, department):
    send_mail(
        "You've been invited to FacSync",
        f"You've been pre-registered as faculty for {department}. Sign in with Google using this email to activate your account.",
        settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False,
    )

def send_faculty_approved_email(user):
    send_mail(
        "Your FacSync faculty account is approved",
        "Your faculty account request has been approved. You can now log in.",
        settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False,
    )

def send_faculty_removed_email(email, name):
    send_mail(
        "Your FacSync faculty account was removed",
        f"Hi {name}, your faculty account has been removed by your Department Head.",
        settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False,
    )


def create_notification(recipient, notification_type, title, message, url=''):
    return Notification.objects.create(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        message=message,
        url=url,
    )


def notify_department_users(department, notification_type, title, message, url='', exclude_user_id=None):
    recipients = User.objects.filter(
        department=department,
        role__in=('student', 'faculty'),
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
    from students.models import FacultyStatusSubscription

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

def get_active_announcements(department=None):
    qs = DepartmentAnnouncement.objects.filter(expiry__gt=timezone.now())
    if department:
        qs = qs.filter(department=department)
    return [
        {
            'department': a.get_department_display(),
            'message': a.message,
            'posted_at': a.posted_at.strftime('%b %d, %Y'),
        }
        for a in qs
    ]

def send_faculty_invite_email(email, department):
    send_mail(
        "You've been invited to FacSync",
        f"You've been pre-registered as faculty for {department}. Sign in with Google using this email to activate your account.",
        settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False,
    )

def send_faculty_approved_email(user):
    send_mail(
        "Your FacSync faculty account is approved",
        "Your faculty account request has been approved. You can now log in.",
        settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False,
    )

def send_faculty_removed_email(email, name):
    send_mail(
        "Your FacSync faculty account was removed",
        f"Hi {name}, your faculty account has been removed by your Department Head.",
        settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False,
    )
