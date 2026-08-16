from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from core.decorators import role_required
from django.contrib import messages
from .forms import DeptHeadInviteForm


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
    return render(request, 'superadmin/manageDepartments.html')

@login_required
@role_required('superadmin')
def manage_admins(request):
    return render(request, 'superadmin/manageAdmins.html')

@login_required
@role_required('superadmin')
def manage_faculty(request):
    return render(request, 'superadmin/manageFaculty.html')

@login_required
@role_required('superadmin')
def manage_students(request):
    return render(request, 'superadmin/manageStudents.html')
