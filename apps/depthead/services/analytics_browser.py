"""Deterministic presentation of existing metrics; no AI or stored conversation."""
from django.urls import reverse
from apps.core.chat_presentation import answer, date_label, date_range, duration, hour_range, quantity
from apps.core.department_updates import UPDATE_QUESTIONS, department_update_answer
from . import analytics
from .analytics_display import (
    student_reporting_period, peak_request_month, faculty_load_display, faculty_trends_display, consultation_topics_display,
)
from .schedule_availability import get_schedule_availability, SCHEDULE_COUNT_NOTE, SCHEDULE_RANK_NOTE


ANALYTICS_QUESTIONS = {
    'daily_faculty': ('Schedules', 'Which faculty have the most open schedule time each day this week?'),
    'daily_availability': ('Schedules', 'How many faculty have at least two consecutive hours of open schedule time each day this week?'),
    'consultation_topics': ('Consultations', 'What consultation topics are most frequently requested?'),
    'peak_day': ('Consultations', 'Which weekday has the most completed consultations?'),
    'peak_hour': ('Consultations', 'What is the peak consultation hour?'),
    'faculty_load': ('Consultations', 'Which faculty receive the most requests?'),
    'capacity': ('Consultations', 'Can we measure the supply-demand gap?'),
    'completion_rates': ('Faculty', 'What are faculty consultation completion rates?'),
    'approval_times': ('Faculty', 'How long do faculty take to approve requests?'),
    'status_availability': ('Faculty', 'How much recorded time were faculty marked Available?'),
    'status_frequency': ('Faculty', 'How often are faculty status changes recorded?'),
    'peak_request_period': ('Students', 'Which month had the most submitted requests?'),
    'student_frequency': ('Students', 'Which students have requested the most consultations?'),
    **{key: ('Department updates', question) for key, question in UPDATE_QUESTIONS.items()},
}


def analytics_browser_answer(metric, college):
    if metric not in ANALYTICS_QUESTIONS:
        raise ValueError('Unknown analytics question')
    if metric in UPDATE_QUESTIONS:
        result = department_update_answer(metric, college, 'depthead', reverse('depthead:college_settings'))
        return dict(result, metric=metric, question=ANALYTICS_QUESTIONS[metric][1])
    period = analytics.normalize_period()
    dates = date_range(period.start_date, period.end_date)
    source = 'peak_analytics'
    lines = []
    paragraphs = False
    empty = ''
    if metric == 'capacity':
        analytics.get_capacity_capability()
        intro = ''
        lines = ['FacSync cannot reliably measure the consultation supply-demand gap yet.']
        note = 'Requests are recorded, but consultation slots and maximum capacity are not defined. Gaps in faculty schedules alone do not tell us how many consultations they can accommodate.'
        paragraphs = True
    elif metric in ('peak_hour', 'peak_day', 'faculty_load'):
        consultations = analytics.get_base_consultation_queryset(college, period)
        if metric == 'faculty_load':
            rows = faculty_load_display({'faculty_workload': analytics.get_faculty_workload(consultations)})
            intro = f'These faculty have the most consultation requests scheduled in your college for {dates}:'
            lines = [f"{row['name']} — {quantity(row['count'], 'request')}" for row in rows]
            note = 'Up to five faculty are shown. All request statuses are included, based on scheduled consultation dates.'
            empty = f'Your college has no consultation requests scheduled for {dates} to rank faculty by.'
        else:
            patterns = analytics.get_scheduled_consultation_patterns(consultations)
            if metric == 'peak_hour':
                peak = patterns['peak_hour']
                labels = [hour_range(hour) for hour in peak['hours']]
                intro = f'These are the busiest consultation start hours in your college for {dates}:'
                empty = f'Your college has no completed consultations with recorded start times for {dates}.'
            else:
                peak = patterns['peak_weekday']
                labels = peak['weekdays']
                intro = f'These weekdays have the most completed consultations in your college for {dates}:'
                empty = f'Your college has no completed consultations recorded for {dates}.'
            lines = [f"{label} — {quantity(peak['count'], 'completed consultation')}" for label in labels]
            note = 'This is based on the scheduled dates and start times of completed consultations. All tied peaks are shown.'
    elif metric in ('peak_request_period', 'student_frequency', 'consultation_topics'):
        source = 'student_behavior'
        months, today = student_reporting_period()
        period = analytics.normalize_period(months[0], today)
        dates = date_range(period.start_date, period.end_date)
        if metric == 'consultation_topics':
            summary = analytics.get_consultation_summary(analytics.get_base_consultation_queryset(college, period))
            rows = consultation_topics_display(summary)
            intro = f'Here are the consultation topics requested most often in your college, {dates}:'
            lines = [f"{row['label']} — {quantity(row['count'], 'request')} ({row['percentage']:.2f}%)" for row in rows]
            note = 'These are the topics students selected when booking. All request statuses are included, based on scheduled consultation dates.'
            empty = f'Your college has no consultation requests scheduled for {dates} to summarize by topic.'
        elif metric == 'peak_request_period':
            patterns = analytics.get_request_submission_patterns(college, period)
            label, count = peak_request_month(patterns['monthly_trend'])
            intro = f'Your college received the most consultation requests in these months, comparing {dates}:'
            lines = [f"{month} — {quantity(count, 'request')}" for month in label.split(', ')] if count else []
            note = 'This uses submission dates, not scheduled consultation dates. The current month and five preceding months are compared, with all tied months shown.'
            empty = f'No consultation requests were submitted in your college from {dates}.'
        else:
            rows = analytics.get_student_request_frequency_display(analytics.get_base_consultation_queryset(college, period))
            intro = f'These students have requested the most consultations with faculty in your college for {dates}:'
            lines = [f"{row['name']} — {quantity(row['count'], 'request')}" for row in rows]
            note = 'Up to ten students are shown. Counts include all request statuses and are based on scheduled consultation dates.'
            empty = f'No students have consultation requests scheduled in your college for {dates}.'
    elif metric in ('daily_faculty', 'daily_availability'):
        source = 'faculty_trends'
        data = get_schedule_availability(college)
        week = date_range(data['week_start'], data['week_end'])
        intro = (f'Here are the faculty in your college with the most open schedule time each day this week, {week}:'
                 if metric == 'daily_faculty' else f'Here is the schedule-based availability in your college for {week}:')
        if data['faculty_count']:
            for row in data['rows']:
                label = f"{row['day']}, {date_label(row['date'])}"
                if metric == 'daily_faculty':
                    value = (f"{', '.join(row['winners'])} — {duration(row['open_minutes'])}" + (' each' if len(row['winners']) > 1 else '')
                             if row['winners'] else ('No recorded schedules to compare' if row['ranking_empty'] == 'No recorded schedules' else 'No open schedule time'))
                else:
                    value = f"{row['available_count']} of {data['faculty_count']} faculty ({row['availability_percent']}%)"
                lines.append(f'{label}: {value}')
        note = SCHEDULE_RANK_NOTE if metric == 'daily_faculty' else SCHEDULE_COUNT_NOTE
        empty = 'There are no active faculty in your college to compare.'
    else:
        source = 'faculty_trends'
        data = analytics.get_faculty_trends(college)
        rows = faculty_trends_display(data)
        field, unit, missing = {
            'completion_rates': ('completion_rate', '%', 'No scheduled requests in this period'),
            'approval_times': ('avg_response_hours', ' hours', 'No recorded approvals in this period'),
            'status_availability': ('availability_rate', '%', 'No observed status history'),
            'status_frequency': ('updates_per_day', ' updates per day', 'No recorded status updates'),
        }[metric]
        for row in rows:
            value = f'{row[field]}{unit}' if row[field] is not None else missing
            if metric == 'status_frequency':
                value += f"; last recorded update: {row['last_update_display']}"
            lines.append(f"{row['name']} — {value}")
        if metric in ('status_frequency', 'status_availability'):
            dates = 'the last seven days (Asia/Manila)'
        else:
            dates = date_range(data['consultation_period']['start_date'], data['consultation_period']['end_date'])
        intro = {
            'status_frequency': f'Here is how often status changes were recorded for faculty in your college over {dates}:',
            'status_availability': f'Here is the share of observed time faculty in your college were marked Available over {dates}:',
            'completion_rates': f'Here are the faculty consultation completion rates in your college for {dates}:',
            'approval_times': f'Here is the average time faculty in your college took to approve requests scheduled for {dates}:',
        }[metric]
        note = {
            'status_frequency': 'The daily average is the number of status-history entries divided by seven. Entries are not necessarily manual updates. The last recorded update may predate this window.',
            'status_availability': 'This measures observed time in the Available status. It is not schedule-based availability or a prediction of future availability.',
            'completion_rates': 'Completed requests are divided by all requests scheduled in this period, including requests with other statuses.',
            'approval_times': 'This measures the average time from submission to recorded approval. Requests without recorded approval times are excluded.',
        }[metric]
        empty = 'There are no active faculty in your college to summarize.'
    source_label = {'peak_analytics': 'View peak analytics', 'student_behavior': 'View student behavior',
                    'faculty_trends': 'View faculty trends'}[source]
    result = answer(intro, lines, note, reverse(f'depthead:{source}'), source_label,
                    empty=empty, paragraphs=paragraphs)
    return dict(result, metric=metric, question=ANALYTICS_QUESTIONS[metric][1])
