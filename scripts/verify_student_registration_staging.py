"""Exercise assigned domains on staging, rolling back every test record.

No migrations or persistent account/domain changes. Never uses default database
settings, production credentials for database access, or external HTTP/email.
"""
import hashlib
import os
from pathlib import Path
import sys
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.staging'

import django
django.setup()

from allauth.account.models import EmailAddress
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.apps import apps
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import serializers
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse

from apps.core.adapters import FacSyncSocialAdapter
from apps.core.models import College, School, SchoolDomain, User
from apps.core.student_registration import EDU_ONLY, SUSPENDED, UNREGISTERED
from verify_school_scoping_staging import other_relations


def state_hash():
    tables = set(connection.introspection.table_names())
    models = sorted((model for model in apps.get_models() if model._meta.managed
        and not model._meta.proxy and model._meta.db_table in tables), key=lambda model: model._meta.label)
    objects = (obj for model in models for obj in model._base_manager.order_by('pk').iterator())
    return hashlib.sha256(serializers.serialize('json', objects).encode('utf-8')).hexdigest()


def social_login(email):
    request = RequestFactory().get('/accounts/google/login/callback/', HTTP_HOST='127.0.0.1:8000')
    request.session = {'registration_role': 'student'}
    request._messages = FallbackStorage(request)
    return request, SocialLogin(user=User(email=email),
        account=SocialAccount(provider='google', uid=email, extra_data={'email': email, 'email_verified': True}),
        email_addresses=[EmailAddress(email=email, verified=True, primary=True)])


def main():
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_user, current_schema(), current_schemas(false)')
        assert cursor.fetchone() == ('facsync_staging_login', 'facsync_staging', ['facsync_staging'])
    executor = MigrationExecutor(connection)
    assert not executor.migration_plan(executor.loader.graph.leaf_nodes()), 'Apply reviewed staging migrations first.'
    assignment = SchoolDomain.objects.select_related('school').get(domain='adnu.edu.ph')
    assert assignment.school.code == 'ADNU' and assignment.school.is_active
    before, unrelated = state_hash(), other_relations()
    print('PASS: isolated staging schema and active, explicitly assigned ADNU domain verified.', flush=True)
    suffix = uuid4().hex[:10]
    with transaction.atomic(), override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'), patch(
            'requests.sessions.Session.request', side_effect=AssertionError('External HTTP forbidden')):
        adapter = FacSyncSocialAdapter()
        request, login = social_login(f'registration-check-{suffix}@adnu.edu.ph')
        adapter.pre_social_login(request, login)
        user = adapter.save_user(request, login)
        assert user.role == 'student' and user.school_id == assignment.school_id and not user.profile_completed
        assert SocialAccount.objects.filter(user=user, provider='google').exists()
        client = Client(HTTP_HOST='127.0.0.1:8000')
        client.force_login(user)
        assert client.get(reverse('core:post_login_redirect')).url == reverse('core:student_profile_setup')
        college = College.objects.filter(school=assignment.school).first()
        assert client.post(reverse('core:student_profile_setup'), dict(student_id='TEST-' + suffix,
            year_level='2', college=college.code)).status_code == 302
        user.refresh_from_db()
        assert user.profile_completed and user.school_id == assignment.school_id

        operator = User.objects.create_user(username='registration-operator-' + suffix, role='systemadmin')
        temporary = School(code='TREG' + suffix.upper(), name='Temporary registration isolation school')
        temporary.save(actor=operator)
        domain = SchoolDomain(school=temporary, domain=f'registration-{suffix}.edu.ph')
        domain.save(actor=operator)
        own_college = College.objects.create(school=temporary, code='CCS', name='Registration test college')
        foreign_college = College.objects.create(school=assignment.school, code='R' + suffix.upper(),
                                                name='Temporary ADNU-only registration college')
        request, login = social_login(f'student@{domain.domain}')
        adapter.pre_social_login(request, login)
        other_user = adapter.save_user(request, login)
        client.force_login(other_user)
        response = client.get(reverse('core:student_profile_setup'))
        assert own_college.name.encode() in response.content and college.name.encode() not in response.content
        assert client.post(reverse('core:student_profile_setup'), dict(student_id='TEST', year_level='2',
            college=foreign_college.code, school=assignment.school_id, role='systemadmin')).status_code == 200
        other_user.refresh_from_db()
        assert not other_user.profile_completed and other_user.role == 'student' and other_user.school_id == temporary.pk

        for email, expected in [(f'{suffix}@gmail.com', EDU_ONLY), (f'student@unregistered-{suffix}.edu.ph', UNREGISTERED)]:
            request, login = social_login(email)
            try:
                adapter.pre_social_login(request, login)
                raise AssertionError('Unsupported registration was accepted.')
            except ImmediateHttpResponse:
                assert [str(message) for message in get_messages(request)] == [expected]
        request, login = social_login(f'late-student@{domain.domain}')
        adapter.pre_social_login(request, login)
        temporary.is_active = False
        temporary.save(actor=operator)
        try:
            adapter.save_user(request, login)
            raise AssertionError('Suspended registration was accepted.')
        except ImmediateHttpResponse:
            assert [str(message) for message in get_messages(request)] == [SUSPENDED]
        assert not User.objects.filter(email=login.user.email).exists()
        transaction.set_rollback(True)
    assert state_hash() == before, 'Staging records changed outside the rehearsal transaction.'
    assert other_relations() == unrelated, 'Unrelated schema inventory changed.'
    print('PASS: real PostgreSQL registration, Google association, profile completion and school isolation.', flush=True)
    print('PASS: both exact rejection messages and suspension at save; all temporary records rolled back.', flush=True)
    print('PASS: all existing staging records and unrelated schema inventory unchanged. No migrations ran.', flush=True)


if __name__ == '__main__':
    try:
        main()
    finally:
        connection.close()
