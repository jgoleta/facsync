from django.shortcuts import render


def superadmin_dashboard(request):
    return render(request, 'superadmin/superadminDashboard.html')


def manage_departments(request):
    return render(request, 'superadmin/manageDepartments.html')


def manage_admins(request):
    return render(request, 'superadmin/manageAdmins.html')


def manage_faculty(request):
    return render(request, 'superadmin/manageFaculty.html')


def manage_students(request):
    return render(request, 'superadmin/manageStudents.html')
