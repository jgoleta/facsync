"""Back up isolated staging, apply only manager metadata, rehearse then roll back.

This script cannot target another settings module, schema or database role. The
temporary UNC records, sessions and login updates all roll back together. No
integration credentials are enabled by staging settings.
"""
from datetime import time, timedelta
import hashlib
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.staging'

import django
django.setup()

from django.apps import apps
from django.core import serializers
from django.core.management import call_command
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.core.models import College, DemoDataBatch, School, SchoolDomain, User
from apps.core.management.commands.seed_demo_data import fingerprint
from apps.core.management.commands.seed_staging_data import KEY, MODELS
from apps.core.school_scope import school_scope
from apps.depthead.models import CollegeAIInsight
from apps.depthead.services.analytics import get_base_consultation_queryset
from apps.depthead.services.ai_insights import get_stored_ai_insights
from apps.faculty.models import ConsultationRequest, FacultyProfile, ScheduleEvent


def other_relations():
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT n.nspname, c.relname, c.relkind, c.oid, c.relowner,
                   c.relacl::text
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname NOT IN ('facsync_staging', 'information_schema')
              AND n.nspname NOT LIKE 'pg_%%'
            ORDER BY n.nspname, c.relname
        """)
        return cursor.fetchall()


def sample_state():
    batch = DemoDataBatch.objects.get(key=KEY)
    count = 0
    for model in MODELS:
        entries = batch.manifest[model._meta.label]
        objects = list(model._base_manager.filter(pk__in=entries))
        assert len(objects) == len(entries), 'Missing owned sample records.'
        for obj in objects:
            assert fingerprint(obj) == entries[str(obj.pk)], 'Sample record changed.'
            count += 1
    return dict(schools=School.objects.count(), users=User.objects.count(),
                colleges=College.objects.count(), domains=SchoolDomain.objects.count(),
                owned_samples=count)


def main():
    assert connection.vendor == 'postgresql'
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_user, current_schema(), current_schemas(false)')
        assert cursor.fetchone() == ('facsync_staging_login', 'facsync_staging', ['facsync_staging'])
    unrelated = other_relations()
    original = sample_state()
    assert original == dict(schools=1, users=16, colleges=7, domains=0, owned_samples=71)
    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes()
    plan = executor.migration_plan(targets)
    assert all(not backwards and migration.app_label == 'core' and
               migration.name == '0022_alter_user_managers'
               for migration, backwards in plan), 'Unexpected migration plan.'

    folder = ROOT / '.staging-backups' / 'before-scope-v1'
    folder.mkdir(parents=True, exist_ok=True)
    fixture = folder / 'data-physical.json'
    manifest = folder / 'manifest.json'
    if not manifest.exists():
        assert not fixture.exists(), 'Incomplete backup exists; preserve it for review.'
        with transaction.atomic():
            tables = set(connection.introspection.table_names())
            models = sorted((m for m in apps.get_models() if m._meta.managed and
                             not m._meta.proxy and m._meta.db_table in tables),
                            key=lambda m: m._meta.label)
            records = (obj for model in models for obj in model._base_manager.order_by('pk').iterator())
            data = serializers.serialize('json', records).encode('utf-8')
            fixture.write_bytes(data)
            manifest.write_text(json.dumps(dict(
                schema='facsync_staging', state=original,
                sha256=hashlib.sha256(data).hexdigest(), objects=len(json.loads(data)),
                applied_migrations=sorted(executor.loader.applied_migrations),
                unrelated_relations=unrelated,
            ), indent=2), encoding='utf-8')
    else:
        saved = json.loads(manifest.read_text(encoding='utf-8'))
        assert hashlib.sha256(fixture.read_bytes()).hexdigest() == saved['sha256']
    print('PASS: isolated schema identity and sample manifest; backup verified.', flush=True)
    call_command('migrate', interactive=False, verbosity=1)

    with transaction.atomic(), patch('requests.sessions.Session.request', side_effect=AssertionError('External HTTP forbidden')):
        actor = User.objects.create_user(username='scope-rehearsal-operator', role='systemadmin')
        unc = School(code='UNC', name='Temporary isolation rehearsal')
        unc.save(actor=actor)
        college = College.objects.create(school=unc, code='CCS', name='UNC_PRIVATE_COLLEGE')
        users = {role: User.objects.create_user(username='UNC_PRIVATE_' + role,
            email='unc-rehearsal-' + role + '@example.invalid', first_name='UNC_PRIVATE_' + role,
            school=unc, college=college.code, role=role, profile_completed=True)
            for role in ('student', 'faculty', 'depthead', 'superadmin')}
        faculty = FacultyProfile.objects.create(user=users['faculty'], faculty_id='UNC_PRIVATE_faculty',
            college_id='CCS', manual_status_override=True, manual_status='available',
            current_status='available', sync_enabled=False)
        ScheduleEvent.objects.create(faculty=faculty, title='UNC_PRIVATE_EVENT',
            date=timezone.localdate() + timedelta(days=2), start_time=time(9), end_time=time(10))
        ConsultationRequest.objects.create(request_id='UNC_PRIVATE_REQUEST', user=users['student'],
            faculty=faculty, date=timezone.localdate(), status='approved')
        CollegeAIInsight.objects.create(school=unc, college_code='CCS', analytics_hash='0' * 64,
            insights={'available': True, 'summary': 'UNC_PRIVATE_AI', 'key_insights': [],
                      'concerns': [], 'recommendations': []}, model_name='test',
            generated_at=timezone.now(), refresh_after=timezone.now() + timedelta(days=7))
        adnu = School.objects.get(code='ADNU')
        foreign = User.objects.filter(school=adnu, role='student').first()
        foreign_faculty = FacultyProfile.objects.filter(user__school=adnu).first()
        foreign_event = ScheduleEvent.objects.filter(faculty=foreign_faculty).first()
        with school_scope(unc):
            assert User.objects.count() == 4
            assert not User.objects.filter(pk=foreign.pk).exists()
            assert get_base_consultation_queryset('CCS').count() == 1
            assert get_stored_ai_insights('CCS')['summary'] == 'UNC_PRIVATE_AI'
        assert not get_base_consultation_queryset('CCS', school=adnu).filter(user__school=unc).exists()
        client = Client(HTTP_HOST='localhost')
        for role in ('student', 'faculty', 'depthead'):
            client.force_login(users[role])
            assert client.get(reverse('superadmin:manage_students')).status_code == 403
            assert client.post(reverse('superadmin:remove_student_superadmin', args=[foreign.pk])).status_code == 403
        client.force_login(users['superadmin'])
        response = client.get(reverse('superadmin:manage_students'))
        assert response.status_code == 200 and b'UNC_PRIVATE_student' in response.content
        assert foreign.email.encode() not in response.content
        assert client.post(reverse('superadmin:remove_student_superadmin', args=[foreign.pk])).status_code == 404
        client.force_login(users['student'])
        response = client.get(reverse('students:api_faculty_statuses'))
        assert response.status_code == 200 and b'UNC_PRIVATE_' in response.content
        assert foreign_faculty.pk.encode() not in response.content
        assert client.get(reverse('students:api_schedule_events'), {'faculty_id': foreign_faculty.pk}).status_code == 404
        client.force_login(users['faculty'])
        assert client.get(reverse('faculty:api_schedule_event_detail', args=[foreign_event.pk])).status_code == 404
        client.force_login(users['depthead'])
        response = client.get(reverse('depthead:ai_insights_api'))
        assert response.status_code == 200 and b'UNC_PRIVATE_AI' in response.content
        unc.is_active = False
        unc.save(actor=actor)
        for role, route in [('student', 'students:dashboard'), ('faculty', 'faculty:dashboard'),
                            ('depthead', 'depthead:admin_dashboard'), ('superadmin', 'superadmin:manage_students')]:
            client.force_login(users[role])
            assert client.get(reverse(route)).status_code == 403
        transaction.set_rollback(True)
    assert sample_state() == original
    assert not School.objects.filter(code='UNC').exists()
    assert not User.objects.filter(username='scope-rehearsal-operator').exists()
    assert other_relations() == unrelated, 'Unrelated schema inventory changed.'
    print('PASS: PostgreSQL role/URL/ID, same-college analytics/AI and suspension isolation.', flush=True)
    print('PASS: rehearsal rolled back; original 71 samples valid; other schema inventory unchanged.', flush=True)


if __name__ == '__main__':
    try:
        main()
    finally:
        connection.close()
