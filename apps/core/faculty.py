from datetime import timedelta

from django.utils import timezone


def mark_inactive_faculty(users, *, days=30):
    """Annotate faculty users whose most recent login is older than ``days``."""
    inactivity_threshold = timezone.now() - timedelta(days=days)
    for user in users:
        user.is_inactive = (
            user.last_login is None or user.last_login < inactivity_threshold
        )
    return users
