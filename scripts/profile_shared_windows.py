"""Read-only real-database endpoint profile; no login/session persistence."""
import json
import os
import statistics
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
import django
django.setup()

from django.conf import settings
from django.contrib.auth import SESSION_KEY, BACKEND_SESSION_KEY, HASH_SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore
from django.db import connection
from django.db.models import Count
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from apps.core.models import User
from apps.faculty.models import FacultyProfile
from apps.depthead.services.shared_windows import planning_week
from apps.depthead.services.analytics import _eligible_faculty
from apps.faculty.services.schedule_conflicts import eligible_schedule_events


def read_only(execute, sql, params, many, context):
    if not sql.lstrip().upper().startswith(('SELECT', 'SHOW', 'SET')):
        raise RuntimeError('Profiling blocked a non-read-only statement.')
    return execute(sql, params, many, context)


def main():
    with connection.execute_wrapper(read_only):
        roster_counts = {
            (row['user__school_id'], row['college_id'].casefold()): row['total']
            for row in FacultyProfile.objects.filter(user__role='faculty', user__account_status='active')
            .values('user__school_id', 'college_id').annotate(total=Count('pk'))
        }
        heads = list(User.objects.filter(role='depthead', account_status='active', school__is_active=True).exclude(college=''))
        user = max(heads, key=lambda head: roster_counts.get((head.school_id, head.college.casefold()), 0), default=None)
        if user is None:
            raise RuntimeError('No active College Head account exists for profiling.')
        week = planning_week()
        day = week['week_end'] if week['ended'] else week['today']
        faculty = _eligible_faculty(user.college, school=user.school)
        roster_count = faculty.count()
        event_count = eligible_schedule_events().filter(faculty__in=faculty).count()
        session = {SESSION_KEY: str(user.pk),
                   BACKEND_SESSION_KEY: 'django.contrib.auth.backends.ModelBackend',
                   HASH_SESSION_KEY: user.get_session_auth_hash()}
        client = Client(HTTP_HOST='localhost')
        client.cookies[settings.SESSION_COOKIE_NAME] = 'a' * 32
        runs = []
        with patch.object(SessionStore, 'load', return_value=session):
            for index in range(5):
                with CaptureQueriesContext(connection) as queries:
                    started = time.perf_counter()
                    response = client.get(reverse('depthead:shared_windows_api'),
                                          {'date': day.isoformat(), 'duration': '120'})
                    wall_ms = (time.perf_counter() - started) * 1000
                if response.status_code != 200:
                    raise RuntimeError(f'Endpoint returned HTTP {response.status_code}.')
                runs.append({'run': index + 1, 'query_count': len(queries),
                             'sql_ms': round(sum(float(q['time']) for q in queries) * 1000, 2),
                             'endpoint_ms': round(wall_ms, 2)})
        print(json.dumps({
            'database': connection.vendor, 'college': user.college,
            'date': day.isoformat(), 'duration_minutes': 120,
            'active_faculty': roster_count, 'eligible_schedule_events': event_count,
            'runs': runs, 'warm_median_ms': round(statistics.median(r['endpoint_ms'] for r in runs[1:]), 2),
            'note': 'Real database and normal request middleware. Session loaded in memory; login/session writes and session lookup excluded. Authentication queries included. First request includes initialization.',
        }, indent=2))


if __name__ == '__main__':
    main()
