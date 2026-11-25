"""Explicit command-line preview and confirmation of a shared test batch."""
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction
from django.utils import timezone
from dotenv import dotenv_values

from apps.core.models import School, User
from apps.core.school_scope import school_scope
from apps.faculty.services.test_requests import TestRequestBuilder, TASKS, ZONE, WEEKDAYS


class Command(TestRequestBuilder, BaseCommand):
    help = 'Preview and confirm four face-to-face testing requests for one faculty; no creation emails.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True, help='Exact invited faculty email address.')
        parser.add_argument('--database-target', required=True, choices=('production', 'rehearsal'))
        parser.add_argument('--dry-run', action='store_true', help='Preview only; create no test records.')
        parser.add_argument('--start-date', type=date.fromisoformat, help='First candidate date, YYYY-MM-DD; default tomorrow in Manila.')
        parser.add_argument('--days', type=int, default=21, help='Search window in days (1-30; default 21).')
        parser.add_argument('--weekdays', nargs='+', choices=tuple(WEEKDAYS),
                            help='Allowed weekdays, e.g. --weekdays tue thu; default Monday-Saturday.')
        parser.add_argument('--start-time', type=time.fromisoformat,
                            help='One candidate start per allowed date, in Philippine time, e.g. 15:30.')
        parser.add_argument('--duration', type=int, default=60,
                            help='Minutes per request, 15-120 in 15-minute increments; default 60.')

    def _validate_target(self, target):
        """Do not let the command silently use a stale shell's database settings."""
        filename = '.env' if target == 'production' else '.env.rehearsal'
        values = dotenv_values(settings.BASE_DIR / filename, interpolate=False)
        mapping = {'DB_HOST': 'HOST', 'DB_PORT': 'PORT', 'DB_NAME': 'NAME',
                   'DB_USER': 'USER', 'DB_PASSWORD': 'PASSWORD'}
        configured = connections['default'].settings_dict
        if any(not values.get(k) or str(configured.get(v, '')) != str(values[k]) for k, v in mapping.items()):
            raise CommandError(f'Database settings do not match {filename}. Use scripts/prepare_faculty_test_requests.py.')
        if target == 'rehearsal':
            production = dotenv_values(settings.BASE_DIR / '.env', interpolate=False)
            identity = ('DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER')
            if tuple(values.get(k) for k in identity) == tuple(production.get(k) for k in identity):
                raise CommandError('Rehearsal matches production; stopped.')

    def handle(self, *args, **options):
        self._validate_target(options['database_target'])
        email = options['email'].strip()
        if not email or '@' not in email:
            raise CommandError('Enter the exact faculty email address.')
        days = options['days']
        tomorrow = timezone.now().astimezone(ZONE).date() + timedelta(days=1)
        start = options['start_date'] or tomorrow
        if not 1 <= days <= 30 or start < tomorrow:
            raise CommandError('Use a future start date (tomorrow or later) and --days between 1 and 30.')
        duration = options['duration']
        begin = options['start_time']
        if duration < 15 or duration > 120 or duration % 15:
            raise CommandError('Use --duration between 15 and 120 minutes, in 15-minute increments.')
        if begin is not None and (begin.tzinfo is not None or begin.second or begin.microsecond
                or begin < time(9) or begin > time(17)
                or (datetime.combine(start, begin) + timedelta(minutes=duration)).time() > time(17)):
            raise CommandError('Use a local --start-time HH:MM and duration fitting between 09:00 and 17:00 Philippine time.')
        plan_options = {'weekdays': options['weekdays'], 'start_time': begin, 'duration': duration}
        faculty = self._faculty(email)
        school = faculty.user.school
        with school_scope(school):
            student = self._student(faculty)
            slots = self._plan(faculty, start, days, **plan_options)
            self.stdout.write(f"Database: {options['database_target']} | School: {school.name}")
            self.stdout.write(f'Faculty: {faculty.user.get_full_name() or faculty.user.username} ({email})')
            self.stdout.write(f'Unit: {faculty.user.department.name if faculty.user.department_id else faculty.college_id}')
            self.stdout.write(f'Student: FacSync Test Student | Level: {student.get_educational_level_display()} | No email or login')
            self.stdout.write(f'All four: Pending | Face-to-Face | General Concern / Talk | {duration} minutes | Philippine time')
            for task, slot in zip(TASKS, slots):
                self.stdout.write(f'{task[0]} - {task[1]}: {slot[0]} {slot[1]:%H:%M}-{slot[2]:%H:%M}')
                self.stdout.write(f'  Message: FacSync testing - Task {task[0]}: {task[2]} This is a test only; no actual meeting is required.')
            self.stdout.write('Creation emails: OFF. No Calendar events are created by this command.')
            self.stdout.write('These records affect histories and analytics. Normal faculty approval may create Calendar events.')
            if options['dry_run']:
                self.stdout.write('Preview only. No test records created.')
                return
            try:
                confirm = input('Create these FOUR requests? Type YES: ')
            except (EOFError, KeyboardInterrupt):
                confirm = ''
            if confirm != 'YES':
                self.stdout.write('Cancelled. No test records created.')
                return
            with transaction.atomic():
                School.objects.select_for_update().get(pk=school.pk, is_active=True)
                User.objects.select_for_update().get(pk=faculty.user_id)
                locked = self._faculty(email)
                student = self._student(locked)
                if (locked.user_id != faculty.user_id or locked.user.department_id != faculty.user.department_id
                        or locked.college_id != faculty.college_id or self._plan(locked, start, days, **plan_options) != slots):
                    raise CommandError('Faculty assignment or available slots changed. Rerun to review a fresh preview.')
                self.create_requests(locked, student, slots)
                # Deliberately do not invoke booking views, notifications, email queues or Calendar writes.
            self.stdout.write(self.style.SUCCESS('Created four test requests. Ask the faculty tester to refresh their dashboard. No creation emails sent.'))
