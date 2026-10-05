"""Explicitly confirmed demo seeds. Dry runs never write, including migrations."""
import hashlib
import json
import random
import re
from collections import Counter
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connections, transaction
from django.db.models.deletion import Collector
from django.utils import timezone

from apps.core.models import College, User, DemoDataBatch
from apps.faculty.models import FacultyProfile, ConsultationRequest, StatusHistory, ScheduleEvent, WalkInQueue


TZ = ZoneInfo('Asia/Manila')
MODELS = (User, FacultyProfile, ConsultationRequest, StatusHistory, ScheduleEvent, WalkInQueue)


def fingerprint(obj):
    values = {f.attname: getattr(obj, f.attname) for f in obj._meta.concrete_fields}
    return hashlib.sha256(json.dumps(values, cls=DjangoJSONEncoder, sort_keys=True).encode()).hexdigest()


def build_plan(college, batch, now, seed):
    """Pure deterministic generator: no model saves, external calls, or signals."""
    rng = random.Random(seed)
    today = now.astimezone(TZ).date()
    prefix = f'demo-{batch}-'
    plan = {m._meta.label: [] for m in MODELS}
    statuses = ['available', 'busy', 'virtual_only', 'on_leave', 'unavailable', 'available']
    def stamp(day, hour, minute=0):
        return datetime.combine(day, time(hour, minute), TZ)
    for i in range(24):
        faculty = i < 6
        number = i + 1 if faculty else i - 5
        username = f'{prefix}{"faculty" if faculty else "student"}-{number:02d}'
        plan['core.User'].append(dict(
            username=username, email=f'{username}@example.invalid',
            first_name='Demo', last_name=f'{"Faculty" if faculty else "Student"} {number:02d}',
            role='faculty' if faculty else 'student', college=college.code,
            account_status='active', is_active=True, profile_completed=True,
            is_staff=False, is_superuser=False,
            student_id=None if faculty else f'DEMO-{batch[:8]}-{number:02d}',
            year_level=None if faculty else str(1 + (number % 4)),
            date_joined=stamp(today - timedelta(days=100), 8),
        ))
        if faculty:
            fid = f'{prefix}f{number}'
            plan['faculty.FacultyProfile'].append(dict(
                faculty_id=fid, user=username, college_id=college.code,
                office_location=f'DEMO office {number}', biography=f'Demo dataset: {batch}',
                current_status=statuses[i], manual_status=statuses[i], manual_status_override=True,
                manual_status_expires_at=None, sync_enabled=False, walk_ins_enabled=i < 3,
                status_updated_at=now,
            ))
            # A carry-in row establishes the state before the rolling seven-day window.
            rows = [(stamp(today - timedelta(days=15), 0), 'unavailable')]
            for offset in range(14, 0, -1):
                day = today - timedelta(days=offset)
                # Different frequencies and durations, not identical daily timelines.
                if (offset + i) % (2 + i % 3) == 0:
                    continue
                rows.extend([
                    (stamp(day, 8, i * 5), 'available' if i % 2 == 0 else 'busy'),
                    (stamp(day, 10 + i % 3, rng.choice([5, 20, 40])), 'busy'),
                    (stamp(day, 13 + i % 3, i * 3), 'available' if i != 3 else 'on_leave'),
                    (stamp(day, 17, i * 2), 'unavailable'),
                ])
            rows.append((now, statuses[i]))
            for j, (changed, status) in enumerate(rows):
                plan['faculty.StatusHistory'].append(dict(history_id=f'{prefix}h{i}-{j}', faculty=fid, status=status, changed_at=changed))
            # Explicit dates avoid recurrence surprises during the defense week.
            week_start = today - timedelta(days=today.weekday())
            for week in range(2):
                for day_index in range(5):
                    day = week_start + timedelta(days=week * 7 + day_index)
                    # Rotate the lightest-loaded faculty each weekday. Some have
                    # no 2-hour gap; others have several hours available.
                    rank = (i - day_index) % 6
                    blocks = [[(9, 11)], [(8, 11), (14, 16)], [(8, 12), (14, 17)],
                              [(9, 12), (13, 16)], [(8, 12), (13, 17)], [(8, 10), (11, 14), (15, 17)]][rank]
                    for b, (start, end) in enumerate(blocks):
                        plan['faculty.ScheduleEvent'].append(dict(
                            faculty=fid, title=f'DEMO teaching block {b + 1}', date=day,
                            start_time=time(start), end_time=time(end), event_type='busy',
                            description=f'Demo dataset: {batch}', location=f'DEMO room {i + 1}',
                            sync_state='local', managed_by_facsync=False, is_csv_upload=False,
                        ))
    # 32 completed, 8 declined, 8 approved, 6 pending. Future slots belong
    # to pending/approved records; completed requests are genuinely historical.
    allocated = set()
    topics = ['grade_consultation'] * 5 + ['project_consultation'] * 3 + ['academic_advising'] * 2 + ['general_concern']
    for i in range(54):
        status = 'completed' if i < 32 else 'declined' if i < 40 else 'approved' if i < 48 else 'pending'
        faculty_index = rng.choices(range(6), weights=[6, 5, 4, 3, 2, 1])[0]
        student_index = i % 18 if i < 18 else rng.choices(range(18), weights=[10, 8, 6] + [2] * 7 + [1] * 8)[0]
        if i < 12:
            day = today - timedelta(days=rng.randint(30, 85))
        elif i < 40:
            # Include a dedicated month-to-date subset early in a new month.
            days_back = rng.randint(1, max(1, today.day - 1)) if i < 24 else rng.randint(1, 21)
            day = today - timedelta(days=days_back)
        else:
            day = today + timedelta(days=1 + (i % 7))
        hour = rng.choices([9, 10, 11, 13, 14, 15, 16], weights=[1, 7, 1, 1, 5, 1, 1])[0]
        def occupied(f, d, h):
            return ((f, d, h) in allocated or any(
                e['faculty'] == f'{prefix}f{f + 1}' and e['date'] == d
                and e['start_time'] < time(h + 1) and e['end_time'] > time(h)
                for e in plan['faculty.ScheduleEvent']
            ))
        while occupied(faculty_index, day, hour):
            faculty_index = (faculty_index + 1) % 6
            if all(occupied(f, day, hour) for f in range(6)):
                day -= timedelta(days=1) if i < 40 else -timedelta(days=1)
        allocated.add((faculty_index, day, hour))
        scheduled = stamp(day, hour)
        requested = min(scheduled - timedelta(days=rng.randint(1, 5), hours=2), now - timedelta(hours=2 + i % 30))
        approved = None if status in ('pending', 'declined') else min(requested + timedelta(hours=rng.randint(2, 36)), scheduled - timedelta(hours=1), now - timedelta(minutes=1))
        plan['faculty.ConsultationRequest'].append(dict(
            request_id=f'{prefix}c{i + 1:02d}', user=f'{prefix}student-{student_index + 1:02d}',
            faculty=f'{prefix}f{faculty_index + 1}', date=day, start_time=time(hour), end_time=time(hour + 1),
            agenda=topics[i % len(topics)], status=status,
            consultation_type='online' if i % 3 == 0 else 'face_to_face',
            student_message=f'DEMO consultation for presentation ({batch})',
            requested_at=requested, approved_at=approved, calendar_sync_status='not_configured',
        ))
    for i in range(10):
        status = 'completed' if i < 6 else 'called' if i < 8 else 'waiting'
        joined = now - timedelta(days=i + 1, minutes=45) if i < 6 else now - timedelta(minutes=10 + (10 - i) * 5)
        plan['faculty.WalkInQueue'].append(dict(
            queue_id=f'{prefix}w{i + 1}', faculty=f'{prefix}f{1 + i % 3}',
            user=f'{prefix}student-{i + 1:02d}', position=1 + i // 3, status=status,
            joined_at=joined, notified_at=joined + timedelta(minutes=5 + i) if status != 'waiting' else None,
            served_at=joined + timedelta(minutes=20 + i * 2) if status == 'completed' else None,
            student_message=f'DEMO walk-in ({batch})',
        ))
    return plan


class Command(BaseCommand):
    help = 'Preview, create, or safely undo one explicitly tagged demo batch.'
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument('--college', help='Exact existing college code or name')
        parser.add_argument('--batch', default='defense-demo')
        parser.add_argument('--seed', type=int, default=20261005)
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--undo', action='store_true')
        parser.add_argument('--confirm-target', help='Target identifier printed by dry-run; required for writes')

    def handle(self, *args, **options):
        alias = 'default'
        db = connections[alias]
        # Supabase pooler hosts and database names can be shared by projects;
        # include the project-specific login in the hash, never in output.
        identity = '|'.join(str(db.settings_dict.get(k, '')) for k in ('ENGINE', 'HOST', 'PORT', 'NAME', 'USER'))
        target = hashlib.sha256(identity.encode()).hexdigest()[:16]
        batch = options['batch']
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,24}', batch):
            raise CommandError('Batch must be 1-25 lowercase letters, digits, or hyphens.')
        self.stdout.write(f"Database: {alias}; engine={db.settings_dict['ENGINE']}; host={db.settings_dict.get('HOST') or '(local)'}; port={db.settings_dict.get('PORT') or '(default)'}; name={db.settings_dict['NAME']}")
        self.stdout.write(f'Target confirmation: {target}')
        if not options['dry_run'] and options['confirm_target'] != target:
            raise CommandError('Write refused. Review --dry-run and explicitly supply its --confirm-target value.')
        with transaction.atomic(using=alias):
            if options['dry_run'] and db.vendor == 'postgresql':
                with db.cursor() as cursor:
                    cursor.execute('SET TRANSACTION READ ONLY')
            manifest_available = DemoDataBatch._meta.db_table in db.introspection.table_names()
            if not manifest_available and not options['dry_run']:
                raise CommandError('Demo manifest migration must be applied separately before writing.')
            if options['undo']:
                if not manifest_available:
                    raise CommandError('No demo manifest table exists; nothing can be safely undone.')
                self.undo(alias, batch, options['dry_run'])
                return
            if not options['college']:
                raise CommandError('--college is required.')
            matches = College.objects.using(alias).filter(name__iexact=options['college'])
            if not matches.exists():
                matches = College.objects.using(alias).filter(code__iexact=options['college'])
            if matches.count() != 1:
                raise CommandError('Specify exactly one existing College name or code.')
            college = matches.get()
            if not college.code or len(college.code) > 64:
                raise CommandError('College has no usable stored code.')
            if manifest_available and DemoDataBatch.objects.using(alias).filter(key=batch).exists():
                raise CommandError('Batch already exists; refusing to modify or duplicate it.')
            prefix = f'demo-{batch}-'
            if User.objects.using(alias).filter(username__startswith=prefix).exists() or FacultyProfile.objects.using(alias).filter(pk__startswith=prefix).exists():
                raise CommandError('Demo identifiers already exist without a new batch; refusing overwrite.')
            plan = build_plan(college, batch, timezone.now(), options['seed'])
            self.stdout.write(f'College resolved from table: id={college.pk}; code={college.code}; name={college.name}')
            self.stdout.write(f'Batch: {batch}; random seed: {options["seed"]}; timezone: Asia/Manila')
            for model in MODELS:
                self.stdout.write(f'  {model._meta.label}: +{len(plan[model._meta.label])}')
            consultations = plan['faculty.ConsultationRequest']
            self.stdout.write('Consultation statuses: ' + json.dumps(dict(Counter(r['status'] for r in consultations)), sort_keys=True))
            self.stdout.write(f"Scheduled dates: {min(r['date'] for r in consultations)} through {max(r['date'] for r in consultations)}")
            self.stdout.write('Agendas: ' + json.dumps(dict(Counter(r['agenda'] for r in consultations)), sort_keys=True))
            self.stdout.write('Scheduled months: ' + json.dumps(dict(Counter(r['date'].strftime('%Y-%m') for r in consultations)), sort_keys=True))
            self.stdout.write('Completed consultation hours: ' + json.dumps(dict(Counter(r['start_time'].strftime('%H:%M') for r in consultations if r['status'] == 'completed')), sort_keys=True))
            self.stdout.write('Top demo requester counts: ' + str([n for _, n in Counter(r['user'] for r in consultations).most_common(5)]))
            self.stdout.write('No announcements, invites, social accounts, subscriptions, Google connections, or external API calls.')
            self.stdout.write('Demo faculty: manual status overrides without expiry; Google sync disabled.')
            self.stdout.write('Existing records modified/deleted: 0. Undo stops if records changed or outside dependencies exist.')
            if options['dry_run']:
                self.stdout.write('Manifest migration: ' + ('already available' if manifest_available else 'NOT APPLIED; needed only before an approved write'))
                self.stdout.write('DRY RUN COMPLETE: no records written, no migration applied.')
                return
            created = self.create_plan(alias, plan)
            manifest = {model._meta.label: {str(obj.pk): fingerprint(obj) for obj in created[model._meta.label]} for model in MODELS}
            DemoDataBatch.objects.using(alias).create(key=batch, college=college, manifest=manifest)
            self.stdout.write(self.style.SUCCESS('Demo batch committed with exact record manifest.'))

    def create_plan(self, alias, plan):
        created = {}
        users, faculty = {}, {}
        for model in MODELS:
            records = []
            for values in plan[model._meta.label]:
                values = values.copy()
                requested = values.pop('requested_at', None)
                if 'user' in values:
                    values['user'] = users[values['user']]
                if 'faculty' in values:
                    values['faculty'] = faculty[values['faculty']]
                obj = model(**values)
                if model is User:
                    obj.set_unusable_password()
                obj.full_clean()
                obj.save(using=alias, force_insert=True)
                if requested is not None:
                    model.objects.using(alias).filter(pk=obj.pk).update(requested_at=requested)
                    obj.requested_at = requested
                # Hash database-normalized timestamps (UTC), not the generator's
                # Asia/Manila representation, so unchanged rows undo reliably.
                obj.refresh_from_db(using=alias)
                if model is User:
                    users[obj.username] = obj
                elif model is FacultyProfile:
                    faculty[obj.pk] = obj
                records.append(obj)
            created[model._meta.label] = records
        return created

    def undo(self, alias, key, dry):
        batches = DemoDataBatch.objects.using(alias)
        if not dry:
            batches = batches.select_for_update()
        batch = batches.filter(key=key).first()
        if batch is None:
            raise CommandError('No recorded batch exists; nothing deleted.')
        owned = {}
        records = []
        for label, snapshots in batch.manifest.items():
            model = apps.get_model(label)
            if model not in MODELS:
                raise CommandError('Unexpected manifest model; undo refused.')
            query = model.objects.using(alias).filter(pk__in=snapshots)
            if not dry:
                query = query.select_for_update()
            rows = list(query)
            if len(rows) != len(snapshots) or any(fingerprint(r) != snapshots[str(r.pk)] for r in rows):
                raise CommandError(f'{label}: seeded records were changed or removed; undo refused for review.')
            owned[model] = set(str(r.pk) for r in rows)
            records.extend(rows)
        collector = Collector(using=alias)
        for model in MODELS:
            collector.collect([r for r in records if type(r) is model])
        def verify(model, rows):
            if any(str(r.pk) not in owned.get(model, set()) for r in rows):
                raise CommandError(f'Outside dependency in {model._meta.label}; undo refused. No records deleted.')
        for model, rows in collector.data.items():
            verify(model, rows)
        for query in collector.fast_deletes:
            verify(query.model, query)
        for updates in collector.field_updates.values():
            for rows in updates:
                rows = list(rows)
                if rows:
                    verify(type(rows[0]), rows)
        self.stdout.write(f'Undo batch {key}: {len(records)} unchanged owned records; no outside dependencies.')
        if dry:
            self.stdout.write('UNDO DRY RUN COMPLETE: nothing deleted.')
            return
        collector.delete()
        batch.delete(using=alias)
        self.stdout.write(self.style.SUCCESS('Only the recorded demo batch was removed.'))
