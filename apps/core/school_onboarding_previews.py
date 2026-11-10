"""Development-only visual previews. No database writes, tokens, email or Google calls."""
from copy import copy
from types import SimpleNamespace

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .school_onboarding_forms import SchoolInquiryForm, SchoolVerificationForm
from .school_request_forms import SchoolRegistrationForm
from .school_onboarding_progress import STEPS, onboarding_progress


def preview_response(request, template, context):
    if not getattr(settings, 'SCHOOL_ONBOARDING_PREVIEWS', False):
        raise Http404
    # Show applicant layouts even when the person previewing is already signed in.
    preview_request = copy(request)
    preview_request.user = AnonymousUser()
    preview_request._messages = []
    response = render(preview_request, template, {**context, 'preview_mode': True,
        'preview_stages': [{'key': key, 'label': label} for key, label, _ in STEPS]})
    response['Referrer-Policy'] = 'same-origin'
    response['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@never_cache
@require_GET
def preview_index(request):
    return preview_response(request, 'core/schoolOnboardingPreviews.html', {})


@never_cache
@require_GET
def preview_stage(request, stage):
    progress = onboarding_progress(stage)
    if not progress:
        raise Http404
    identity = {'email': 'representative@school.example.org', 'domain': 'school.example.org',
        'name': 'Sample Representative'}
    details = dict(school_name='Sample School', school_code='SAMPLE', representative_name='Sample Representative',
        position='School representative', contact_email='director@school.example.org',
        website='https://school.example.org', educational_levels=['elementary', 'jhs', 'shs'])
    context = {'onboarding_progress': progress, 'title': progress['label'], 'description': progress['description']}
    template = 'core/schoolAccess.html'
    if stage == 'inquiry_form':
        context.update(title='Request School Access', form=SchoolInquiryForm(initial={
            **details, 'email': identity['email']}))
    elif stage == 'inquiry':
        context.update(title='Inquiry received', completed=True)
    elif stage == 'verification_wait':
        context.update(title='School Verification', identity=identity,
            form=SchoolVerificationForm(domain=identity['domain'], initial={**details, 'address': 'Sample school address',
                'official_name': 'Sample Director', 'official_position': 'School Director',
                'authority': 'Authorized to register the school and serve as its first School Admin.'}))
    elif stage == 'verification_review':
        context.update(title='Verification submitted', completed=True)
    else:
        template = 'core/schoolRegistration.html'
        context.update(identity=identity, form=SchoolRegistrationForm(identity=identity, initial=details), application=None)
        if stage in {'registration_review', 'approved'}:
            status = 'approved' if stage == 'approved' else 'pending'
            context['application'] = SimpleNamespace(**details, pk='SAMPLE-REFERENCE', status=status,
                get_status_display=lambda: 'Approved' if status == 'approved' else 'Pending review')
    return preview_response(request, template, context)
