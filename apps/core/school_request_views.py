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
    identity = applicant_identity(request) if not request.user.is_authenticated else None
    latest = SchoolRegistrationRequest.objects.filter(google_subject=identity['subject'],
        applicant_email=identity['email']).first() if identity else None
    form = SchoolRegistrationForm(request.POST if request.method == 'POST' else None,
        identity=identity, initial={'representative_name': identity['name'] if identity else ''})
    if request.method == 'POST':
        if not identity:
            messages.error(request, 'Verify your institutional Google account before submitting a request.')
            return redirect('core:school_registration')
        if latest and latest.status in ('pending', 'approved'):
            return redirect('core:school_registration')
        if form.is_valid():
            from apps.systemadmin.registration_services import submit_request
            try:
                item, created = submit_request(identity, request.POST)
            except ValidationError as error:
                form.add_error(None, error.messages)
            except IntegrityError:
                form.add_error(None, 'A request was submitted at the same time. Refresh to check your status before retrying.')
            else:
                if created:
                    from .services import send_school_request_receipt, send_school_request_notification
                    deliver_request_email(send_school_request_receipt, item)
                    deliver_request_email(send_school_request_notification, item)
                return redirect('core:school_registration')
    response = render(request, 'core/schoolRegistration.html', {'identity': identity,
        'application': latest, 'form': form}, status=400 if request.method == 'POST' else 200)
    # Same-origin form POSTs need their Origin/Referer for Django's CSRF checks.
    response['Referrer-Policy'] = 'same-origin'
    return response
