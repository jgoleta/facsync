from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from .models import SchoolAccessLink, SchoolInquiry, SchoolInquiryEvent
from .school_onboarding_forms import SchoolInquiryForm, SchoolVerificationForm
from .school_requests import applicant_identity
from .school_request_views import deliver_request_email
from .profile_photos import PhotoStorageError
from .school_onboarding_progress import onboarding_progress
from apps.systemadmin.onboarding_services import link_digest, valid_link, submit_verification

LINK_SESSION_KEY = 'school_access_link_id'


def current_access(request, purpose=None):
    link = SchoolAccessLink.objects.select_related('inquiry').filter(pk=request.session.get(LINK_SESSION_KEY)).first()
    return link if link and valid_link(link) and (not purpose or link.purpose == purpose) else None


def render_access(request, **context):
    context['onboarding_progress'] = onboarding_progress(context.pop('progress_stage', None))
    response = render(request, 'core/schoolAccess.html', context)
    # Canonical form URLs contain no token. Same-origin Referer/Origin is needed by CSRF checks.
    response['Referrer-Policy'] = 'same-origin'
    response['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@never_cache
@require_http_methods(['GET', 'POST'])
def school_inquiry(request):
    form = SchoolInquiryForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        # Public forms do not disclose whether an email already has an inquiry.
        email = form.cleaned_data['email']
        key = 'school-inquiry:' + link_digest(request.META.get('REMOTE_ADDR', 'unknown'))
        attempts = cache.get(key, 0)
        if attempts >= 5:
            form.add_error(None, 'Too many submissions. Please try again in an hour.')
        else:
            cache.set(key, attempts + 1, 3600)
            try:
                if not SchoolInquiry.objects.filter(email__iexact=email).exclude(stage__in=['approved', 'rejected']).exists():
                    from datetime import timedelta
                    if SchoolInquiry.objects.filter(email__iexact=email, created_at__gte=timezone.now()-timedelta(hours=1)).count() < 3:
                        item = SchoolInquiry.objects.create(**{k: form.cleaned_data[k] for k in
                            ('representative_name', 'email', 'position', 'school_name')})
                        SchoolInquiryEvent.objects.create(inquiry=item, action='inquiry_submitted')
                        from .services import send_school_inquiry_receipt, send_school_inquiry_notification
                        deliver_request_email(send_school_inquiry_receipt, item)
                        deliver_request_email(send_school_inquiry_notification, item)
            except IntegrityError:
                pass
            return render_access(request, title='Inquiry received', completed=True, progress_stage='inquiry',
                description='Your inquiry has been received. If an inquiry already exists, it remains in review. Check your email for the next steps.')
    return render_access(request, title='Request School Access', form=form, progress_stage='inquiry_form',
        description='Tell us who you represent. A Super Admin will review your inquiry before inviting you to complete private verification.')


@never_cache
@require_GET
def open_school_access(request, token):
    link = SchoolAccessLink.objects.select_related('inquiry').filter(digest=link_digest(token)).first()
    if not link or not valid_link(link):
        return render_access(request, title='Invitation unavailable',
            description='This link has expired, was replaced, or has already been submitted. Contact FacSync if you need a new invitation.')
    request.session[LINK_SESSION_KEY] = link.pk
    # Do not consume a link just by opening it (including email security scanners).
    request.session.pop('school_request_identity', None)
    response = redirect('core:school_verification' if link.purpose == 'verification' else 'core:school_registration')
    response['Referrer-Policy'] = 'no-referrer'
    return response


@never_cache
@require_http_methods(['GET', 'POST'])
def school_verification(request):
    link = current_access(request, 'verification')
    if not link:
        return render_access(request, title='Private verification', description='Open the private verification invitation sent to your email to continue.')
    identity = applicant_identity(request) if not request.user.is_authenticated else None
    if not identity:
        return render_access(request, title='Verify your school representative account', needs_google=True, progress_stage='verification_wait',
            description='Sign in with the Google email that received this invitation. No FacSync account is created at this stage.')
    if identity['email'].lower() != link.inquiry.email.lower():
        return render_access(request, title='Use the invited account', needs_google=True, progress_stage='verification_wait',
            description='The signed-in Google email does not match this invitation. Choose the account that received it.')
    item = link.inquiry
    form = SchoolVerificationForm(request.POST if request.method == 'POST' else None,
        request.FILES if request.method == 'POST' else None, domain=identity['domain'],
        initial={key: getattr(item, key) for key in ('website', 'address', 'official_name', 'official_position', 'contact_email', 'authority')})
    if request.method == 'POST' and form.is_valid():
        try:
            saved = submit_verification(link.pk, identity, request.POST, request.FILES)
        except ValidationError as error:
            form.add_error(None, ' '.join(error.messages))
        except PhotoStorageError:
            form.add_error(None, 'Private document storage is unavailable. Your form has not been submitted. Please try again later.')
        else:
            request.session.pop(LINK_SESSION_KEY, None)
            from .services import send_school_inquiry_notification
            deliver_request_email(send_school_inquiry_notification, saved)
            return render_access(request, title='Verification submitted', completed=True, progress_stage='verification_review',
                description='The Super Admin will review your information and contact the school if needed. You will receive the next steps by email.')
    return render_access(request, title='School Verification', form=form, identity=identity, progress_stage='verification_wait',
        description='Provide the school’s official details and evidence that you are authorized to register it.')
