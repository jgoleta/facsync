"""Production settings with debug output disabled."""

from .base import *  # noqa: F403

DEBUG = False

# Check reused connections once per request so dropped idle connections
# are replaced before executing application queries.
DATABASES = {
    **DATABASES,
    'default': {**DATABASES['default'], 'CONN_MAX_AGE': 60, 'CONN_HEALTH_CHECKS': True},
}
