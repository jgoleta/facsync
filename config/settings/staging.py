"""Local staging against a separate Supabase project; select explicitly."""

import re

from django.core.exceptions import ImproperlyConfigured
from dotenv import dotenv_values

from .base import *  # noqa: F403


_staging = dotenv_values(BASE_DIR / '.env.staging', interpolate=False)
_required = ('NAME', 'USER', 'PASSWORD', 'HOST', 'PORT')
if any(not _staging.get(f'STAGING_DB_{key}') for key in _required):
    raise ImproperlyConfigured('Set all STAGING_DB_* values in .env.staging.')


def _project_reference(host, username):
    direct = re.fullmatch(r'db\.([a-z0-9]+)\.supabase\.co', host)
    if direct:
        return direct.group(1)
    if host.endswith('.pooler.supabase.com'):
        pooled = re.fullmatch(r'[a-z_][a-z0-9_]*\.([a-z0-9]+)', username)
        if pooled:
            return pooled.group(1)
    return None


_host = _staging['STAGING_DB_HOST'].strip().lower()
_user = _staging['STAGING_DB_USER'].strip()
_reference = _project_reference(_host, _user)
if not _reference:
    raise ImproperlyConfigured('Use a Supabase direct or session-pooler connection for staging.')

_primary_reference = _project_reference(
    str(DATABASES['default']['HOST']).strip().lower(),
    str(DATABASES['default']['USER']).strip(),
)
_storage_reference = re.fullmatch(r'https://([a-z0-9]+)\.supabase\.co', SUPABASE_URL)
if _reference == _primary_reference or (
    _storage_reference and _reference == _storage_reference.group(1)
):
    raise ImproperlyConfigured('Staging must use a different Supabase project from the main configuration.')

if _staging['STAGING_DB_PORT'].strip() != '5432':
    raise ImproperlyConfigured('Use port 5432 for the staging direct/session connection.')

if _staging.get('STAGING_DB_SCHEMA') != 'facsync_staging':
    raise ImproperlyConfigured('Provision the isolated facsync_staging schema before using staging.')
if _user.split('.')[0] != 'facsync_staging_login':
    raise ImproperlyConfigured('Staging must use the dedicated facsync_staging_login database role.')

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': _staging['STAGING_DB_NAME'].strip(),
        'USER': _user,
        'PASSWORD': _staging['STAGING_DB_PASSWORD'],
        'HOST': _host,
        'PORT': '5432',
        'CONN_MAX_AGE': 0,
        'CONN_HEALTH_CHECKS': True,
        'OPTIONS': {
            'sslmode': 'require',
            'connect_timeout': 8,
            # Never resolve existing Django tables or migration records in other schemas.
            'options': '-c search_path=facsync_staging',
        },
    },
}

# This settings module is for a local server, not a public deployment.
DEBUG = False
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]']
SITE_URL = 'http://127.0.0.1:8000'
SESSION_COOKIE_NAME = 'facsync_staging_sessionid'
CSRF_COOKIE_NAME = 'facsync_staging_csrftoken'

# Do not inherit external delivery/storage credentials from the main .env.
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
EMAIL_HOST_USER = ''
EMAIL_HOST_PASSWORD = ''
BREVO_API_KEY = ''
GEMINI_API_KEY = ''
AUTOMATIC_STATUS_EMAIL_QUEUE_ENABLED = False
STATUS_SCHEDULER_SECRET = ''
SUPABASE_URL = ''
SUPABASE_SECRET_KEY = ''
GOOGLE_CALENDAR_REDIRECT_URI = SITE_URL + '/faculty/calendar/callback/'

# The separate staging database has no production SocialApp records. Wire the
# existing local Google login credentials into allauth without copying records
# or exposing credentials through the System Admin bootstrap command.
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    SOCIALACCOUNT_PROVIDERS = {
        **SOCIALACCOUNT_PROVIDERS,
        'google': {
            **SOCIALACCOUNT_PROVIDERS.get('google', {}),
            'APP': {'client_id': GOOGLE_CLIENT_ID, 'secret': GOOGLE_CLIENT_SECRET, 'key': ''},
        },
    }
