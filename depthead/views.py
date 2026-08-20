from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from core.decorators import role_required
from core.models import User, FacultyInvite, OfficeClosure, DepartmentAnnouncement, Department
from core.forms import DepartmentAnnouncementForm, DepartmentDescriptionForm
from django.contrib import messages
from .forms import FacultyInviteForm, OfficeClosureForm
from faculty.models import FacultyProfile
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from core.services import notify_department_users

@login_required
@role_required('depthead')
def pending_faculty_requests(request):
    pending_faculty = User.objects.filter(role='faculty', account_status='pending', department__iexact=request.user.department)
    active_faculty = User.objects.filter(role='faculty', account_status='active', department__iexact=request.user.department)
    return render(request, 'depthead/pendingFacultyRequests.html', {
        'pending_faculty': pending_faculty,
        'active_faculty': active_faculty,
    })


@login_required
@role_required('depthead')
def approve_faculty(request, user_id):
    faculty_user = get_object_or_404(User, id=user_id, role='faculty', account_status='pending', department__iexact=request.user.department)
    if request.method == 'POST':
        faculty_user.account_status = 'active'
        faculty_user.save()
        return JsonResponse({'success': True, 'message': f"{faculty_user.get_full_name() or faculty_user.username} approved."})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)


@login_required
@role_required('depthead')
def decline_faculty(request, user_id):
    faculty_user = get_object_or_404(User, id=user_id, role='faculty', account_status='pending', department__iexact=request.user.department)
    if request.method == 'POST':
        faculty_user.account_status = 'declined'
        faculty_user.save()
        return JsonResponse({'success': True, 'message': f"{faculty_user.get_full_name() or faculty_user.username} declined."})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)


@login_required
@role_required('depthead')
def invite_faculty(request):
    if request.method == 'POST':
        if not request.user.department:
            messages.error(request, "Your account has no department set. Contact a Super Admin.")
            return redirect('depthead:pending_faculty_requests')
        form = FacultyInviteForm(request.POST)
        if form.is_valid():
            invite = form.save(commit=False)
            invite.department = request.user.department
            invite.invited_by = request.user
            invite.save()
            messages.success(request, f"Invitation created for {invite.email}.")
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
    return redirect('depthead:pending_faculty_requests')

@login_required
@role_required('depthead')
def remove_faculty(request, user_id):
    faculty_user = get_object_or_404(User, id=user_id, role='faculty', account_status='active', department__iexact=request.user.department)
    if request.method == 'POST':
        name = faculty_user.get_full_name() or faculty_user.username
        faculty_user.delete()
        return JsonResponse({'success': True, 'message': f"{name} removed."})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)


@login_required
@role_required('depthead')
def admin_dashboard(request):
    return render(request, 'depthead/adminDashboard.html')

@login_required
@role_required('depthead')
def admin_faculty(request):
    return render(request, 'depthead/adminFaculty.html')

@login_required
@role_required('depthead')
def student_behavior(request):
    return render(request, 'depthead/studentBehavior.html')

STATUS_LABELS = {
    'available': ('Available', 'status-available'),
    'busy': ('Busy', 'status-busy'),
    'virtual_only': ('Virtual Only', 'status-virtual'),
    'on_leave': ('On Leave', 'status-on-leave'),
    'unavailable': ('Unavailable', 'status-unavailable'),
}

@login_required
@role_required('depthead')
def faculty_monitoring(request):
    profiles = FacultyProfile.objects.select_related('user').filter(
        user__role='faculty',
        user__account_status='active',
        department_id__iexact=request.user.department,
    )
    faculty_list = []
    for profile in profiles:
        label, css_class = STATUS_LABELS.get(profile.current_status, ('Unknown', 'status-unavailable'))
        faculty_list.append({
            'name': profile.user.get_full_name() or profile.user.username,
            'status_label': label,
            'status_class': css_class,
            'updated_at': profile.status_updated_at,
        })
    return render(request, 'depthead/facultyMonitoring.html', {'faculty_list': faculty_list})

@login_required
@role_required('depthead')
def department_settings(request):
    closure, _ = OfficeClosure.objects.get_or_create(
        department__iexact=request.user.department,
        defaults={'department': request.user.department}
    )
    if request.method == 'POST':
        form = OfficeClosureForm(request.POST, instance=closure)
        if form.is_valid():
            closure = form.save(commit=False)
            closure.department = request.user.department
            closure.updated_by = request.user
            closure.save()
            return JsonResponse({'success': True})
        errors = ' '.join(
            error for error_list in form.errors.values() for error in error_list
        )
        return JsonResponse({'success': False, 'error': errors or 'Unable to save closure settings.'})
    else:
        form = OfficeClosureForm(instance=closure)

    department_announcements = DepartmentAnnouncement.objects.filter(
        department__iexact=request.user.department,
        expiry__gt=timezone.now()
    )

    department = Department.objects.filter(code__iexact=request.user.department).first()

    return render(request, 'depthead/departmentSettings.html', {
        'closure_form': form,
        'department_announcements': department_announcements,
        'department': department,
    })

@login_required
@role_required('depthead')
def peak_analytics(request):
    return render(request, 'depthead/peakAnalytics.html')

@login_required
@role_required('depthead')
def faculty_trends(request):
    return render(request, 'depthead/facultyTrends.html')

@login_required
@role_required('depthead')
@require_POST
def create_announcement(request):
    if not request.user.department:
        return JsonResponse(
            {'success': False, 'error': "Your account has no department set. Contact a Super Admin."},
            status=400
        )

    form = DepartmentAnnouncementForm(request.POST)
    if not form.is_valid():
        errors = [e for error_list in form.errors.values() for e in error_list]
        return JsonResponse({'success': False, 'error': ' '.join(errors)}, status=400)

    announcement = form.save(commit=False)
    announcement.department = request.user.department
    announcement.posted_by = request.user
    announcement.save()
    notify_department_users(
        department=announcement.department,
        notification_type='announcement',
        title='Department announcement',
        message=announcement.message,
        url='',
        exclude_user_id=request.user.id,
    )

    return JsonResponse({
        'success': True,
        'announcement': {
            'message': announcement.message,
            'posted_at': announcement.posted_at.strftime('%b %d, %Y'),
            'expiry': announcement.expiry.strftime('%b %d, %Y'),
        }
    })

@login_required
@role_required('depthead')
def edit_department_description(request):
    department = Department.objects.filter(code__iexact=request.user.department).first()
    if not department:
        messages.error(request, "Your department could not be found. Contact a Super Admin.")
        return redirect('depthead:department_settings')

    if request.method == 'POST':
        form = DepartmentDescriptionForm(request.POST, instance=department)
        if form.is_valid():
            form.save()
            messages.success(request, "Department description updated.")
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)

    return redirect('depthead:department_settings')