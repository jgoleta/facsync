from django.shortcuts import render


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
