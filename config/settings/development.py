"""Development settings; preserves the existing application configuration."""

from .base import *  # noqa: F403

# Local visual previews use sample data and never submit onboarding forms.
SCHOOL_ONBOARDING_PREVIEWS = True

# Close the connection after each request in runserver so reloads and request
# threads do not exhaust the Supabase session pooler's limited client slots.
DATABASES = {
    **DATABASES,
    'default': {**DATABASES['default'], 'CONN_MAX_AGE': 0, 'CONN_HEALTH_CHECKS': True},
}

INSTALLED_APPS = [*INSTALLED_APPS, 'debug_toolbar']
MIDDLEWARE = ['debug_toolbar.middleware.DebugToolbarMiddleware', *MIDDLEWARE]
INTERNAL_IPS = ['127.0.0.1', '::1']


def show_debug_toolbar(request):
    """Keep the toolbar off JSON endpoints, where it is not useful.

    The toolbar's template panel can inspect and mutate template context while
    processing a response. API responses do not render templates, so allowing
    the toolbar to process them can cause runtime errors in the toolbar itself.
    """
    return not request.path.startswith(
        (
            '/api/',
            '/student/api/',
            '/faculty/api/',
            '/depthead/api/',
            '/schooladmin/api/',
            '/systemadmin/api/',
        )
    )


DEBUG_TOOLBAR_CONFIG = {
    'SHOW_TOOLBAR_CALLBACK': 'config.settings.development.show_debug_toolbar',
}

# Read edited templates on every development request, including long-lived workers.
TEMPLATES = [
    {
        **template,
        'APP_DIRS': False,
        'OPTIONS': {
            **template['OPTIONS'],
            'loaders': [
                'django.template.loaders.filesystem.Loader',
                'django.template.loaders.app_directories.Loader',
            ],
        },
    }
    for template in TEMPLATES
]
