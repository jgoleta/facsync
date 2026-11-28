import json
from datetime import timezone as dt_timezone
from django.utils import timezone
from .models import User
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from apps.faculty.models import FacultyProfile
from .forms import StudentProfileForm, FacultyProfileSetupForm, COLLEGE_CHOICES
from django.contrib.auth import login as auth_login
from django.http import Http404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .models import Notification
from .decorators import role_required
from .role_access import active_role, available_roles, has_role

def active_announcements(request):
    """Keep college announcements unavailable to visitors of the public dashboard."""
    return JsonResponse({'announcements': []})


def landing_page(request):
    return render(request, 'core/landingPage.html')

def terms_of_service(request):
    return render(request, 'core/terms_of_service.html')

def privacy_policy(request):
    return render(request, 'core/privacy_policy.html')

def login_page(request):
    request.session.pop('school_request_intent', None)
    return render(request, 'core/loginPage.html')

def register_page(request):
    request.session.pop('school_request_intent', None)
    return render(request, 'core/registerPage.html')

def dashboard_public(request):
    return render(request, 'core/dashboardPublic.html', {
        'college_choices': COLLEGE_CHOICES,
    })

@login_required
@require_http_methods(['GET', 'POST', 'DELETE'])
def notifications_api(request):
    if not any(has_role(request.user, role) for role in {'student', 'faculty', 'officeadmin'}):
        return JsonResponse({'error': 'Notifications are unavailable for this account.'}, status=403)

    if request.method == 'GET':
        notifications = Notification.objects.filter(recipient=request.user)[:50]
        return JsonResponse({
            'unread_count': Notification.objects.filter(
                recipient=request.user,
                is_read=False,
            ).count(),
            'notifications': [
                {
                    'id': notification.id,
                    'type': notification.notification_type,
                    'title': notification.title,
                    'message': notification.message,
                    'url': notification.url,
                    'is_read': notification.is_read,
                    'created_at': notification.created_at.isoformat(),
                }
                for notification in notifications
            ],
        })

    if request.method == 'POST':
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except (TypeError, ValueError, UnicodeDecodeError):
            payload = {}
        queryset = Notification.objects.filter(recipient=request.user, is_read=False)
        notification_id = payload.get('notification_id')
        if notification_id:
            queryset = queryset.filter(pk=notification_id)
        updated = queryset.update(is_read=True)
        return JsonResponse({'updated': updated})

    try:
        notification_id = json.loads(request.body.decode('utf-8') or '{}').get('notification_id')
    except (TypeError, ValueError, UnicodeDecodeError):
        notification_id = None
    if not notification_id:
        return JsonResponse({'error': 'notification_id is required.'}, status=400)
    deleted, _ = Notification.objects.filter(
        recipient=request.user,
        pk=notification_id,
    ).delete()
    return JsonResponse({'deleted': deleted})

def register_student(request):
    request.session.pop('school_request_intent', None)
    request.session.pop('student_profile_setup_allowed', None)
    request.session['registration_role'] = 'student'
    return redirect('google_login')

@login_required
def post_login_redirect(request):
    user = request.user

    roles = available_roles(user)
    if not roles:
        return render(request, 'core/roleAccessUnavailable.html', status=403)
    stored_role = request.session.get('active_role')
    selected = active_role(request)
    if len(roles) > 1 and stored_role not in {role for role, _ in roles}:
        request.session.pop('active_role', None)
        return redirect('core:select_role')

    if selected == 'systemadmin':
        return redirect('systemadmin:manage_school')

    if not user.profile_completed:
        if selected == 'student':
            return redirect('core:student_profile_setup')
        elif selected in {'faculty', 'officeadmin'}:
            return redirect('core:faculty_profile_setup')

    if selected == 'student':
        return redirect('students:home')
    elif selected == 'faculty':
        return redirect('faculty:dashboard')
    elif selected == 'depthead':
        return redirect('depthead:admin_dashboard')
    elif selected == 'officeadmin':
        return redirect('depthead:admin_dashboard')
    elif selected == 'superadmin':
        return redirect('superadmin:superadmin_dashboard')

    return redirect('core:landing')


@login_required
def select_role(request):
    roles = available_roles(request.user)
    if len(roles) <= 1:
        return redirect('core:post_login_redirect')
    if request.method == 'POST':
        selected = request.POST.get('role')
        if any(role == selected for role, _ in roles):
            request.session['active_role'] = selected
            return redirect('core:post_login_redirect')
    return render(request, 'core/selectRole.html', {'roles': roles})


@login_required
def switch_role(request):
    if request.method != 'POST':
        return redirect('core:post_login_redirect')
    selected = request.POST.get('role')
    if any(role == selected for role, _ in available_roles(request.user)):
        request.session['active_role'] = selected
    return redirect('core:post_login_redirect')

@login_required
@role_required('student')
def student_profile_setup(request):
    if request.user.profile_completed or not request.session.get('student_profile_setup_allowed'):
        return redirect('students:profile')
    from .models import School
    school = School.objects.get(pk=request.user.school_id)
    if request.method == 'POST':
        from django.db import transaction
        with transaction.atomic():
            school = School.objects.select_for_update().get(pk=request.user.school_id)
            request.user.school = school
            form = StudentProfileForm(request.POST, instance=request.user, school=school)
            if form.is_valid():
                user = form.save(commit=False)
                user.profile_completed = True
                user.save()
                request.session.pop('student_profile_setup_allowed', None)
                return redirect('students:home')
    else:
        form = StudentProfileForm(instance=request.user, school=school)

    from .education import LEVELS, YEAR_CHOICES
    from .models import Department
    return render(request, 'core/studentProfileSetup.html', {'form': form, 'year_choices': YEAR_CHOICES,
        'single_level_label': LEVELS.get(request.user.school.educational_levels[0]) if len(request.user.school.educational_levels) == 1 else None,
        'department_colleges': {str(d.pk): d.college.name if d.college else 'No college' for d in
            form.fields['department'].queryset}})

@login_required
@role_required('faculty')
def faculty_profile_setup(request):
    destination = 'depthead:admin_dashboard' if has_role(request.user, 'officeadmin') and not has_role(request.user, 'faculty') else 'faculty:dashboard'
    if FacultyProfile.objects.filter(user=request.user).exists() or not request.session.get('faculty_profile_setup_allowed'):
        return redirect(destination)
    if request.method == 'POST':
        form = FacultyProfileSetupForm(request.POST)
        if form.is_valid():
            from django.db import IntegrityError, transaction
            try:
                with transaction.atomic():
                    user = User.objects.select_for_update().get(pk=request.user.pk)
                    # Another tab may have completed setup after validation.
                    if not FacultyProfile.objects.filter(user=user).exists():
                        FacultyProfile.objects.create(
                            faculty_id=form.cleaned_data['faculty_id'], user=user,
                            college_id=user.college, office_location=form.cleaned_data['office_location'],
                        )
                    user.profile_completed = True
                    user.save(update_fields=['profile_completed'])
                request.session.pop('faculty_profile_setup_allowed', None)
                return redirect(destination)
            except IntegrityError:
                # A different account may have claimed this identifier after
                # validation. Never expose its identity or return a server error.
                form.add_error('faculty_id', 'This faculty identifier is unavailable. Please choose another.')
    else:
        form = FacultyProfileSetupForm()

    return render(request, 'core/facultyProfileSetup.html', {'form': form})

@login_required
@role_required('systemadmin')
def dev_login_as(request, user_id):
    if not settings.DEBUG:
        raise Http404()
    user = get_object_or_404(User, id=user_id)
    auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    return redirect('core:post_login_redirect')
