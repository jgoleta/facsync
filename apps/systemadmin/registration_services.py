"""Transactional request submission and restricted review."""
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.education import validate_school_levels
from apps.core.invitations import validate_invite_identity
from apps.core.models import School, SchoolDomain, SchoolRegistrationRequest, SuperAdminInvite, OfficeAdminInvite, User
from apps.core.school_models import require_system_admin
from apps.core.school_requests import email_domain
from apps.core.school_scope import ALL_SCHOOLS, current_school


def available_identity(email):
    validate_invite_identity(email)
    if OfficeAdminInvite._base_manager.filter(email__iexact=email).exists():
        raise ValidationError('This email is already registered or has a pending invitation.')


def submit_request(identity, data):
    from apps.core.school_request_forms import SchoolRegistrationForm
    form = SchoolRegistrationForm(data, identity=identity)
    if not form.is_valid():
        raise ValidationError(form.errors.as_data())
    with transaction.atomic():
        existing = SchoolRegistrationRequest.objects.filter(status='pending').filter(
            Q(google_subject=identity['subject']) | Q(applicant_email__iexact=identity['email'])).first()
        if existing:
            if existing.google_subject == identity['subject'] and existing.applicant_email == identity['email']:
                return existing, False
            raise ValidationError('A request for this verified address is already awaiting review.')
        available_identity(identity['email'])
        if SchoolRegistrationRequest.objects.filter(google_subject=identity['subject'],
                created_at__gte=timezone.now() - timedelta(minutes=1)).exists():
            raise ValidationError('Please wait one minute before submitting another request.')
        item = SchoolRegistrationRequest(google_subject=identity['subject'], applicant_email=identity['email'],
            domain=email_domain(identity['email']), **form.cleaned_data)
        item.full_clean()
        item.save()
        return item, True


def review_request(request_id, *, actor, decision, verification_notes='', decision_reason=''):
    from apps.core.school_request_forms import SchoolRequestReviewForm
    require_system_admin(actor)
    if current_school() is not None and current_school() is not ALL_SCHOOLS:
        raise PermissionDenied('Only FacSync Administration can review school requests.')
    if not User._base_manager.filter(pk=actor.pk, role='systemadmin', school__isnull=True,
            is_active=True, account_status='active').exists():
        raise PermissionDenied('Only FacSync Administration can review school requests.')
    form = SchoolRequestReviewForm({'decision': decision, 'verification_notes': verification_notes,
                                   'decision_reason': decision_reason})
    if not form.is_valid():
        raise ValidationError(form.errors.as_data())
    with transaction.atomic():
        item = SchoolRegistrationRequest.objects.select_for_update().get(pk=request_id)
        if item.status != 'pending':
            return item, False
        if decision == 'approve':
            available_identity(item.applicant_email)
            domain = email_domain(item.applicant_email)
            if item.domain != domain or email_domain(item.contact_email) != domain:
                raise ValidationError('Request identity/domain details are inconsistent. Review before approval.')
            if SchoolDomain.objects.filter(domain__iexact=domain).exists():
                raise ValidationError('This domain is already registered. No school was created.')
            validate_school_levels(item.educational_levels)
            school = School(name=item.school_name, code=item.school_code, educational_levels=item.educational_levels)
            school.save(actor=actor)
            SchoolDomain(school=school, domain=domain).save(actor=actor)
            invite = SuperAdminInvite(school=school, email=item.applicant_email, invited_by=actor)
            invite.full_clean()
            invite.save()
            item.approved_school = school
            item.invitation = invite
            item.status = 'approved'
        else:
            item.status = 'rejected'
        item.reviewed_by = actor
        item.reviewer_label = actor.username
        item.reviewed_at = timezone.now()
        item.verification_notes = form.cleaned_data['verification_notes']
        item.decision_reason = form.cleaned_data['decision_reason']
        item.full_clean()
        item.save()
        return item, True
