"""Preset answers restricted to the authenticated faculty member's own records."""
from django.urls import reverse
from apps.core.department_updates import UPDATE_QUESTIONS, department_update_answer
from apps.depthead.services import analytics
from apps.depthead.services.analytics_display import (
    student_reporting_period, peak_request_month, consultation_topics_display,
)

QUESTIONS = {
    'peak_hour': ('Consultations', 'What is the peak consultation hour?'),
    'peak_day': ('Consultations', 'What is the peak consultation day?'),
    'consultation_topics': ('Consultations', 'What consultation topics are most frequently requested?'),
    'peak_request_period': ('Students', 'Which month had the most submitted requests?'),
    'student_frequency': ('Students', 'Which students submit the most requests?'),
    **{key: ('Department updates', question) for key, question in UPDATE_QUESTIONS.items()},
}


def consultation_browser_answer(metric, faculty):
    if metric not in QUESTIONS:
        raise ValueError('Unknown consultation question')
    college = faculty.college_id
    if metric in UPDATE_QUESTIONS:
        return department_update_answer(metric, college, 'faculty', reverse('faculty:dashboard'))
    period = analytics.normalize_period()
    if metric in ('consultation_topics', 'peak_request_period', 'student_frequency'):
        months, today = student_reporting_period()
        period = analytics.normalize_period(months[0], today)
    # Ownership is enforced before any aggregation, never supplied by the browser.
    consultations = analytics.get_base_consultation_queryset(college, period).filter(faculty=faculty)
    if metric in ('peak_hour', 'peak_day'):
        patterns = analytics.get_scheduled_consultation_patterns(consultations)
        if metric == 'peak_hour':
            peak = patterns['peak_hour']
            labels = [f"{hour % 12 or 12}{'AM' if hour < 12 else 'PM'}" for hour in peak['hours']]
        else:
            peak = patterns['peak_weekday']
            labels = peak['weekdays']
        lines = [f"{label}: {peak['count']} completed consultations" for label in labels]
        note = 'Your completed consultations only, using scheduled dates and start times. All tied peaks are shown.'
    elif metric == 'consultation_topics':
        rows = consultation_topics_display(analytics.get_consultation_summary(consultations))
        lines = [f"{row['label']}: {row['count']} requests ({row['percentage']:.2f}%)" for row in rows]
        note = 'Your requests only, all statuses; topics selected when booking. Based on scheduled dates.'
    elif metric == 'peak_request_period':
        patterns = analytics.get_request_submission_patterns(college, period, faculty=faculty)
        label, count = peak_request_month(patterns['monthly_trend'])
        lines = [f'{label}: {count} submitted requests'] if count else []
        note = 'Requests submitted to you, using submission dates across the current and five preceding months. All ties included.'
    else:
        rows = analytics.get_student_request_frequency_display(consultations)
        lines = [f"{row['name']}: {row['count']} requests" for row in rows]
        note = 'Top ten students requesting consultations with you only. Based on scheduled dates, all request statuses.'
    return {'period': f'Your consultations: {period.start_date} to {period.end_date} ({period.timezone_name})',
            'lines': lines or ['No data for this reporting period.'], 'note': note,
            'source_url': reverse('faculty:booking_management'), 'source_label': 'View your consultations'}
