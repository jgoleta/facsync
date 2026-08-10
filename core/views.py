from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .forms import StudentProfileForm

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

@login_required
def post_login_redirect(request):
    user = request.user

    if not user.profile_completed:
        if user.role == 'student':
            return redirect('core:student_profile_setup')
        elif user.role == 'faculty':
            return redirect('core:faculty_profile_setup')

    if user.role == 'student':
        return redirect('students:dashboard')
    elif user.role == 'faculty':
        return redirect('faculty:dashboard')
    elif user.role == 'depthead':
        return redirect('depthead:dashboard')
    elif user.role == 'superadmin':
        return redirect('superadmin:dashboard')

    return redirect('core:landing')

@login_required
def student_profile_setup(request):
    if request.method == 'POST':
        form = StudentProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            user = form.save(commit=False)
            user.profile_completed = True
            user.save()
            return redirect('students:dashboard')
    else:
        form = StudentProfileForm(instance=request.user)

    return render(request, 'core/studentProfileSetup.html', {'form': form})