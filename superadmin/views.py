from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from core.decorators import role_required
from django.contrib import messages
from django.http import JsonResponse
from core.departments import get_department_choices
from .forms import DeptHeadInviteForm, FacultySuperInviteForm
from core.models import User, Department 
from core.forms import DepartmentForm


@login_required
@role_required('superadmin')
def invite_depthead(request):
    if request.method == 'POST':
        form = DeptHeadInviteForm(request.POST)
        if form.is_valid():
            invite = form.save(commit=False)
            invite.invited_by = request.user
            invite.save()
            messages.success(request, f"Dept Head invitation created for {invite.email}.")
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
    return redirect('superadmin:manage_admins')

@login_required
@role_required('superadmin')
def superadmin_dashboard(request):
    return render(request, 'superadmin/superadminDashboard.html')

@login_required
@role_required('superadmin')
def manage_departments(request):
    departments = Department.objects.all().order_by('name')

    # Create a dictionary mapping department codes to their respective department heads
    # This allows us to easily find the department head for each department when rendering the template.
    # We use upper() to ensure that the department codes match regardless of case.
    heads_by_dept = {}
    depthead_qs = User.objects.filter(role='depthead').exclude(department='').exclude(department__isnull=True)
    for u in depthead_qs:
        key = u.department.upper()
        heads_by_dept.setdefault(key, []).append(u)

    for dept in departments:
        dept.head_users = heads_by_dept.get(dept.code.upper(), [])

    return render(request, 'superadmin/manageDepartments.html', {
        'departments': departments,
    })

@login_required
@role_required('superadmin')
def manage_admins(request):
    depthead_accounts = User.objects.filter(role='depthead')
    return render(request, 'superadmin/manageAdmins.html', {
        'depthead_accounts': depthead_accounts,
        'dept_head_form': DeptHeadInviteForm(),
        'role_choices': User.ROLE_CHOICES,
    })

@login_required
def manage_faculty(request):
    faculty_accounts = User.objects.filter(role='faculty')
    return render(request, 'superadmin/manageFaculty.html', {
        'faculty_accounts': faculty_accounts,
        'department_choices': get_department_choices(),
    })

@login_required
@role_required('superadmin')
def manage_students(request):
    return render(request, 'superadmin/manageStudents.html')

@login_required
@role_required('superadmin')
def create_department(request):
    if request.method == 'POST':
        form = DepartmentForm(request.POST)
        if form.is_valid():
            dept = form.save()
            messages.success(request, f"Department '{dept.name}' created with code {dept.code}.")
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
    return redirect('superadmin:manage_departments')

@login_required
@role_required('superadmin')
def edit_department(request, department_id):
    department = get_object_or_404(Department, id=department_id)
    if request.method == 'POST':
        form = DepartmentForm(request.POST, instance=department)
        if form.is_valid():
            form.save()
            messages.success(request, f"Department '{department.name}' updated.")
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
    return redirect('superadmin:manage_departments')

@login_required
@role_required('superadmin')
def delete_department(request, department_id):
    department = get_object_or_404(Department, id=department_id)
    if request.method == 'POST':
        name = department.name
        department.delete()
        messages.success(request, f"Department '{name}' removed.")
    return redirect('superadmin:manage_departments')

@login_required
@role_required('superadmin')
def edit_depthead(request, user_id):
    depthead = get_object_or_404(User, id=user_id, role='depthead')
    if request.method == 'POST':
        new_role = request.POST.get('role')
        new_department = request.POST.get('department')

        if new_role not in dict(User.ROLE_CHOICES):
            messages.error(request, "Invalid role selected.")
            return redirect('superadmin:manage_admins')

        depthead.role = new_role
        depthead.department = new_department
        depthead.save()
        messages.success(request, f"Updated {depthead.username}.")
    return redirect('superadmin:manage_admins')


@login_required
@role_required('superadmin')
def remove_depthead(request, user_id):
    depthead = get_object_or_404(User, id=user_id, role='depthead')
    if request.method == 'POST':
        depthead.account_status = 'deactivated'
        depthead.save()
        messages.success(request, f"{depthead.username} has been deactivated.")
    return redirect('superadmin:manage_admins')

@login_required
def invite_faculty_superadmin(request):
    if request.method == 'POST':
        form = FacultySuperInviteForm(request.POST)
        if form.is_valid():
            invite = form.save(commit=False)
            invite.invited_by = request.user
            invite.save()
            messages.success(request, f"Invitation created for {invite.email}.")
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
    return redirect('superadmin:manage_faculty')


@login_required
def remove_faculty_superadmin(request, user_id):
    faculty_user = get_object_or_404(User, id=user_id, role='faculty')
    if request.method == 'POST':
        name = faculty_user.get_full_name() or faculty_user.username
        faculty_user.delete()
        return JsonResponse({'success': True, 'message': f"{name} removed."})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)