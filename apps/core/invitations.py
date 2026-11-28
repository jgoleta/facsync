"""Global identity collision checks return no account or school details."""
from django.core.exceptions import ValidationError


IDENTITY_UNAVAILABLE = 'This email is already registered or has a pending invitation.'


def unique_registered_user(email):
    """Return one exact identity match, but never guess between duplicate rows."""
    from .models import User
    matches = list(User._base_manager.filter(email__iexact=email).order_by('pk')[:2])
    if len(matches) > 1:
        raise ValidationError(IDENTITY_UNAVAILABLE)
    return matches[0] if matches else None


def validate_invite_identity(email, *, instance=None):
    from .models import User, FacultyInvite, DeptHeadInvite, SuperAdminInvite
    # Exact email existence is an identity check, not tenant browsing. The base
    # manager intentionally checks across schools to prevent duplicate identities.
    if User._base_manager.filter(email__iexact=email).exists():
        raise ValidationError(IDENTITY_UNAVAILABLE)
    for model in (FacultyInvite, DeptHeadInvite, SuperAdminInvite):
        rows = model._base_manager.filter(email__iexact=email)
        if isinstance(instance, model) and instance.pk:
            rows = rows.exclude(pk=instance.pk)
        if rows.exists():
            raise ValidationError(IDENTITY_UNAVAILABLE)
    return email
