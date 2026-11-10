import logging
import time

from django.contrib import messages
from django.db import IntegrityError
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from .models import SchoolRegistrationRequest
from .school_request_forms import SchoolRegistrationForm
from .school_requests import applicant_identity, IDENTITY_KEY, INTENT_KEY
from .school_onboarding_progress import onboarding_progress

logger = logging.getLogger(__name__)


def deliver_request_email(sender, item):
    try:
        if not sender(item):
            logger.warning('school_request_email_not_accepted request=%s', item.pk)
            return False
        return True
    except Exception as error:
        logger.warning('school_request_email_failed request=%s category=%s', item.pk, type(error).__name__)
        return False


@never_cache
@require_POST
def start_school_registration(request):
    from .school_onboarding_views import current_access
    if not current_access(request):
        return redirect('core:school_inquiry')
    if request.user.is_authenticated:
        messages.error(request, 'Use your existing account. Sign out first if you need to verify a different institutional email.')
        return redirect('core:school_registration')
    request.session.pop(IDENTITY_KEY, None)
    request.session.pop('registration_role', None)
    request.session[INTENT_KEY] = time.time()
    return redirect('google_login')


@never_cache
@require_POST
def reset_school_registration(request):
    request.session.pop(IDENTITY_KEY, None)
    request.session.pop(INTENT_KEY, None)
    return redirect('core:school_registration')


@never_cache
@require_http_methods(['GET', 'POST'])
def school_registration(request):
    from .school_onboarding_views import current_access, render_access
    link = current_access(request, 'registration')
    identity = applicant_identity(request) if not request.user.is_authenticated else None
    latest = SchoolRegistrationRequest.objects.filter(google_subject=identity['subject'],
        applicant_email=identity['email']).first() if identity else None
    if not link and not (identity and latest and latest.status in ('pending', 'approved')):
        return render_access(request, title='School registration is by invitation',
            description='Submit an inquiry to request access. If you were invited, open the private registration link sent to your email.')
    if link and identity and (identity['email'].lower() != link.inquiry.email.lower()
            or identity['subject'] != link.inquiry.google_subject):
        return render_access(request, title='Use the invited account', needs_google=True,
            progress_stage='registration_wait',
            description='Choose the Google account that completed school verification.')
    initial = {'representative_name': identity['name'] if identity else ''}
    if link:
        initial.update({key: getattr(link.inquiry, key) for key in
            ('representative_name', 'position', 'school_name', 'contact_email', 'website')})
    form = SchoolRegistrationForm(request.POST if request.method == 'POST' else None,
        identity=identity, initial=initial)
    if request.method == 'POST':
        if not identity:
            messages.error(request, 'Verify your institutional Google account before submitting a request.')
            return redirect('core:school_registration')
        if latest and latest.status in ('pending', 'approved'):
            return redirect('core:school_registration')
        if not link:
            return redirect('core:school_inquiry')
        if form.is_valid():
            from apps.systemadmin.onboarding_services import submit_private_registration
            try:
                item, created = submit_private_registration(link.pk, identity, request.POST)
            except ValidationError as error:
                form.add_error(None, error.messages)
            except IntegrityError:
                form.add_error(None, 'A request was submitted at the same time. Refresh to check your status before retrying.')
            else:
                if created:
                    request.session.pop('school_access_link_id', None)
                    from .services import send_school_request_receipt, send_school_request_notification
                    deliver_request_email(send_school_request_receipt, item)
                    deliver_request_email(send_school_request_notification, item)
                return redirect('core:school_registration')
    stage = ('approved' if latest.status == 'approved' else 'registration_review') if latest and latest.status in ('pending', 'approved') else 'registration_wait'
    response = render(request, 'core/schoolRegistration.html', {'identity': identity,
        'application': latest, 'form': form,
        'onboarding_progress': onboarding_progress(stage)}, status=400 if request.method == 'POST' else 200)
    # Same-origin form POSTs need their Origin/Referer for Django's CSRF checks.
    response['Referrer-Policy'] = 'same-origin'
    return response
