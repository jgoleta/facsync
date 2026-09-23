"""Production settings with debug output disabled."""

from .base import *  # noqa: F403
from decouple import Csv, config

DEBUG = False
SECRET_KEY = config('SECRET_KEY')
ALLOWED_HOSTS = [host for host in config('ALLOWED_HOSTS', cast=Csv()) if host]
CSRF_TRUSTED_ORIGINS = [origin for origin in config('CSRF_TRUSTED_ORIGINS', cast=Csv()) if origin]
SITE_URL = config('SITE_URL').rstrip('/')

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
# Vercel terminates TLS and supplies the original request protocol.
# Other hosts must ensure their trusted proxy overwrites this header.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Check reused connections once per request so dropped idle connections
# are replaced before executing application queries.
DATABASES = {
    **DATABASES,
    'default': {
        **DATABASES['default'],
        'CONN_MAX_AGE': config('DB_CONN_MAX_AGE', default=0, cast=int),
        'CONN_HEALTH_CHECKS': True,
    },
}
