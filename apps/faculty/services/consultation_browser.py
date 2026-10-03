"""Preset answers restricted to the authenticated faculty member's own records."""
from django.urls import reverse
from apps.core.chat_presentation import answer, date_range, hour_range, quantity
from apps.core.department_updates import UPDATE_QUESTIONS, department_update_answer
from apps.depthead.services import analytics
from apps.depthead.services.analytics_display import (
    student_reporting_period, peak_request_month, consultation_topics_display,
)

QUESTIONS = {
    'peak_hour': ('Consultations', 'What is the peak consultation hour?'),
    'peak_day': ('Consultations', 'Which weekday has the most completed consultations?'),
    'consultation_topics': ('Consultations', 'What consultation topics are most frequently requested?'),
    'peak_request_period': ('Students', 'Which month had the most submitted requests?'),
    'student_frequency': ('Students', 'Which students have requested the most consultations with me?'),
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
    dates = date_range(period.start_date, period.end_date)
    # Ownership is enforced before any aggregation, never supplied by the browser.
    consultations = analytics.get_base_consultation_queryset(college, period).filter(faculty=faculty)
    if metric in ('peak_hour', 'peak_day'):
        patterns = analytics.get_scheduled_consultation_patterns(consultations)
        if metric == 'peak_hour':
            peak = patterns['peak_hour']
            labels = [hour_range(hour) for hour in peak['hours']]
            intro = f'Your busiest consultation start hours for {dates} are:'
            empty = f'You have no completed consultations with recorded start times for {dates}.'
        else:
            peak = patterns['peak_weekday']
            labels = peak['weekdays']
            intro = f'Your busiest consultation weekdays for {dates} are:'
            empty = f'You have no completed consultations recorded for {dates}.'
        lines = [f"{label} — {quantity(peak['count'], 'completed consultation')}" for label in labels]
        note = 'This is based on the scheduled dates and start times of your completed consultations. All tied peaks are shown.'
    elif metric == 'consultation_topics':
        rows = consultation_topics_display(analytics.get_consultation_summary(consultations))
        intro = f'Here are the consultation topics students requested from you most often, {dates}:'
        lines = [f"{row['label']} — {quantity(row['count'], 'request')} ({row['percentage']:.2f}%)" for row in rows]
        empty = f'You have no consultation requests scheduled for {dates} to summarize by topic.'
        note = 'These are the topics students selected when booking. All request statuses are included, based on scheduled consultation dates.'
    elif metric == 'peak_request_period':
        patterns = analytics.get_request_submission_patterns(college, period, faculty=faculty)
        label, count = peak_request_month(patterns['monthly_trend'])
        intro = f'You received the most consultation requests in these months, comparing {dates}:'
        lines = [f"{month} — {quantity(count, 'request')}" for month in label.split(', ')] if count else []
        empty = f'No consultation requests were submitted to you from {dates}.'
        note = 'This uses the submission date, not the scheduled consultation date. The current month and five preceding months are compared, with all tied months shown.'
    else:
        rows = analytics.get_student_request_frequency_display(consultations)
        intro = f'These students have requested the most consultations with you for {dates}:'
        lines = [f"{row['name']} — {quantity(row['count'], 'request')}" for row in rows]
        empty = f'No students have consultation requests scheduled with you for {dates}.'
        note = 'Up to ten students are shown. Counts include all request statuses and are based on scheduled consultation dates.'
    return answer(intro, lines, note, reverse('faculty:dashboard') + '#consultation-requests',
                  'View your consultations', empty=empty)
