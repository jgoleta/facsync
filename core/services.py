from django.utils import timezone
from .models import DepartmentAnnouncement

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