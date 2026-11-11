from django.core.exceptions import ValidationError

from apps.core.models import User


def require_replacement_superadmin(user, *, removing_full_access=False):
    if user.role == 'superadmin' and user.school_id and user.is_active and user.account_status == 'active':
        others = User._base_manager.filter(school_id=user.school_id, role='superadmin',
                is_active=True, account_status='active').exclude(pk=user.pk)
        if user.school_admin_full_access and not others.filter(school_admin_full_access=True).exists():
            raise ValidationError('Keep at least one active full-access School Admin for this school. Assign a replacement first.')
        if not removing_full_access and not others.exists():
            raise ValidationError('Keep at least one active School Admin for this school. Activate a replacement first.')
