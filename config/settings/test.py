"""Settings used by the local test suite.

Tests use an isolated SQLite database so they never depend on, or write to, the
configured development/production PostgreSQL database.
"""

from .base import *  # noqa: F403

GEMINI_API_KEY = ""


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
