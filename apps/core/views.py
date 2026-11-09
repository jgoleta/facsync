import json
from datetime import timezone as dt_timezone
from django.utils import timezone
from .models import User, OfficeClosure
from .department_access import faculty_closed
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
from apps.core.colleges import get_college_label
from .decorators import role_required
from django.views.decorators.cache import never_cache

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

STATUS_DISPLAY_MAP = {
    'not_set': ('not-set', 'status-not-set'),
    'available': ('available', 'status-available'),
    'busy': ('busy', 'status-busy'),
    'virtual_only': ('virtual', 'status-virtual'),
    'on_leave': ('on-leave', 'status-on-leave'),
    'unavailable': ('unavailable', 'status-unavailable'),
}

STATUS_NOTE_DEFAULTS = {
    'not_set': 'Not set (default status)',
    'available': 'Available now',
    'busy': 'Currently busy',
    'virtual_only': 'Virtual consultation available',
    'on_leave': 'On leave',
    'unavailable': 'Unavailable',
}

@login_required
@never_cache
def dashboard_public(request):

    closures = OfficeClosure.objects.filter(is_closed=True)
    if request.user.role == 'depthead':
        from apps.depthead.scope import managed_departments
        closures = closures.filter(department__in=managed_departments(request.user))

    closure_list = [
        {
            'college_name': c.department.name if c.department_id else get_college_label(c.college),
            'reason': c.reason,
            'closure_start': c.closure_start,
            'closure_end': c.closure_end,
        }
        for c in closures
    ]

    faculty_profiles = (
        FacultyProfile.objects
        .select_related('user')
        .filter(user__account_status='active')
    )
    if request.user.role == 'depthead':
        faculty_profiles = faculty_profiles.filter(user__department__in=managed_departments(request.user))

    faculty_cards = []
    for profile in faculty_profiles:
        status_key = profile.current_status
        data_status, status_class = STATUS_DISPLAY_MAP.get(status_key, ('available', 'status-available'))
        is_college_closed = faculty_closed(profile)
        faculty_cards.append({
            'id': profile.faculty_id,
            'name': profile.user.get_full_name() or profile.user.username,
            'photo_url': profile.user.avatar_url,
            'college_name': get_college_label(profile.college_id),
            'data_status': data_status,
            'status_class': status_class,
            'status_label': profile.get_current_status_display(),
            'status_note': 'College closed' if is_college_closed else (profile.status_note or STATUS_NOTE_DEFAULTS.get(status_key, '')),
            'last_updated_iso': profile.status_updated_at.isoformat() if profile.status_updated_at else '',
            'last_updated_display': profile.status_updated_at.strftime('%Y-%m-%d %H:%M') if profile.status_updated_at else 'Not yet updated',
            'is_college_closed': is_college_closed,
        })

    return render(request, 'core/dashboardPublic.html', {
        'faculty_cards': faculty_cards,
        'closures': closure_list,
        'college_choices': COLLEGE_CHOICES,
    })

@login_required
@require_http_methods(['GET', 'POST', 'DELETE'])
def notifications_api(request):
    if request.user.role not in {'student', 'faculty', 'officeadmin'}:
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
    request.session['registration_role'] = 'student'
    return redirect('google_login')

@login_required
def post_login_redirect(request):
    user = request.user

    if user.role == 'systemadmin':
        return redirect('systemadmin:manage_schools')

    if not user.profile_completed:
        if user.role == 'student':
            return redirect('core:student_profile_setup')
        elif user.role in {'faculty', 'officeadmin'}:
            return redirect('core:faculty_profile_setup')

    if user.role == 'student':
        return redirect('students:home')
    elif user.role == 'faculty':
        return redirect('faculty:dashboard')
    elif user.role == 'depthead':
        return redirect('depthead:admin_dashboard')
    elif user.role == 'officeadmin':
        return redirect('depthead:admin_dashboard')
    elif user.role == 'superadmin':
        return redirect('superadmin:superadmin_dashboard')

    return redirect('core:landing')

@login_required
@role_required('student')
def student_profile_setup(request):
    if request.method == 'POST':
        from django.db import transaction
        from .models import School
        with transaction.atomic():
            school = School.objects.select_for_update().get(pk=request.user.school_id)
            request.user.school = school
            form = StudentProfileForm(request.POST, instance=request.user, school=school)
            if form.is_valid():
                user = form.save(commit=False)
                user.profile_completed = True
                user.save()
                return redirect('students:home')
    else:
        form = StudentProfileForm(instance=request.user)

    from .education import LEVELS, YEAR_CHOICES
    from .models import Department
    return render(request, 'core/studentProfileSetup.html', {'form': form, 'year_choices': YEAR_CHOICES,
        'single_level_label': LEVELS.get(request.user.school.educational_levels[0]) if len(request.user.school.educational_levels) == 1 else None,
        'department_colleges': {str(d.pk): d.college.name if d.college else 'No college' for d in
            Department.objects.filter(school=request.user.school, is_active=True).select_related('college')}})

@login_required
@role_required('faculty')
def faculty_profile_setup(request):
    destination = 'depthead:admin_dashboard' if request.user.role == 'officeadmin' else 'faculty:dashboard'
    if FacultyProfile.objects.filter(user=request.user).exists():
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
