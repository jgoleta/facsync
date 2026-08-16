from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from core.decorators import role_required
from core.models import User, FacultyInvite
from django.contrib import messages
from .forms import FacultyInviteForm

@login_required
@role_required('depthead')
def pending_faculty_requests(request):
    pending_faculty = User.objects.filter(role='faculty', account_status='pending')
    active_faculty = User.objects.filter(role='faculty', account_status='active')
    return render(request, 'depthead/pendingFacultyRequests.html', {
        'pending_faculty': pending_faculty,
        'active_faculty': active_faculty,
    })


@login_required
@role_required('depthead')
def approve_faculty(request, user_id):
    faculty_user = get_object_or_404(User, id=user_id, role='faculty', account_status='pending')
    if request.method == 'POST':
        faculty_user.account_status = 'active'
        faculty_user.save()
    return redirect('depthead:pending_faculty_requests')


@login_required
@role_required('depthead')
def decline_faculty(request, user_id):
    faculty_user = get_object_or_404(User, id=user_id, role='faculty', account_status='pending')
    if request.method == 'POST':
        faculty_user.account_status = 'declined'
        faculty_user.save()
    return redirect('depthead:pending_faculty_requests')

@login_required
@role_required('depthead')
def invite_faculty(request):
    if request.method == 'POST':
        if not request.user.department:
            messages.error(request, "Your account has no department set. Contact a Super Admin.")
            return redirect('depthead:pending_faculty_requests')
        form = FacultyInviteForm(request.POST)
        if form.is_valid():
            invite = form.save(commit=False)
            invite.department = request.user.department
            invite.invited_by = request.user
            invite.save()
            messages.success(request, f"Invitation created for {invite.email}.")
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
    return redirect('depthead:pending_faculty_requests')

@login_required
@role_required('depthead')
def admin_dashboard(request):
    return render(request, 'depthead/adminDashboard.html')

@login_required
@role_required('depthead')
def admin_faculty(request):
    return render(request, 'depthead/adminFaculty.html')

@login_required
@role_required('depthead')
def student_behavior(request):
    return render(request, 'depthead/studentBehavior.html')

@login_required
@role_required('depthead')
def faculty_monitoring(request):
    return render(request, 'depthead/facultyMonitoring.html')

@login_required
@role_required('depthead')
def department_settings(request):
    return render(request, 'depthead/departmentSettings.html')

@login_required
@role_required('depthead')
def peak_analytics(request):
    return render(request, 'depthead/peakAnalytics.html')

@login_required
@role_required('depthead')
def faculty_trends(request):
    return render(request, 'depthead/facultyTrends.html')
