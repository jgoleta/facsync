"""Preserve school history when an administrator withdraws account access."""
import logging
from django.core.exceptions import ValidationError

from django.db import transaction
from django.db.models import Count, Q

logger = logging.getLogger(__name__)


def with_consultation_counts(users):
    return users.annotate(consultation_count=(
        Count('student_consultation_requests', distinct=True)
        + Count('faculty_profile__consultation_requests', distinct=True)
    ))


def consultation_count(user):
    from apps.faculty.models import ConsultationRequest
    return ConsultationRequest.objects.filter(Q(user=user) | Q(faculty__user=user)).count()


def change_access(user, *, reactivate=False):
    """Caller must resolve and authorize the target in its current school scope."""
    from .models import School, User
    with transaction.atomic():
        School.objects.select_for_update().get(pk=user.school_id)
        target = User.objects.select_for_update().get(pk=user.pk)
        if reactivate:
            from .models import College, Office
            if target.college and not target.department_id and College.objects.filter(
                    code__iexact=target.college, is_active=False).exists():
                raise ValidationError('Reactivate the assigned college before restoring account access.')
            if target.department_id and (not target.department.is_active or (
                    target.department.college_id and not target.department.college.is_active)):
                raise ValidationError('Reactivate the assigned department and college before restoring account access.')
            if target.role == 'depthead' and target.managed_departments.filter(is_active=False).exists():
                raise ValidationError('Reactivate assigned departments before restoring account access.')
            if target.role in {'faculty', 'officeadmin'} and not target.department_id and Office.objects.filter(
                    code__iexact=target.college or '', is_active=False).exists():
                raise ValidationError('Reactivate the assigned office before restoring account access.')
        was_active = target.is_active and target.account_status == 'active'
        changed = target.is_active != reactivate or target.account_status != ('active' if reactivate else 'deactivated')
        target.is_active = reactivate
        target.account_status = 'active' if reactivate else 'deactivated'
        if changed:
            target.save(update_fields=['is_active', 'account_status'])
    sent = True
    if was_active and not reactivate and target.email and target.role in {'faculty', 'depthead'}:
        from .services import send_faculty_deactivated_email, send_depthead_deactivated_email
        try:
            sent = (send_faculty_deactivated_email(target) if target.role == 'faculty'
                    else send_depthead_deactivated_email(target))
        except Exception:
            sent = False
            logger.warning('Account deactivation email failed for user_id=%s', target.pk)
    return target, changed, sent


def access_response(user, *, reactivate=False):
    from django.http import JsonResponse
    try:
        target, changed, sent = change_access(user, reactivate=reactivate)
    except ValidationError as error:
        return JsonResponse({'success': False, 'error': ' '.join(error.messages)}, status=409)
    action = 'reactivated' if reactivate else 'deactivated'
    message = f'{target.get_full_name() or target.username} {action}. Consultation history is preserved.'
    if not sent:
        message += ' The email could not be sent.'
    return JsonResponse({'success': True, 'changed': changed, 'email_sent': sent, 'message': message})
