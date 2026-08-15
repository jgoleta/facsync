from .models import User
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from faculty.models import FacultyProfile
from .forms import StudentProfileForm, FacultyRegistrationForm, FacultyProfileSetupForm
from django.contrib.auth import login as auth_login
from django.http import Http404
from allauth.socialaccount.models import SocialAccount

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
        return redirect('depthead:admin_dashboard')
    elif user.role == 'superadmin':
        return redirect('superadmin:superadmin_dashboard')

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

@login_required
def faculty_profile_setup(request):
    if request.method == 'POST':
        form = FacultyProfileSetupForm(request.POST)
        if form.is_valid():
            FacultyProfile.objects.create(
                faculty_id=form.cleaned_data['faculty_id'],
                user=request.user,
                department_id=request.user.department,
                office_location=form.cleaned_data['office_location'],
            )
            request.user.profile_completed = True
            request.user.save()
            return redirect('faculty:dashboard')
    else:
        form = FacultyProfileSetupForm()

    return render(request, 'core/facultyProfileSetup.html', {'form': form})

def faculty_pending_registration(request):
    email = request.session.get('pending_faculty_email', '')
    name = request.session.get('pending_faculty_name', '')

    if not email:
        return redirect('core:register')

    if request.method == 'POST':
        form = FacultyRegistrationForm(request.POST)
        if form.is_valid():
            name_parts = name.split(' ', 1)
            first_name = name_parts[0] if name_parts else ''
            last_name = name_parts[1] if len(name_parts) > 1 else ''

            user = User.objects.create(
                username=email,
                email=email,
                first_name=first_name,
                last_name=last_name,
                role='faculty',
                account_status='pending',
                department=form.cleaned_data['department'],
                profile_completed=True,
            )

            pending_uid = request.session.pop('pending_faculty_uid', None)
            if pending_uid:
                SocialAccount.objects.create(
                    user=user,
                    provider='google',
                    uid=pending_uid,
                    extra_data={'email': email, 'name': name},
                )

            FacultyProfile.objects.create(
                faculty_id=form.cleaned_data['faculty_id'],
                user=user,
                department_id=form.cleaned_data['department'],
                office_location=form.cleaned_data['office_location'],
            )

            del request.session['pending_faculty_email']
            del request.session['pending_faculty_name']

            return redirect('core:pending_approval_notice')
    else:
        form = FacultyRegistrationForm(initial={'email': email, 'name': name})

    return render(request, 'core/facultyPendingRegistration.html', {
        'form': form,
        'email': email,
        'name': name,
    })


def pending_approval_notice(request):
    return render(request, 'core/pendingApproval.html')

def dev_login_as(request, user_id):
    if not settings.DEBUG:
        raise Http404()
    user = get_object_or_404(User, id=user_id)
    auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    return redirect('core:post_login_redirect')