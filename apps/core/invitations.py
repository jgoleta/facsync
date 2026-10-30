"""Global identity collision checks return no account or school details."""
from django.core.exceptions import ValidationError


def validate_invite_identity(email, *, instance=None):
    from .models import User, FacultyInvite, DeptHeadInvite, SuperAdminInvite
    # Exact email existence is an identity check, not tenant browsing. The base
    # manager intentionally checks across schools to prevent duplicate identities.
    if User._base_manager.filter(email__iexact=email).exists():
        raise ValidationError('This email is already registered or has a pending invitation.')
    for model in (FacultyInvite, DeptHeadInvite, SuperAdminInvite):
        rows = model._base_manager.filter(email__iexact=email)
        if isinstance(instance, model) and instance.pk:
            rows = rows.exclude(pk=instance.pk)
        if rows.exists():
            raise ValidationError('This email is already registered or has a pending invitation.')
    return email
