"""Verified, short-lived applicant sessions; no pending User is created."""
import time

from allauth.core.exceptions import ImmediateHttpResponse
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect

from .school_domains import school_domain_from_email

INTENT_KEY = 'school_request_intent'
IDENTITY_KEY = 'school_request_identity'
IDENTITY_TTL = 3600


def email_domain(email):
    return school_domain_from_email(email)


def applicant_identity(request):
    identity = request.session.get(IDENTITY_KEY)
    try:
        if (not isinstance(identity, dict) or not isinstance(identity['issued_at'], (int, float))
                or not 0 <= time.time() - identity['issued_at'] <= IDENTITY_TTL
                or not isinstance(identity['subject'], str) or not 1 <= len(identity['subject']) <= 255):
            raise ValueError
        domain = email_domain(identity['email'])
    except (KeyError, TypeError, ValueError, ValidationError):
        request.session.pop(IDENTITY_KEY, None)
        return None
    return {**identity, 'domain': domain}


def capture_applicant(request, sociallogin, verified_email):
    from .models import User
    intent = request.session.pop(INTENT_KEY, None)
    request.session.pop(IDENTITY_KEY, None)
    request.session.pop('registration_role', None)
    from .school_onboarding_views import current_access
    access = current_access(request)
    try:
        if not isinstance(intent, (int, float)) or not 0 <= time.time() - intent <= 900:
            raise ValidationError('Your verification link expired. Start Google verification again.')
        if not access or not verified_email or access.inquiry.email.lower() != verified_email.lower():
            raise ValidationError('Use the Google email that received your current private invitation.')
        if not verified_email:
            raise ValidationError('Use a verified institutional Google account.')
        email_domain(verified_email)
        subject = str(sociallogin.account.uid or '')
        if not 1 <= len(subject) <= 255:
            raise ValidationError('Google verification could not be completed. Please try again.')
        if (request.user.is_authenticated or sociallogin.is_existing
                or User._base_manager.filter(email__iexact=verified_email).exists()):
            raise ValidationError('This address already has a FacSync account. Sign in normally instead; existing accounts cannot register another school.')
    except ValidationError as error:
        messages.error(request, ' '.join(error.messages))
    else:
        request.session.cycle_key()
        request.session[IDENTITY_KEY] = {'email': verified_email.lower(), 'subject': subject,
            'name': str(sociallogin.account.extra_data.get('name', ''))[:150], 'issued_at': time.time()}
    target = 'core:school_verification' if access and access.purpose == 'verification' else 'core:school_registration'
    raise ImmediateHttpResponse(redirect(target))
