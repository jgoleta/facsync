"""Deterministic presentation of existing metrics; no AI or stored conversation."""
from django.urls import reverse
from . import analytics
from .analytics_display import (
    student_reporting_period, peak_request_month, faculty_load_display, faculty_trends_display,
)
from .schedule_availability import get_schedule_availability


ANALYTICS_QUESTIONS = {
    'peak_hour': ('Consultations', 'What is the peak consultation hour?'),
    'peak_day': ('Consultations', 'What is the peak consultation day?'),
    'capacity': ('Consultations', 'Can we measure the supply-demand gap?'),
    'faculty_load': ('Consultations', 'Which faculty receive the most requests?'),
    'status_frequency': ('Faculty', 'How often do faculty update their status?'),
    'completion_rates': ('Faculty', 'What are faculty consultation completion rates?'),
    'approval_times': ('Faculty', 'How long do faculty take to approve requests?'),
    'status_availability': ('Faculty', 'What are faculty status availability rates?'),
    'peak_request_period': ('Students', 'Which month had the most submitted requests?'),
    'student_frequency': ('Students', 'Which students submit the most requests?'),
    'daily_faculty': ('Schedules', 'Who has the most open schedule time each day?'),
    'daily_availability': ('Schedules', 'How much schedule availability is there each day?'),
}


def analytics_browser_answer(metric, college):
    period = analytics.normalize_period()
    period_label = f'Month-to-date: {period.start_date} to {period.end_date} ({period.timezone_name})'
    source = 'peak_analytics'
    lines = []
    note = ''
    if metric == 'capacity':
        capacity = analytics.get_capacity_capability()
        if not capacity['authoritatively_calculable']:
            lines = ['The supply-demand gap is not currently measurable.']
            note = 'Consultation slots and maximum consultation capacity are not defined. Recorded schedule gaps alone cannot establish how many consultations faculty can accommodate.'
        period_label = 'Current data capability'
    elif metric in ('peak_hour', 'peak_day', 'faculty_load'):
        consultations = analytics.get_base_consultation_queryset(college, period)
        if metric == 'faculty_load':
            rows = faculty_load_display({'faculty_workload': analytics.get_faculty_workload(consultations)})
            lines = [f"{row['name']}: {row['count']} requests" for row in rows]
            note = 'Top five faculty by requests across all request statuses.'
        else:
            patterns = analytics.get_scheduled_consultation_patterns(consultations)
            if metric == 'peak_hour':
                peak = patterns['peak_hour']
                labels = [f"{hour % 12 or 12}{'AM' if hour < 12 else 'PM'}" for hour in peak['hours']]
            else:
                peak = patterns['peak_weekday']
                labels = peak['weekdays']
            lines = [f"{label}: {peak['count']} completed consultations" for label in labels]
            note = 'Based on scheduled dates and times of completed consultations. All tied peaks are shown.'
    elif metric in ('peak_request_period', 'student_frequency'):
        source = 'student_behavior'
        months, today = student_reporting_period()
        period = analytics.normalize_period(months[0], today)
        period_label = f'{period.start_date} to {period.end_date} ({period.timezone_name})'
        if metric == 'peak_request_period':
            patterns = analytics.get_request_submission_patterns(college, period)
            label, count = peak_request_month(patterns['monthly_trend'])
            lines = [f'{label}: {count} submitted requests'] if count else []
            note = 'Peak submission month across the current month and five preceding months; ties included.'
        else:
            rows = analytics.get_student_request_frequency_display(analytics.get_base_consultation_queryset(college, period))
            lines = [f"{row['name']}: {row['count']} requests" for row in rows]
            note = 'Top ten students, based on scheduled consultation dates in this six-month range.'
    elif metric in ('daily_faculty', 'daily_availability'):
        source = 'faculty_trends'
        data = get_schedule_availability(college)
        period_label = f"This week: {data['week_start']} to {data['week_end']} ({data['timezone']}); 8am-5pm"
        for row in data['rows']:
            label = f"{row['day']} ({row['date']})"
            if not data['faculty_count']:
                value = 'No faculty data'
            elif metric == 'daily_faculty':
                value = f"{', '.join(row['winners'])}: {row['open_display']} open" if row['winners'] else row['ranking_empty']
            else:
                value = f"{row['availability_percent']}% ({row['available_count']} of {data['faculty_count']} faculty)"
            lines.append(f'{label}: {value}')
        note = ('Ranked by total open time; all ties shown. Faculty without recorded schedules are excluded.'
                if metric == 'daily_faculty' else
                'Based on recorded schedules: at least 60 consecutive minutes free. Faculty without records count as fully unscheduled. Free time does not guarantee availability.')
    else:
        source = 'faculty_trends'
        data = analytics.get_faculty_trends(college)
        rows = faculty_trends_display(data)
        field, unit = {
            'completion_rates': ('completion_rate', '%'),
            'approval_times': ('avg_response_hours', ' hours'),
            'status_availability': ('availability_rate', '%'),
            'status_frequency': ('updates_per_day', ' updates/day'),
        }[metric]
        for row in rows:
            value = f'{row[field]}{unit}' if row[field] is not None else 'No data'
            if metric == 'status_frequency':
                value += f"; last recorded update: {row['last_update_display']}"
            lines.append(f"{row['name']}: {value}")
        if metric in ('status_frequency', 'status_availability'):
            period_label = 'Rolling last 7 days (Asia/Manila)'
        else:
            period_label = f"Month-to-date: {data['consultation_period']['start_date']} to {data['consultation_period']['end_date']} (Asia/Manila)"
        note = {
            'status_frequency': 'Status-history updates divided by seven. The last recorded update may predate this window.',
            'status_availability': 'Observed time in the Available status; this is not schedule-based availability.',
            'completion_rates': 'Completed requests divided by all requests scheduled in the reporting period.',
            'approval_times': 'Average time from submission to recorded approval for requests scheduled in the reporting period.',
        }[metric]
    return {'metric': metric, 'question': ANALYTICS_QUESTIONS[metric][1],
            'period': period_label, 'lines': lines or ['No data for this reporting period.'],
            'note': note, 'source_url': reverse(f'depthead:{source}')}
