from django.core.exceptions import ValidationError

from apps.core.models import User


def require_replacement_superadmin(user):
    if user.role == 'superadmin' and user.school_id and user.is_active and user.account_status == 'active':
        if not User._base_manager.filter(school_id=user.school_id, role='superadmin',
                is_active=True, account_status='active').exclude(pk=user.pk).exists():
            raise ValidationError('Keep at least one active Super Admin for this school. Activate a replacement first.')
