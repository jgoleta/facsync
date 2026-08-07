from django.shortcuts import redirect, render


def dashboard(request):
    return render(request, 'faculty/dashboardFaculty.html')


def booking_management(request):
    return render(request, 'faculty/bookingManagement.html')


def booking_management_legacy(request):
    return redirect('faculty:booking_management')


def profile(request):
    return render(request, 'faculty/profile.html')


def schedule(request):
    return render(request, 'faculty/scheduleFaculty.html')
