"""Reviewed, atomic transitions before a school exists."""
import hashlib
import secrets
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import SchoolAccessLink, SchoolInquiry, SchoolInquiryEvent, SchoolDomain, User
from apps.core.school_models import require_system_admin
from apps.core.school_requests import email_domain


def link_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def valid_link(link):
    expected = 'verification_wait' if link.purpose == 'verification' else 'registration_wait'
    return (not link.consumed_at and not link.revoked_at and link.expires_at > timezone.now()
            and link.inquiry.stage == expected)


def reviewer(actor):
    require_system_admin(actor)
    if not User._base_manager.filter(pk=actor.pk, role='systemadmin', school__isnull=True,
            is_active=True, account_status='active').exists():
        raise PermissionDenied('Only an active platform Super Admin can review school inquiries.')


def review_inquiry(inquiry_id, *, actor, action, private_notes='', applicant_message=''):
    from apps.core.school_onboarding_forms import SchoolInquiryReviewForm
    reviewer(actor)
    form = SchoolInquiryReviewForm(dict(action=action, private_notes=private_notes, applicant_message=applicant_message))
    if not form.is_valid():
        raise ValidationError(form.errors.as_data())
    with transaction.atomic():
        item = SchoolInquiry.objects.select_for_update().get(pk=inquiry_id)
        if action in {'send_verification', 'request_changes'}:
            allowed = {'inquiry', 'verification_wait', 'verification_review'} if action == 'send_verification' else {'verification_review'}
            purpose, stage = 'verification', 'verification_wait'
        elif action == 'send_registration':
            allowed = {'verification_review', 'registration_wait'}
            purpose, stage = 'registration', 'registration_wait'
        else:
            allowed = {'inquiry', 'verification_wait', 'verification_review', 'registration_wait'}
            purpose, stage = None, 'rejected'
        if item.stage not in allowed:
            raise ValidationError('This action is unavailable at the current stage. Refresh the request.')
        if purpose == 'registration' and (not item.evidence_path or not item.google_subject):
            raise ValidationError('The representative must submit verification details first.')
        now = timezone.now()
        item.links.filter(consumed_at__isnull=True, revoked_at__isnull=True).update(revoked_at=now)
        item.stage = stage
        if stage == 'rejected':
            item.closed_at = now
        item.save()
        event = SchoolInquiryEvent.objects.create(inquiry=item, actor=actor, action=action,
            private_notes=form.cleaned_data['private_notes'], applicant_message=form.cleaned_data['applicant_message'])
        token = None
        if purpose:
            token = secrets.token_urlsafe(32)
            SchoolAccessLink.objects.create(inquiry=item, purpose=purpose, digest=link_digest(token),
                expires_at=now + timedelta(days=7))
        return item, token, event


def submit_verification(link_id, identity, data, files):
    from apps.core.school_onboarding_forms import SchoolVerificationForm
    from apps.core.school_evidence import SchoolEvidenceStorage, remove_evidence_safely
    form = SchoolVerificationForm(data, files, domain=identity['domain'])
    if not form.is_valid():
        raise ValidationError(form.errors.as_data())
    path = ''
    try:
        with transaction.atomic():
            # Always lock the inquiry before its links, matching review and final submission.
            inquiry_id = SchoolAccessLink.objects.values_list('inquiry_id', flat=True).get(pk=link_id)
            item = SchoolInquiry.objects.select_for_update().get(pk=inquiry_id)
            link = SchoolAccessLink.objects.select_for_update().select_related('inquiry').get(pk=link_id)
            if (not valid_link(link) or link.purpose != 'verification'
                    or item.email.lower() != identity['email'].lower()):
                raise ValidationError('This verification invitation is unavailable or belongs to another account.')
            if SchoolDomain.objects.filter(domain__iexact=identity['domain']).exists():
                raise ValidationError('This domain is already registered. Contact the School Admin or FacSync support.')
            path, digest = SchoolEvidenceStorage().store(item, form.cleaned_data['letter'])
            previous = item.evidence_path
            for key, value in form.cleaned_data.items():
                if key not in {'letter', 'declaration'}:
                    setattr(item, key, value)
            item.evidence_path, item.evidence_sha256 = path, digest
            item.domain, item.google_subject = identity['domain'], identity['subject']
            item.stage = 'verification_review'
            item.save()
            link.consumed_at = timezone.now()
            link.save(update_fields=['consumed_at'])
            SchoolInquiryEvent.objects.create(inquiry=item, action='verification_submitted')
            transaction.on_commit(lambda: remove_evidence_safely(previous))
            return item
    except Exception:
        if path:
            remove_evidence_safely(path)
        raise


def submit_private_registration(link_id, identity, data):
    from .registration_services import submit_request
    with transaction.atomic():
        inquiry_id = SchoolAccessLink.objects.values_list('inquiry_id', flat=True).get(pk=link_id)
        item = SchoolInquiry.objects.select_for_update().get(pk=inquiry_id)
        link = SchoolAccessLink.objects.select_for_update().select_related('inquiry').get(pk=link_id)
        if (link.purpose != 'registration' or not valid_link(link)
                or item.email.lower() != identity['email'].lower() or item.google_subject != identity['subject']
                or item.domain != identity['domain']):
            raise ValidationError('This registration invitation is unavailable or belongs to another account.')
        application, created = submit_request(identity, data, invitation=link)
        item.application, item.stage = application, 'registration_review'
        item.save()
        link.consumed_at = timezone.now()
        link.save(update_fields=['consumed_at'])
        SchoolInquiryEvent.objects.create(inquiry=item, action='registration_submitted')
        return application, created
