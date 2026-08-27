import json
from datetime import timezone as dt_timezone
from django.utils import timezone
from .models import User, OfficeClosure
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from faculty.models import FacultyProfile
from .forms import StudentProfileForm, FacultyRegistrationForm, FacultyProfileSetupForm, COLLEGE_CHOICES
from django.contrib.auth import login as auth_login
from django.http import Http404
from allauth.socialaccount.models import SocialAccount
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .models import Notification
from core.colleges import get_college_label

def landing_page(request):
    return render(request, 'core/landingPage.html')

def login_page(request):
    return render(request, 'core/loginPage.html')

def register_page(request):
    return render(request, 'core/registerPage.html')

STATUS_DISPLAY_MAP = {
    'available': ('available', 'status-available'),
    'busy': ('busy', 'status-busy'),
    'virtual_only': ('virtual', 'status-virtual'),
    'on_leave': ('on-leave', 'status-on-leave'),
    'unavailable': ('unavailable', 'status-unavailable'),
}

STATUS_NOTE_DEFAULTS = {
    'available': 'Available now',
    'busy': 'Currently busy',
    'virtual_only': 'Virtual consultation available',
    'on_leave': 'On leave',
    'unavailable': 'Unavailable',
}

def dashboard_public(request):

    closures = OfficeClosure.objects.filter(is_closed=True)
    closed_college_codes = set(closures.values_list('college', flat=True))

    closure_list = [
        {
            'college_name': get_college_label(c.college),
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

    faculty_cards = []
    for profile in faculty_profiles:
        status_key = profile.current_status
        data_status, status_class = STATUS_DISPLAY_MAP.get(status_key, ('available', 'status-available'))
        is_college_closed = profile.college_id in closed_college_codes
        faculty_cards.append({
            'id': profile.faculty_id,
            'name': profile.user.get_full_name() or profile.user.username,
            'college_name': get_college_label(profile.college_id),
            'data_status': data_status,
            'status_class': status_class,
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
    if request.user.role not in {'student', 'faculty'}:
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
    request.session['registration_role'] = 'student'
    return redirect('google_login')

def register_faculty(request):
    request.session['registration_role'] = 'faculty'
    return redirect('google_login')

@login_required
def post_login_redirect(request):
    user = request.user

    if not user.profile_completed:
        if user.role == 'student':
            return redirect('core:student_profile_setup')
        elif user.role == 'faculty':
            return redirect('core:faculty_profile_setup')

    if user.role == 'student':
        return redirect('students:home')
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
            return redirect('students:home')
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
                college_id=request.user.college,
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
                college=form.cleaned_data['college'],
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
                college_id=form.cleaned_data['college'],
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


@login_required
def dev_login_as(request, user_id):
    if not settings.DEBUG:
        raise Http404()
    user = get_object_or_404(User, id=user_id)
    auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    return redirect('core:post_login_redirect')
