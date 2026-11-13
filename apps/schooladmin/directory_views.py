"""Reversible college/office activation. No cascade to account access or history."""
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from apps.core.decorators import role_required
from apps.core.models import College, Department, DeptHeadInvite, FacultyInvite, Office, OfficeAdminInvite, School, User
from .forms import OfficeStudentLevelsForm
from .department_views import form_error


def _change_status(request, model, pk):
    action = request.POST.get('action')
    if action not in {'deactivate', 'reactivate'}:
        return JsonResponse({'success': False, 'error': 'Choose deactivate or reactivate.'}, status=400)
    if model is College and not request.user.school.offers_college:
        return JsonResponse({'success': False, 'error': 'College is not an offered educational level.'}, status=403)
    with transaction.atomic():
        get_object_or_404(School.objects.select_for_update(), pk=request.user.school_id, is_active=True)
        unit = get_object_or_404(model.objects.select_for_update(), pk=pk)
        if action == 'deactivate' and unit.is_active:
            active_users = User.objects.filter(is_active=True, account_status='active')
            if model is College:
                occupied = (Department.objects.filter(college=unit, is_active=True).exists()
                    or active_users.filter(college__iexact=unit.code).exists()
                    or active_users.filter(department__college=unit).exists()
                    or active_users.filter(managed_departments__college=unit).exists()
                    or FacultyInvite.objects.filter(used=False, college__iexact=unit.code).exists()
                    or FacultyInvite.objects.filter(used=False, department__college=unit).exists()
                    or DeptHeadInvite.objects.filter(used=False, college__iexact=unit.code).exists()
                    or DeptHeadInvite.objects.filter(used=False, departments__college=unit).exists())
            else:
                occupied = (active_users.filter(college__iexact=unit.code, department__isnull=True).exists()
                    or FacultyInvite.objects.filter(used=False, college__iexact=unit.code, department__isnull=True).exists()
                    or OfficeAdminInvite.objects.filter(used=False, office__iexact=unit.code).exists()
                    or DeptHeadInvite.objects.filter(used=False, college__iexact=unit.code).exists())
            if occupied:
                return JsonResponse({'success': False, 'error':
                    'Resolve active departments, assigned accounts and pending invitations before deactivating this '
                    + model._meta.verbose_name + '. Accounts and history will not be deleted.'}, status=409)
        unit.is_active = action == 'reactivate'
        unit.save(update_fields=['is_active'])
    return JsonResponse({'success': True, 'message': f'{unit.name} {"reactivated" if unit.is_active else "deactivated"}. Records are preserved.'})


@login_required
@role_required('superadmin')
@require_POST
def college_status(request, college_id):
    return _change_status(request, College, college_id)


@login_required
@role_required('superadmin')
@require_POST
def office_status(request, office_id):
    return _change_status(request, Office, office_id)


@login_required
@role_required('superadmin')
@require_POST
def edit_office_levels(request, office_id):
    with transaction.atomic():
        get_object_or_404(School.objects.select_for_update(), pk=request.user.school_id, is_active=True)
        office = get_object_or_404(Office.objects.select_for_update(), pk=office_id)
        form = OfficeStudentLevelsForm(request.POST, instance=office)
        if not form.is_valid():
            return form_error(form)
        form.save()
    return JsonResponse({'success': True, 'message': 'Educational levels updated. Existing appointments and history are preserved.'})
