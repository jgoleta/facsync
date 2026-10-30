"""Staging-only System Admin migration and rollback-contained smoke checks."""
from io import StringIO
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

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.apps import apps
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail, serializers
from django.core.management import call_command
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse

from apps.core.adapters import FacSyncSocialAdapter
from apps.core.models import School, SuperAdminInvite, User
from verify_school_scoping_staging import other_relations, sample_state


def main():
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_user, current_schema(), current_schemas(false)')
        assert cursor.fetchone() == ('facsync_staging_login', 'facsync_staging', ['facsync_staging'])
    unrelated = other_relations()
    original = sample_state()
    assert original == dict(schools=1, users=16, colleges=7, domains=0, owned_samples=71)
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    assert all(not backwards and migration.app_label == 'core' and
               migration.name == '0023_alter_user_role_superadmininvite'
               for migration, backwards in plan), 'Unexpected migration plan.'
    folder = ROOT / '.staging-backups' / 'before-systemadmin-v1'
    folder.mkdir(parents=True, exist_ok=True)
    fixture, manifest = folder / 'data-physical.json', folder / 'manifest.json'
    if not manifest.exists():
        assert not fixture.exists(), 'Preserve incomplete backup for review.'
        with transaction.atomic():
            tables = set(connection.introspection.table_names())
            models = sorted((m for m in apps.get_models() if m._meta.managed and
                             not m._meta.proxy and m._meta.db_table in tables), key=lambda m: m._meta.label)
            records = (obj for model in models for obj in model._base_manager.order_by('pk').iterator())
            data = serializers.serialize('json', records).encode('utf-8')
            fixture.write_bytes(data)
            manifest.write_text(json.dumps(dict(schema='facsync_staging', state=original,
                sha256=hashlib.sha256(data).hexdigest(), objects=len(json.loads(data)),
                applied_migrations=sorted(executor.loader.applied_migrations), unrelated_relations=unrelated),
                indent=2), encoding='utf-8')
    else:
        saved = json.loads(manifest.read_text(encoding='utf-8'))
        assert hashlib.sha256(fixture.read_bytes()).hexdigest() == saved['sha256']
    print('PASS: isolated schema identity; backup and 71 sample fingerprints verified.', flush=True)
    call_command('migrate', interactive=False, verbosity=1)
    with transaction.atomic(), override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'), patch(
            'requests.sessions.Session.request', side_effect=AssertionError('External HTTP forbidden')):
        call_command('create_systemadmin', email='system-area-rehearsal@example.invalid', apply=True, stdout=StringIO())
        operator = User.objects.get(email='system-area-rehearsal@example.invalid')
        client = Client(HTTP_HOST='localhost')
        client.force_login(operator)
        assert client.get(reverse('systemadmin:manage_schools')).status_code == 200
        assert client.get(reverse('systemadmin:manage_superadmins')).status_code == 200
        assert client.post(reverse('systemadmin:school_add'), dict(name='Temporary UNC', code='UNC', domains='unc.edu.ph')).status_code == 302
        unc = School.objects.get(code='UNC')
        assert unc.domains.get().domain == 'unc.edu.ph'
        assert unc.changes.filter(actor=operator).exists()
        assert client.post(reverse('systemadmin:invite_add'), dict(email='invited-unc@example.invalid', school=unc.pk)).status_code == 302
        invite = SuperAdminInvite.objects.get(email='invited-unc@example.invalid')
        assert mail.outbox[-1].to == [invite.email]
        request = RequestFactory().get('/accounts/google/login/callback/', HTTP_HOST='localhost')
        request.session = {}
        request._messages = FallbackStorage(request)
        login = SocialLogin(user=User(email=invite.email),
            account=SocialAccount(provider='google', uid='system-area-rehearsal', extra_data={'email': invite.email, 'email_verified': True}),
            email_addresses=[EmailAddress(email=invite.email, primary=True, verified=True)])
        adapter = FacSyncSocialAdapter()
        adapter.pre_social_login(request, login)
        user = adapter.save_user(request, login)
        invite.refresh_from_db()
        assert invite.used and user.school_id == unc.pk and user.role == 'superadmin'
        client.force_login(user)
        assert client.get(reverse('systemadmin:manage_schools')).status_code == 403
        assert client.get(reverse('superadmin:manage_students')).status_code == 200
        client.force_login(operator)
        assert client.post(reverse('systemadmin:school_status', args=[unc.pk]), {'action': 'suspend'}).status_code == 302
        client.force_login(user)
        assert client.get(reverse('superadmin:manage_students')).status_code == 403
        client.force_login(operator)
        assert client.post(reverse('systemadmin:school_status', args=[unc.pk]), {'action': 'reactivate'}).status_code == 302
        assert client.post(reverse('systemadmin:school_edit', args=[unc.pk]),
            dict(name='Renamed temporary UNC', code='FORGED', domains='students.unc.edu.ph')).status_code == 302
        unc.refresh_from_db()
        assert unc.code == 'UNC' and unc.domains.get().domain == 'students.unc.edu.ph'
        transaction.set_rollback(True)
    assert sample_state() == original
    assert not User.objects.filter(role='systemadmin').exists()
    assert not School.objects.filter(code='UNC').exists()
    assert not SuperAdminInvite.objects.exists()
    assert other_relations() == unrelated
    print('PASS: PostgreSQL tabs, school/domain edits, invitation email, Google activation, ACL and suspension.', flush=True)
    print('PASS: all rehearsal accounts and schools rolled back; original data and unrelated schema inventory unchanged.', flush=True)


if __name__ == '__main__':
    try:
        main()
    finally:
        connection.close()
