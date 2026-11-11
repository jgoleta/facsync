from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.core.decorators import role_required
from apps.core.models import Department, User
from apps.faculty.models import FacultyProfile
from .assignment_services import faculty_has_activity, lock_departments
from .forms import DepartmentForm, FacultyAssignmentForm


def form_error(form):
    return JsonResponse({'success': False, 'error': ' '.join(
        str(error) for errors in form.errors.values() for error in errors), 'errors': form.errors}, status=400)


@login_required
@role_required('superadmin')
def manage_departments(request):
    return redirect('superadmin:manage_colleges')


@login_required
@role_required('superadmin')
@require_POST
def save_department(request, department_id=None):
    try:
        with transaction.atomic():
            department = get_object_or_404(Department.objects.select_for_update(), pk=department_id) if department_id else None
            form = DepartmentForm(request.POST, instance=department)
            if not form.is_valid():
                return form_error(form)
            form.save()
    except (ValidationError, IntegrityError) as error:
        message = ' '.join(error.messages) if isinstance(error, ValidationError) else 'That department name or code is already in use.'
        return JsonResponse({'success': False, 'error': message}, status=400)
    return JsonResponse({'success': True, 'message': 'Department updated.' if department_id else 'Department created.'})


@login_required
@role_required('superadmin')
@require_POST
def department_status(request, department_id):
    action = request.POST.get('action')
    if action not in {'deactivate', 'reactivate'}:
        return JsonResponse({'success': False, 'error': 'Choose a valid department action.'}, status=400)
    with transaction.atomic():
        department = get_object_or_404(Department.objects.select_for_update(), pk=department_id)
        if action == 'deactivate' and department.is_active:
            occupied = (department.members.filter(is_active=True, account_status='active').exists()
                        or department.head_assignments.filter(user__is_active=True, user__account_status='active').exists()
                        or department.faculty_invites.filter(used=False).exists()
                        or department.invite_assignments.filter(invite__used=False).exists())
            if occupied:
                return JsonResponse({'success': False, 'error':
                    'Reassign active members and heads and resolve pending invitations before deactivating this department. Accounts and history will not be deleted.'}, status=409)
        department.is_active = action == 'reactivate'
        department.save(update_fields=['is_active'])
    return JsonResponse({'success': True, 'message': 'Department reactivated.' if department.is_active else 'Department deactivated.'})


@login_required
@role_required('superadmin')
@require_POST
def delete_department(request, department_id):
    with transaction.atomic():
        department = get_object_or_404(Department.objects.select_for_update(), pk=department_id)
        try:
            department.delete()
        except ProtectedError:
            return JsonResponse({'success': False, 'error':
                'This department has linked accounts or records. Preserve it and deactivate it when eligible.'}, status=409)
    return JsonResponse({'success': True, 'message': 'Empty department removed.'})


@login_required
@role_required('superadmin')
@require_POST
def assign_faculty(request, user_id):
    form = FacultyAssignmentForm(request.POST, school=request.user.school)
    if not form.is_valid():
        return form_error(form)
    try:
        with transaction.atomic():
            department, office = form.cleaned_data['unit']
            if department:
                department = lock_departments([department], request.user.school)[0]
            user = get_object_or_404(User.objects.select_for_update(), pk=user_id, role='faculty')
            target_code = (department.college.code if department.college else '') if department else office.code
            same = user.department_id == (department.pk if department else None)
            if not department:
                same = same and str(user.college or '').casefold() == office.code.casefold()
            if not same and faculty_has_activity(user):
                return JsonResponse({'success': False, 'error':
                    'This account has activity records. Department or office transfers are not supported yet; its historical records must be preserved.'}, status=409)
            user.department = department
            user.college = target_code
            user.save(update_fields=['department', 'college'])
            profile = FacultyProfile.objects.select_for_update().filter(user=user).first()
            if profile and profile.college_id != target_code:
                profile.college_id = target_code
                profile.save(update_fields=['college_id'])
    except ValidationError as error:
        return JsonResponse({'success': False, 'error': ' '.join(error.messages)}, status=400)
    return JsonResponse({'success': True, 'message': 'Faculty assignment saved.'})
