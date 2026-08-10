from django.shortcuts import render
from faculty.models import FacultyProfile, StatusHistory

def dashboard(request):
    faculty_statuses = FacultyProfile.objects.select_related('user').all()
    status_history = StatusHistory.objects.select_related('faculty__user').order_by('-changed_at')[:10]
    return render(request, 'students/dashboardStudent.html', {
        'faculty_statuses': faculty_statuses,
        'status_history': status_history,
    })

def view_schedule(request):
    return render(request, 'students/viewSchedule.html')

def consultation_requests(request):
    return render(request, 'students/consultationRequests.html')

def home(request):
    return render(request, 'students/homeStudent.html')