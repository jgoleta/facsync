from django.shortcuts import render

def dashboard(request):
    return render(request, 'students/dashboardStudent.html')

def book_consultation(request):
    return render(request, 'students/bookConsultation.html')

def view_schedule(request):
    return render(request, 'students/viewSchedule.html')

def consultation_requests(request):
    return render(request, 'students/consultationRequests.html')