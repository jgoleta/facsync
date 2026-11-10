import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.decorators import role_required
from apps.core.models import School, SuperAdminInvite, User
from apps.core.services import send_superadmin_deactivated_email, send_superadmin_invite_email
from .forms import SchoolForm, SuperAdminEditForm, SuperAdminInviteForm
from .services import require_replacement_superadmin

logger = logging.getLogger(__name__)


def _deliver_invite(request, invite):
    if not (invite.email or '').strip():
        return
    try:
        sent = send_superadmin_invite_email(invite.email, invite.school)
        if not sent:
            raise RuntimeError('Email backend did not accept the invitation.')
    except Exception as error:
        logger.warning('superadmin_invite_email_failed invite=%s category=%s', invite.pk, type(error).__name__)
        messages.warning(request, 'The invitation is saved, but its email could not be sent. Use Resend email to try again.')
    else:
        messages.success(request, f'Invitation email sent to {invite.email}.')


def _deliver_deactivation(request, user):
    if not (user.email or '').strip():
        return
    try:
        if not send_superadmin_deactivated_email(user):
            raise RuntimeError('Email backend did not accept the notice.')
    except Exception as error:
        logger.warning('superadmin_deactivation_email_failed user=%s category=%s', user.pk, type(error).__name__)
        messages.warning(request, 'The School Admin was deactivated, but the notification email could not be sent.')


def _form_page(request, form, *, title, tab, back, school=None):
    return render(request, 'systemadmin/form.html', dict(form=form, title=title, tab=tab,
        back=back, school=school, changes=school.changes.select_related('actor')[:30] if school else None))


@login_required
@role_required('systemadmin')
def overview(request):
    schools = School.objects.aggregate(total=Count('pk'), active=Count('pk', filter=Q(is_active=True)))
    return render(request, 'systemadmin/overview.html', {
        'tab': 'overview', 'title': 'System Overview',
        'subtitle': 'A platform-wide view of schools and administrator onboarding.',
        'total_schools': schools['total'],
        'active_schools': schools['active'],
        'suspended_schools': schools['total'] - schools['active'],
        'total_superadmins': User.objects.filter(role='superadmin').count(),
        'pending_invitations': SuperAdminInvite.objects.filter(
            used=False, is_active=True, school__is_active=True,
        ).count(),
    })


@login_required
@role_required('systemadmin')
def manage_schools(request):
    return render(request, 'systemadmin/schools.html', {
        'schools': School.objects.prefetch_related('domains').annotate(
            superadmin_count=Count('users', filter=Q(users__role='superadmin'), distinct=True)),
        'tab': 'schools', 'title': 'Manage Schools',
        'subtitle': 'Manage school details, registration domains and access to FacSync.',
    })


@login_required
@role_required('systemadmin')
def school_edit(request, school_id=None):
    school = get_object_or_404(School, pk=school_id) if school_id else None
    form = SchoolForm(request.POST or None, instance=school)
    if request.method == 'POST' and form.is_valid():
        try:
            form.save(actor=request.user)
        except (ValidationError, IntegrityError) as error:
            form.add_error(None, '; '.join(error.messages) if isinstance(error, ValidationError)
                           else 'A school code or domain is already in use. Review the latest assignments.')
        else:
            messages.success(request, 'School updated.' if school else 'School created.')
            return redirect('systemadmin:manage_schools')
    return _form_page(request, form, title='Edit School' if school else 'Add School',
                      tab='schools', back='systemadmin:manage_schools', school=school)


@login_required
@role_required('systemadmin')
@require_POST
def school_status(request, school_id):
    with transaction.atomic():
        school = get_object_or_404(School.objects.select_for_update(), pk=school_id)
        action = request.POST.get('action')
        if action not in {'suspend', 'reactivate'}:
            messages.error(request, 'Choose suspend or reactivate.')
        else:
            school.is_active = action == 'reactivate'
            school.save(actor=request.user, update_fields=['is_active', 'updated_at'])
            messages.success(request, 'School reactivated.' if school.is_active else 'School suspended. Its users can no longer access FacSync.')
    return redirect('systemadmin:manage_schools')


@login_required
@role_required('systemadmin')
def manage_superadmins(request):
    return render(request, 'systemadmin/superadmins.html', {
        'administrators': User.objects.filter(role='superadmin').select_related('school').order_by('school__name', 'email'),
        'invitations': SuperAdminInvite.objects.filter(used=False).select_related('school', 'invited_by'),
        'filter_schools': School.objects.all(),
        'tab': 'superadmins', 'title': 'Manage School Admins',
        'subtitle': 'Invite School Admins and manage their access to each school.',
    })


@login_required
@role_required('systemadmin')
def invite_edit(request, invite_id=None):
    # Never edit a consumed invite to silently reassign an activated account.
    with transaction.atomic():
        invite = get_object_or_404(SuperAdminInvite.objects.select_for_update(), pk=invite_id, used=False) if invite_id else None
        form = SuperAdminInviteForm(request.POST or None, instance=invite)
        saved = None
        if request.method == 'POST' and form.is_valid():
            try:
                with transaction.atomic():
                    saved = form.save(commit=False)
                    saved.invited_by = request.user
                    # Editing a cancelled invite does not implicitly reactivate it.
                    saved.save()
            except (ValidationError, IntegrityError):
                saved = None
                form.add_error(None, 'This email is no longer available. Review existing accounts and invitations.')
    if saved:
        if saved.is_active:
            _deliver_invite(request, saved)
        else:
            messages.success(request, 'Invitation updated. Reactivate it when ready.')
        return redirect('systemadmin:manage_superadmins')
    return _form_page(request, form, title='Edit School Admin Invitation' if invite else 'Invite School Admin',
                      tab='superadmins', back='systemadmin:manage_superadmins')


@login_required
@role_required('systemadmin')
@require_POST
def invite_status(request, invite_id):
    with transaction.atomic():
        invite = get_object_or_404(SuperAdminInvite.objects.select_for_update().select_related('school'), pk=invite_id, used=False)
        action = request.POST.get('action')
        if action not in {'deactivate', 'reactivate'}:
            messages.error(request, 'Choose deactivate or reactivate.')
        elif action == 'reactivate' and not invite.school.is_active:
            messages.error(request, 'Reactivate the school before reactivating this invitation.')
        else:
            invite.is_active = action == 'reactivate'
            invite.invited_by = request.user
            invite.save(update_fields=['is_active', 'invited_by'])
            messages.success(request, 'Invitation reactivated.' if invite.is_active else 'Invitation deactivated.')
    return redirect('systemadmin:manage_superadmins')


@login_required
@role_required('systemadmin')
@require_POST
def invite_resend(request, invite_id):
    invite = get_object_or_404(SuperAdminInvite.objects.select_related('school'), pk=invite_id, used=False, is_active=True)
    if not invite.school.is_active:
        messages.error(request, 'Reactivate the school before sending this invitation.')
    else:
        _deliver_invite(request, invite)
    return redirect('systemadmin:manage_superadmins')


@login_required
@role_required('systemadmin')
def superadmin_edit(request, user_id):
    user = get_object_or_404(User, pk=user_id, role='superadmin')
    form = SuperAdminEditForm(request.POST or None, instance=user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'School Admin updated.')
        return redirect('systemadmin:manage_superadmins')
    return _form_page(request, form, title=f'Edit School Admin: {user.email}',
                      tab='superadmins', back='systemadmin:manage_superadmins')


@login_required
@role_required('systemadmin')
@require_POST
def superadmin_status(request, user_id):
    # Lock the school first so two concurrent deactivations cannot remove its last admin.
    initial = get_object_or_404(User, pk=user_id, role='superadmin')
    notify_deactivation = False
    with transaction.atomic():
        school = get_object_or_404(School.objects.select_for_update(), pk=initial.school_id)
        user = get_object_or_404(User.objects.select_for_update(), pk=user_id, role='superadmin', school=school)
        action = request.POST.get('action')
        try:
            if action not in {'deactivate', 'reactivate'}:
                raise ValidationError('Choose deactivate or reactivate.')
            if action == 'deactivate':
                require_replacement_superadmin(user)
            elif not school.is_active:
                raise ValidationError('Reactivate the school before reactivating this account.')
            was_active = user.is_active and user.account_status == 'active'
            user.account_status = 'active' if action == 'reactivate' else 'deactivated'
            user.is_active = action == 'reactivate'
            user.save(update_fields=['account_status', 'is_active'])
        except ValidationError as error:
            messages.error(request, '; '.join(error.messages))
        else:
            notify_deactivation = was_active and action == 'deactivate'
            messages.success(request, 'School Admin reactivated.' if user.is_active else 'School Admin deactivated.')
    if notify_deactivation:
        _deliver_deactivation(request, user)
    return redirect('systemadmin:manage_superadmins')
