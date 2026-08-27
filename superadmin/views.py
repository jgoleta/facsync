from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from core.decorators import role_required
from django.contrib import messages
from django.http import JsonResponse
from core.colleges import get_college_choices
from .forms import DeptHeadInviteForm, FacultySuperInviteForm
from core.models import User, College
from core.forms import CollegeForm


@login_required
@role_required('superadmin')
def invite_depthead(request):
    if request.method == 'POST':
        form = DeptHeadInviteForm(request.POST)
        if form.is_valid():
            invite = form.save(commit=False)
            invite.invited_by = request.user
            invite.save()
            messages.success(request, f"College Head invitation created for {invite.email}.")
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
def manage_colleges(request):
    colleges = College.objects.all().order_by('name')

    # Create a dictionary mapping college codes to their respective college heads
    # This allows us to easily find the college head for each college when rendering the template.
    # We use upper() to ensure that the college codes match regardless of case.
    heads_by_college = {}
    depthead_qs = User.objects.filter(role='depthead').exclude(college='').exclude(college__isnull=True)
    for u in depthead_qs:
        key = u.college.upper()
        heads_by_college.setdefault(key, []).append(u)

    for college in colleges:
        college.head_users = heads_by_college.get(college.code.upper(), [])

    return render(request, 'superadmin/manageColleges.html', {
        'colleges': colleges,
    })

@login_required
@role_required('superadmin')
def manage_admins(request):
    depthead_accounts = User.objects.filter(role='depthead')
    return render(request, 'superadmin/manageAdmins.html', {
        'depthead_accounts': depthead_accounts,
        'dept_head_form': DeptHeadInviteForm(),
        'role_choices': User.ROLE_CHOICES,
        'title_choices': User.TITLE_CHOICES,
    })

@login_required
def manage_faculty(request):
    faculty_accounts = User.objects.filter(role='faculty')
    return render(request, 'superadmin/manageFaculty.html', {
        'faculty_accounts': faculty_accounts,
        'college_choices': get_college_choices(),
    })

@login_required
def manage_students(request):
    student_accounts = User.objects.filter(role='student')
    return render(request, 'superadmin/manageStudents.html', {
        'student_accounts': student_accounts
    })


@login_required
def remove_student_superadmin(request, user_id):
    student_user = get_object_or_404(User, id=user_id, role='student')
    if request.method == 'POST':
        name = student_user.get_full_name() or student_user.username
        student_user.delete()
        return JsonResponse({'success': True, 'message': f"{name} removed."})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)

@login_required
@role_required('superadmin')
def create_college(request):
    if request.method == 'POST':
        form = CollegeForm(request.POST)
        if form.is_valid():
            college = form.save()
            messages.success(request, f"College '{college.name}' created with code {college.code}.")
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
    return redirect('superadmin:manage_colleges')

@login_required
@role_required('superadmin')
def edit_college(request, college_id):
    college = get_object_or_404(College, id=college_id)
    if request.method == 'POST':
        form = CollegeForm(request.POST, instance=college)
        if form.is_valid():
            form.save()
            messages.success(request, f"College '{college.name}' updated.")
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
    return redirect('superadmin:manage_colleges')

@login_required
@role_required('superadmin')
def delete_college(request, college_id):
    college = get_object_or_404(College, id=college_id)
    if request.method == 'POST':
        name = college.name
        college.delete()
        messages.success(request, f"College '{name}' removed.")
    return redirect('superadmin:manage_colleges')

@login_required
@role_required('superadmin')
def edit_depthead(request, user_id):
    depthead = get_object_or_404(User, id=user_id, role='depthead')
    if request.method == 'POST':
        new_role = request.POST.get('role')
        new_college = request.POST.get('college')
        new_title = request.POST.get('title')

        if new_role not in dict(User.ROLE_CHOICES):
            messages.error(request, "Invalid role selected.")
            return redirect('superadmin:manage_admins')

        depthead.role = new_role
        depthead.college = new_college
        depthead.title = new_title
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
