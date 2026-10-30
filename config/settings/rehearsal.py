"""Read-only access to a restored production copy; no HTTP application routes."""
import re
import secrets

from django.core.exceptions import ImproperlyConfigured
from django.db.backends.signals import connection_created
from dotenv import dotenv_values

from .base import *  # noqa: F403


def project_reference(host, username):
    direct = re.fullmatch(r'db\.([a-z0-9]+)\.supabase\.co', host.strip().lower())
    if direct:
        return direct.group(1)
    if host.strip().lower().endswith('.pooler.supabase.com'):
        pooled = re.fullmatch(r'[a-z_][a-z0-9_]*\.([a-z0-9]+)', username.strip())
        if pooled:
            return pooled.group(1)
    return None


_rehearsal = dotenv_values(BASE_DIR / '.env.rehearsal', interpolate=False)
if any(not _rehearsal.get('REHEARSAL_DB_' + key) for key in ('NAME', 'USER', 'PASSWORD', 'HOST', 'PORT')):
    raise ImproperlyConfigured('Fill in the REHEARSAL_DB_* values in .env.rehearsal.')
_reference = project_reference(_rehearsal['REHEARSAL_DB_HOST'], _rehearsal['REHEARSAL_DB_USER'])
_primary = project_reference(str(DATABASES['default']['HOST']), str(DATABASES['default']['USER']))
_storage = re.fullmatch(r'https://([a-z0-9]+)\.supabase\.co/?', SUPABASE_URL)
_staging = dotenv_values(BASE_DIR / '.env.staging', interpolate=False)
_staging_reference = project_reference(_staging.get('STAGING_DB_HOST') or '', _staging.get('STAGING_DB_USER') or '')
if not _reference or not _primary or not _staging_reference:
    raise ImproperlyConfigured('Cannot verify all three Supabase project identities. Check the connection hosts/users; no connection was attempted.')
if _reference in {_primary, _staging_reference} or (_storage and _reference == _storage.group(1)):
    raise ImproperlyConfigured('Rehearsal must use a project separate from production and staging.')
if (_rehearsal['REHEARSAL_DB_PORT'].strip() != '5432'
        or _rehearsal.get('REHEARSAL_DB_SCHEMA') != 'public'
        or _rehearsal['REHEARSAL_DB_NAME'].strip() != 'postgres'):
    raise ImproperlyConfigured('Rehearsal requires port 5432, database postgres and restored schema public.')

DATABASES = {'default': {
    'ENGINE': 'django.db.backends.postgresql',
    'NAME': 'postgres', 'HOST': _rehearsal['REHEARSAL_DB_HOST'].strip(),
    'USER': _rehearsal['REHEARSAL_DB_USER'].strip(), 'PASSWORD': _rehearsal['REHEARSAL_DB_PASSWORD'],
    'PORT': '5432', 'CONN_MAX_AGE': 0,
    'OPTIONS': {'sslmode': 'require', 'connect_timeout': 8,
                'options': '-c search_path=public -c default_transaction_read_only=on'},
}}


def _enforce_read_only(sender, connection, **kwargs):
    # Some Supabase poolers ignore startup options. Enforce and verify this on
    # the established session before any application command can use it.
    with connection.cursor() as cursor:
        cursor.execute('SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY')
        cursor.execute('SHOW default_transaction_read_only')
        if cursor.fetchone()[0] != 'on':
            raise ImproperlyConfigured('Cannot enforce read-only rehearsal access.')


connection_created.connect(_enforce_read_only, weak=False, dispatch_uid='facsync_rehearsal_read_only')

DEBUG = False
SECRET_KEY = secrets.token_urlsafe(48)
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]']
ROOT_URLCONF = 'config.rehearsal_urls'
SITE_URL = 'http://127.0.0.1:8000'
SESSION_COOKIE_NAME = 'facsync_rehearsal_sessionid'
CSRF_COOKIE_NAME = 'facsync_rehearsal_csrftoken'
EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'
EMAIL_HOST_USER = EMAIL_HOST_PASSWORD = BREVO_API_KEY = GEMINI_API_KEY = ''
SUPABASE_URL = SUPABASE_SECRET_KEY = ''
GOOGLE_CLIENT_ID = GOOGLE_CLIENT_SECRET = GOOGLE_CALENDAR_REDIRECT_URI = ''
SOCIALACCOUNT_PROVIDERS = {}
AUTOMATIC_STATUS_EMAIL_QUEUE_ENABLED = False
STATUS_SCHEDULER_SECRET = ''
