"""Synthetic migration rehearsal data, confined to the isolated staging schema."""
from datetime import time, timedelta

from django.conf import settings
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.utils import timezone

from apps.core.models import (
    College, CollegeAnnouncement, DemoDataBatch, DeptHeadInvite, FacultyInvite,
    Notification, OfficeClosure, User,
)
from apps.depthead.models import CollegeAIInsight
from apps.faculty.models import (
    ConsultationRequest, FacultyProfile, ScheduleEvent, StatusHistory, WalkInQueue,
)
from apps.students.models import FacultyStatusSubscription
from .seed_demo_data import Command as DemoCommand, fingerprint

KEY = 'staging-adnu-v1'
PREFIX = 'demo-staging-adnu-v1-'
MODELS = (
    User, FacultyProfile, ConsultationRequest, ScheduleEvent, StatusHistory,
    WalkInQueue, FacultyInvite, DeptHeadInvite, CollegeAnnouncement, OfficeClosure,
    FacultyStatusSubscription, Notification, CollegeAIInsight,
)


def build_samples(colleges, now):
    """Build tagged objects without saving, sending mail, or calling integrations."""
    today = timezone.localdate(now, timezone=timezone.get_fixed_timezone(480))
    groups = {model: [] for model in MODELS}
    users = {}

    def user(key, role, college=None, status='active', complete=True):
        obj = User(
            username=PREFIX + key, email=PREFIX + key + '@example.invalid',
            first_name='Staging', last_name=key.replace('-', ' ').title(),
            role=role, college=college, account_status=status,
            school_id=colleges['CCS'].school_id,
            profile_completed=complete, is_staff=False, is_superuser=False,
            title='dean' if role == 'depthead' else None,
            student_id='STG-' + key if role == 'student' else None,
            year_level='2' if role == 'student' else None,
        )
        obj.set_unusable_password()
        groups[User].append(obj)
        users[key] = obj
        return obj

    admin = user('superadmin-1', 'superadmin')
    user('superadmin-2', 'superadmin')
    heads = [user('head-1', 'depthead', 'CCS'),
             user('head-2', 'depthead', 'CON', status='deactivated')]
    profiles = []
    for i, (code, status) in enumerate([
        ('CCS', 'active'), ('ccs', 'active'), ('CON', 'pending'), ('CON', 'deactivated'),
    ], 1):
        owner = user('faculty-' + str(i), 'faculty', code, status)
        profile = FacultyProfile(
            faculty_id=PREFIX + 'f' + str(i), user=owner, college_id=code,
            office_location='STAGING room ' + str(i), biography='Synthetic migration rehearsal data.',
            current_status='available' if i == 1 else 'busy',
            manual_status='available' if i == 1 else 'busy',
            manual_status_override=True, sync_enabled=False, walk_ins_enabled=i <= 2,
            status_updated_at=now,
        )
        profiles.append(profile)
        groups[FacultyProfile].append(profile)
        for offset in (2, 1):
            groups[StatusHistory].append(StatusHistory(
                history_id=PREFIX + f'h{i}-{offset}', faculty=profile,
                status='busy' if offset == 2 else 'available', changed_at=now - timedelta(days=offset),
            ))
        for offset in (1, 2):
            groups[ScheduleEvent].append(ScheduleEvent(
                faculty=profile, title='STAGING teaching block',
                description='Synthetic migration rehearsal schedule.',
                date=today + timedelta(days=offset), start_time=time(9), end_time=time(10),
                event_type='busy', uploaded_by=heads[0] if code.lower() == 'ccs' else heads[1],
                sync_state='local',
            ))

    students = []
    for i in range(1, 9):
        students.append(user(
            'student-' + str(i), 'student',
            None if i == 8 else ('ccs' if i <= 4 else 'CON'),
            'declined' if i == 7 else 'active', complete=i != 8,
        ))
    for i, status in enumerate(dict(ConsultationRequest.STATUS_CHOICES)):
        for faculty_index in (0, 1):
            historical = status in {'completed', 'declined', 'cancelled'}
            groups[ConsultationRequest].append(ConsultationRequest(
                request_id=PREFIX + f'c{i}-{faculty_index}',
                user=students[i % 4], faculty=profiles[faculty_index],
                date=today + timedelta(days=-(i + 1) if historical else i + 1),
                start_time=time(13 + faculty_index), end_time=time(14 + faculty_index),
                status=status, agenda='academic_advising' if i % 2 else 'general_concern',
                consultation_type='online' if faculty_index else 'face_to_face',
                student_message='STAGING synthetic consultation.',
                faculty_note='STAGING synthetic note.' if historical else '',
                calendar_sync_status='not_configured',
            ))
    for i, status in enumerate(dict(WalkInQueue.QUEUE_STATUS_CHOICES)):
        groups[WalkInQueue].append(WalkInQueue(
            queue_id=PREFIX + 'w' + str(i), user=students[i], faculty=profiles[0],
            position=i + 1, status=status, joined_at=now - timedelta(minutes=30 + i),
            notified_at=now - timedelta(minutes=15) if status in {'called', 'completed'} else None,
            served_at=now - timedelta(minutes=5) if status == 'completed' else None,
            student_message='STAGING synthetic walk-in.',
        ))
    for i, used in enumerate((False, True)):
        groups[FacultyInvite].append(FacultyInvite(
            email=PREFIX + f'invited-faculty-{i}@example.invalid',
            college='CCS', invited_by=heads[0], used=used,
        ))
        groups[DeptHeadInvite].append(DeptHeadInvite(
            email=PREFIX + f'invited-head-{i}@example.invalid',
            college='CON', title='dean', invited_by=admin, used=used,
        ))
    for i, audience in enumerate(('faculty', 'students', 'both', 'both')):
        groups[CollegeAnnouncement].append(CollegeAnnouncement(
            college='ccs' if i < 3 else 'con', audience=audience,
            message='STAGING synthetic announcement ' + str(i + 1),
            expiry=now + timedelta(days=7 if i < 3 else -1),
            posted_by=heads[0] if i < 3 else heads[1],
        ))
    for i, code in enumerate(('CCS', 'CON')):
        groups[OfficeClosure].append(OfficeClosure(
            college=code, is_closed=bool(i), reason='STAGING synthetic closure.' if i else '',
            closure_start=today if i else None,
            closure_end=today + timedelta(days=2) if i else None, updated_by=heads[i],
        ))
    for i in range(4):
        groups[FacultyStatusSubscription].append(FacultyStatusSubscription(
            student=students[i], faculty=profiles[i % 2],
        ))
        groups[Notification].append(Notification(
            recipient=students[i], notification_type='announcement',
            title='STAGING synthetic notification', message='Migration rehearsal only.',
            is_read=bool(i % 2),
        ))
    groups[CollegeAIInsight].append(CollegeAIInsight(
        college_code=colleges['CCS'].code, analytics_hash='0' * 64,
        insights={'summary': 'STAGING synthetic cached insight; no AI call was made.',
                  'key_insights': [], 'concerns': [], 'recommendations': []},
        model_name='synthetic-staging-fixture', generated_at=now - timedelta(days=8),
        refresh_after=now - timedelta(days=1),
    ))
    for model, records in groups.items():
        if any(field.name == 'school' for field in model._meta.fields):
            for record in records:
                record.school_id = colleges['CCS'].school_id
    return groups


class Command(DemoCommand):
    help = 'Preview, create, or safely undo the isolated staging migration sample.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--undo', action='store_true')

    def verify_target(self):
        if settings.SETTINGS_MODULE != 'config.settings.staging' or connection.vendor != 'postgresql':
            raise CommandError('This command requires config.settings.staging and PostgreSQL.')
        if (settings.EMAIL_BACKEND != 'django.core.mail.backends.console.EmailBackend'
                or settings.GEMINI_API_KEY or settings.SUPABASE_SECRET_KEY
                or settings.AUTOMATIC_STATUS_EMAIL_QUEUE_ENABLED):
            raise CommandError('Staging external integrations must remain disabled.')
        with connection.cursor() as cursor:
            cursor.execute('SELECT current_user,current_schema(),current_schemas(false)')
            if cursor.fetchone() != ('facsync_staging_login', 'facsync_staging', ['facsync_staging']):
                raise CommandError('Refusing an unexpected schema or database login.')

    def handle(self, *args, **options):
        apply = options['apply']
        with transaction.atomic():
            if not apply and connection.vendor == 'postgresql':
                with connection.cursor() as cursor:
                    cursor.execute('SET TRANSACTION READ ONLY')
            self.verify_target()
            if options['undo']:
                self.undo('default', KEY, not apply, models=MODELS)
                return
            if DemoDataBatch.objects.filter(key=KEY).exists():
                raise CommandError('Staging sample already exists; refusing to duplicate or overwrite it.')
            if User.objects.filter(username__startswith=PREFIX).exists():
                raise CommandError('Tagged accounts already exist without a manifest; refusing to overwrite.')
            colleges = {obj.code.upper(): obj for obj in College.objects.filter(code__in=['CCS','CON'])}
            if set(colleges) != {'CCS', 'CON'}:
                raise CommandError('The existing CCS and CON college seeds are required.')
            if (OfficeClosure.objects.filter(college__iexact='CCS').exists()
                    or OfficeClosure.objects.filter(college__iexact='CON').exists()
                    or CollegeAIInsight.objects.filter(college_code__iexact='CCS').exists()):
                raise CommandError('Existing closure/insight records would conflict; nothing overwritten.')
            now = timezone.now()
            groups = build_samples(colleges, now)
            for model, records in groups.items():
                self.stdout.write(f'{model._meta.label}: +{len(records)}')
            self.stdout.write('Synthetic addresses only; unusable passwords; no OAuth/calendar connections or external calls.')
            if not apply:
                self.stdout.write('Read-only preview complete. No records written.')
                return
            manifest = {}
            for model, records in groups.items():
                for obj in records:
                    obj.clean_fields(exclude=[field.name for field in obj._meta.fields if field.is_relation])
                model.objects.bulk_create(records)
                if model is ConsultationRequest:
                    for obj in records:
                        obj.requested_at = now - timedelta(days=20)
                        if obj.status in {'approved', 'completed', 'cancellation_requested', 'cancelled'}:
                            obj.approved_at = now - timedelta(days=19)
                    model.objects.bulk_update(records, ['requested_at', 'approved_at'])
                saved = model.objects.filter(pk__in=[obj.pk for obj in records])
                manifest[model._meta.label] = {str(obj.pk): fingerprint(obj) for obj in saved}
            DemoDataBatch.objects.create(key=KEY, college=colleges['CCS'], manifest=manifest)
            self.stdout.write('Staging sample saved atomically with an exact ownership manifest: ' + KEY)
