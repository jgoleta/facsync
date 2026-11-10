"""School-only School Admin accounts and invitations; no account removal actions."""
import logging

from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.core.decorators import role_required
from apps.core.invitations import validate_invite_identity
from apps.core.models import OfficeAdminInvite, School, SuperAdminInvite, User
from apps.core.services import send_superadmin_invite_email
from .department_views import form_error

logger = logging.getLogger(__name__)


class SchoolSuperAdminInviteForm(forms.Form):
    email = forms.EmailField(label='Google email')

    def clean_email(self):
        email = validate_invite_identity(self.cleaned_data['email'].strip().lower())
        if OfficeAdminInvite._base_manager.filter(email__iexact=email).exists():
            raise ValidationError('This email is already registered or has a pending invitation.')
        return email


def _deliver(invite):
    if not (invite.email or '').strip():
        return False
    try:
        if send_superadmin_invite_email(invite.email, invite.school):
            return True
        logger.warning('school_superadmin_invite_email_not_accepted invite=%s', invite.pk)
    except Exception as error:
        logger.warning('school_superadmin_invite_email_failed invite=%s category=%s', invite.pk, type(error).__name__)
    return False


@login_required
@role_required('superadmin')
def manage_superadmins(request):
    accounts = list(User.objects.filter(role='superadmin', school=request.user.school).order_by('first_name', 'email', 'pk'))
    return render(request, 'superadmin/manageSuperadmins.html', {
        'superadmin_accounts': accounts,
        'superadmin_invites': SuperAdminInvite.objects.filter(school=request.user.school, used=False).select_related('invited_by'),
        'invite_form': SchoolSuperAdminInviteForm(),
    })


def _school_lock(request):
    return get_object_or_404(School.objects.select_for_update(), pk=request.user.school_id, is_active=True)


@login_required
@role_required('superadmin')
@require_POST
def invite_superadmin(request):
    form = SchoolSuperAdminInviteForm(request.POST)
    if not form.is_valid():
        return form_error(form)
    try:
        with transaction.atomic():
            school = _school_lock(request)
            invite = SuperAdminInvite(email=form.cleaned_data['email'], school=school, invited_by=request.user)
            invite.full_clean()
            invite.save()
    except (ValidationError, IntegrityError):
        return JsonResponse({'success': False, 'error': 'This email is already registered or has a pending invitation.'}, status=400)
    sent = _deliver(invite)
    return JsonResponse({'success': True, 'email_sent': sent, 'message':
        'School Admin invitation saved and emailed.' if sent else 'Invitation saved, but the email could not be sent. Use Resend email to try again.'})


@login_required
@role_required('superadmin')
@require_POST
def resend_superadmin_invite(request, invite_id):
    with transaction.atomic():
        _school_lock(request)
        invite = get_object_or_404(SuperAdminInvite.objects.select_for_update().select_related('school'),
            pk=invite_id, school=request.user.school, used=False, is_active=True)
    sent = _deliver(invite)
    return JsonResponse({'success': True, 'email_sent': sent, 'message':
        'Invitation email sent.' if sent else 'The invitation remains saved, but its email could not be sent. Try Resend email again later.'})


@login_required
@role_required('superadmin')
@require_POST
def cancel_superadmin_invite(request, invite_id):
    with transaction.atomic():
        _school_lock(request)
        invite = get_object_or_404(SuperAdminInvite.objects.select_for_update(),
            pk=invite_id, school=request.user.school, used=False)
        if invite.is_active:
            invite.is_active = False
            invite.invited_by = request.user
            invite.save(update_fields=['is_active', 'invited_by'])
    return JsonResponse({'success': True, 'message': 'Invitation cancelled. It can no longer activate a School Admin account.'})
