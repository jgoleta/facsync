"""Read-only department notices, restricted by college and recipient role."""
from django.utils import timezone
from .models import CollegeAnnouncement, OfficeClosure
from .chat_presentation import answer, date_label

UPDATE_QUESTIONS = {
    'active_announcements': 'What announcements are currently active in my college?',
    'college_closure': 'Is my college currently open or closed?',
}


def department_update_answer(metric, college, role, source_url):
    if metric not in UPDATE_QUESTIONS or role not in ('student', 'faculty', 'depthead'):
        raise ValueError('Unsupported department update')
    if not str(college or '').strip():
        raise ValueError('College is required')
    source_label = {'student': 'View faculty directory', 'faculty': 'View faculty dashboard',
                    'depthead': 'View college settings'}[role]
    if metric == 'active_announcements':
        audiences = {'student': ('students', 'both'), 'faculty': ('faculty', 'both'),
                     'depthead': ('students', 'faculty', 'both')}[role]
        announcements = CollegeAnnouncement.objects.filter(
            college__iexact=college, expiry__gt=timezone.now(), audience__in=audiences,
        ).order_by('-posted_at', '-pk')
        def stamp(value):
            value = timezone.localtime(value)
            return f'{date_label(value)}, {value:%I:%M %p} ({timezone.get_current_timezone_name()})'
        blocks = [{'message': item.message, 'details': [
            f'For: {item.get_audience_display()}', f'Posted: {stamp(item.posted_at)}',
            f'Expires: {stamp(item.expiry)}',
        ]} for item in announcements]
        audience = {'student': ' for students', 'faculty': ' for faculty', 'depthead': ''}[role]
        result = answer(f'Here are the active announcements{audience} in your college, newest first:',
                        [block['message'] for block in blocks], '', source_url, source_label,
                        empty=f'There are no active announcements{audience} in your college right now.')
        if blocks:
            result['announcements'] = blocks
        return result
    else:
        closure = OfficeClosure.objects.filter(college__iexact=college).first()
        if not closure:
            return answer('', ['No college closure is currently recorded.'],
                          'Individual faculty availability may vary. Check with your college before visiting.',
                          source_url, source_label, paragraphs=True)
        if not closure.is_closed:
            return answer('', ['Your college is currently marked as open.'],
                          'Individual faculty availability may vary. Check the faculty directory before visiting.'
                          if role == 'student' else 'Individual faculty availability may vary.',
                          source_url, source_label, paragraphs=True)
        lines = [f'Reason: {closure.reason or "No reason has been provided."}',
                 f'Recorded closure start: {date_label(closure.closure_start) if closure.closure_start else "Not specified"}',
                 f'Recorded closure end: {date_label(closure.closure_end) if closure.closure_end else "Not specified"}']
        return answer('Your college is currently marked as closed.', lines,
                      'The college remains marked as closed until an administrator updates its status. Recorded dates do not automatically change it.',
                      source_url, source_label, paragraphs=True)
