"""Development settings; preserves the existing application configuration."""

from .base import *  # noqa: F403

# Reuse healthy connections in persistent workers; threaded runserver may
# still close them when its request threads finish.
DATABASES = {
    **DATABASES,
    'default': {**DATABASES['default'], 'CONN_MAX_AGE': 60, 'CONN_HEALTH_CHECKS': True},
}

INSTALLED_APPS = [*INSTALLED_APPS, 'debug_toolbar']
MIDDLEWARE = ['debug_toolbar.middleware.DebugToolbarMiddleware', *MIDDLEWARE]
INTERNAL_IPS = ['127.0.0.1', '::1']
