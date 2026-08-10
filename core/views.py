from django.shortcuts import render, redirect

def landing_page(request):
    return render(request, 'core/landingPage.html')

def login_page(request):
    return render(request, 'core/loginPage.html')

def register_page(request):
    return render(request, 'core/registerPage.html')

def dashboard_public(request):
    return render(request, 'core/dashboardPublic.html')

def register_student(request):
    request.session['registration_role'] = 'student'
    return redirect('google_login')

def register_faculty(request):
    request.session['registration_role'] = 'faculty'
    return redirect('google_login')

def faculty_pending_registration(request):
    email = request.session.get('pending_faculty_email', '')
    return render(request, 'core/facultyPendingRegistration.html', {'email': email})