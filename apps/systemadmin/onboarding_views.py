from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from apps.core.decorators import role_required
from apps.core.models import SchoolInquiry
from apps.core.school_onboarding_forms import SchoolInquiryReviewForm
from apps.core.school_request_views import deliver_request_email
from apps.core.profile_photos import PhotoStorageError
from .onboarding_services import review_inquiry, reviewer


@login_required
@role_required('systemadmin')
@never_cache
@require_http_methods(['GET', 'POST'])
def inquiry_review(request, inquiry_id):
    reviewer(request.user)
    item = get_object_or_404(SchoolInquiry.objects.select_related('application'), pk=inquiry_id)
    allowed = []
    if item.stage in {'inquiry', 'verification_wait', 'verification_review'}:
        allowed.append('send_verification')
    if item.stage in {'verification_review', 'registration_wait'}:
        allowed.append('send_registration')
    if item.stage == 'verification_review':
        allowed.append('request_changes')
    if item.stage not in {'registration_review', 'approved', 'rejected'}:
        allowed.append('reject')
    form = SchoolInquiryReviewForm(request.POST if request.method == 'POST' else None)
    form.fields['action'].choices = [(key, value) for key, value in form.fields['action'].choices if key in allowed]
    if request.method == 'POST' and form.is_valid():
        try:
            saved, token, event = review_inquiry(item.pk, actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, ' '.join(error.messages))
        else:
            from apps.core.services import send_school_access_update
            sent = deliver_request_email(lambda obj: send_school_access_update(obj, token, event.applicant_message), saved)
            messages.success(request, 'Review saved and email sent.' if sent else 'Review saved.')
            if not sent:
                messages.warning(request, 'The email could not be sent. The review remains saved. For an invitation, reopen the inquiry and send a replacement; for a rejection, contact the applicant.')
            return redirect('systemadmin:school_requests')
    return render(request, 'systemadmin/inquiry_review.html', {'tab': 'requests', 'title': 'Review School Inquiry',
        'inquiry': item, 'events': item.events.select_related('actor'), 'form': form, 'can_review': bool(allowed)})


@login_required
@role_required('systemadmin')
@never_cache
@require_GET
def inquiry_document(request, inquiry_id):
    reviewer(request.user)
    item = get_object_or_404(SchoolInquiry, pk=inquiry_id)
    if not item.evidence_path:
        return HttpResponse('No document is available.', status=404)
    from apps.core.school_evidence import SchoolEvidenceStorage
    try:
        content = SchoolEvidenceStorage().download(item.evidence_path)
    except PhotoStorageError:
        return HttpResponse('Document storage is unavailable. Please try again later.', status=503)
    response = HttpResponse(content, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="school-authorization.pdf"'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = "sandbox; default-src 'none'"
    response['Referrer-Policy'] = 'no-referrer'
    return response
