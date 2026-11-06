from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.core.decorators import role_required
from apps.core.models import SchoolRegistrationRequest
from apps.core.school_request_forms import SchoolRequestReviewForm
from apps.core.school_request_views import deliver_request_email
from apps.core.services import send_school_request_rejection
from .registration_services import review_request
from .views import _deliver_invite


@login_required
@role_required('systemadmin')
def school_requests(request):
    status = request.GET.get('status', 'pending')
    if status not in {'pending', 'approved', 'rejected', 'all'}:
        status = 'pending'
    rows = SchoolRegistrationRequest.objects.select_related('approved_school', 'reviewed_by')
    if status != 'all':
        rows = rows.filter(status=status)
    return render(request, 'systemadmin/requests.html', {'tab': 'requests', 'title': 'School Requests',
        'subtitle': 'Verify school representatives before creating schools and their first Super Admin invitation.',
        'applications': Paginator(rows, 25).get_page(request.GET.get('page')), 'status_filter': status})


@login_required
@role_required('systemadmin')
@require_http_methods(['GET', 'POST'])
def request_review(request, request_id):
    item = get_object_or_404(SchoolRegistrationRequest.objects.select_related('approved_school', 'invitation'), pk=request_id)
    form = SchoolRequestReviewForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST':
        if item.status != 'pending':
            messages.info(request, 'This request has already been reviewed. No changes or duplicate emails were made.')
            return redirect('systemadmin:school_requests')
        if form.is_valid():
            try:
                saved, changed = review_request(item.pk, actor=request.user, **form.cleaned_data)
            except ValidationError as error:
                form.add_error(None, error.messages)
            except IntegrityError:
                form.add_error(None, 'A school code, domain or email was claimed at the same time. No partial school was saved. Review the latest records.')
            else:
                if changed:
                    if saved.status == 'approved':
                        messages.success(request, 'School approved. Its first Super Admin invitation is saved.')
                        _deliver_invite(request, saved.invitation)
                    else:
                        messages.success(request, 'Request rejected. No school or account was created.')
                        if not deliver_request_email(send_school_request_rejection, saved):
                            messages.warning(request, 'The decision is saved, but its email could not be sent. The applicant can still check their status.')
                else:
                    messages.info(request, 'This request was already reviewed. No changes were made.')
                return redirect('systemadmin:school_requests')
    return render(request, 'systemadmin/request_review.html', {'tab': 'requests', 'title': 'Review School Request',
        'application': item, 'form': form})
