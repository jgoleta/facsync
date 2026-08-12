from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from core.models import User

@login_required
def pending_faculty_requests(request):
    pending_faculty = User.objects.filter(role='faculty', account_status='pending')
    active_faculty = User.objects.filter(role='faculty', account_status='active')
    return render(request, 'depthead/pendingFacultyRequests.html', {
        'pending_faculty': pending_faculty,
        'active_faculty': active_faculty,
    })


@login_required
def approve_faculty(request, user_id):
    faculty_user = get_object_or_404(User, id=user_id, role='faculty', account_status='pending')
    if request.method == 'POST':
        faculty_user.account_status = 'active'
        faculty_user.save()
    return redirect('depthead:admin_faculty')


@login_required
def decline_faculty(request, user_id):
    faculty_user = get_object_or_404(User, id=user_id, role='faculty', account_status='pending')
    if request.method == 'POST':
        faculty_user.account_status = 'declined'
        faculty_user.save()
    return redirect('depthead:admin_faculty')


def admin_dashboard(request):
    return render(request, 'depthead/adminDashboard.html')


def admin_faculty(request):
    return render(request, 'depthead/adminFaculty.html')


def student_behavior(request):
    return render(request, 'depthead/studentBehavior.html')


def faculty_monitoring(request):
    return render(request, 'depthead/facultyMonitoring.html')


def department_settings(request):
    return render(request, 'depthead/departmentSettings.html')


def peak_analytics(request):
    return render(request, 'depthead/peakAnalytics.html')


def faculty_trends(request):
    return render(request, 'depthead/facultyTrends.html')
