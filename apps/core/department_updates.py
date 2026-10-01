"""Read-only department notices, restricted by college and recipient role."""
from django.utils import timezone
from .models import CollegeAnnouncement, OfficeClosure

UPDATE_QUESTIONS = {
    'active_announcements': 'What announcements are currently active in my college?',
    'college_closure': 'Is my college currently open or closed?',
}


def department_update_answer(metric, college, role, source_url):
    if metric not in UPDATE_QUESTIONS or role not in ('student', 'faculty', 'depthead'):
        raise ValueError('Unsupported department update')
    if not str(college or '').strip():
        raise ValueError('College is required')
    if metric == 'active_announcements':
        audiences = {'student': ('students', 'both'), 'faculty': ('faculty', 'both'),
                     'depthead': ('students', 'faculty', 'both')}[role]
        announcements = CollegeAnnouncement.objects.filter(
            college__iexact=college, expiry__gt=timezone.now(), audience__in=audiences,
        ).order_by('-posted_at', '-pk')
        def stamp(value):
            return timezone.localtime(value).strftime('%b %d, %Y %I:%M %p %Z')
        lines = [f'{item.message} | Audience: {item.get_audience_display()} | Posted: {stamp(item.posted_at)} | Expires: {stamp(item.expiry)}'
                 for item in announcements]
        lines = lines or ['No active announcements for your audience in this college.']
        period = 'Currently active college announcements'
        note = 'Newest first. Only unexpired announcements for your college and audience are shown.'
    else:
        closure = OfficeClosure.objects.filter(college__iexact=college).first()
        closed = bool(closure and closure.is_closed)
        lines = ['College status: ' + ('Closed' if closed else 'Open')]
        if closure:
            lines.extend([f'Reason: {closure.reason or "Not provided"}',
                          f'Recorded closure start: {closure.closure_start or "Not specified"}',
                          f'Recorded closure end: {closure.closure_end or "Not specified"}'])
        else:
            lines.append('No closure record is configured.')
        period = 'Current college closure status'
        note = 'Status follows the saved open/closed setting. Recorded dates do not automatically change it.'
    return {'period': period, 'lines': lines, 'note': note, 'source_url': source_url,
            'source_label': 'View college settings' if role == 'depthead' else 'View dashboard'}
