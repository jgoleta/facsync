from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from core.decorators import role_required
from django.contrib import messages
from django.http import JsonResponse
from core.colleges import get_college_choices
from core.faculty import mark_inactive_faculty
from .forms import DeptHeadInviteForm, FacultySuperInviteForm
from core.models import User, College, FacultyInvite
from core.forms import CollegeForm
from core.services import (
    send_depthead_invite_email,
    send_depthead_deactivated_email,
    send_faculty_approved_email,
    send_faculty_invite_email,
    send_faculty_removed_email,
)
from faculty.models import FacultyProfile, ConsultationRequest

@login_required
@role_required('superadmin')
def invite_depthead(request):
    if request.method == 'POST':
        form = DeptHeadInviteForm(request.POST)
        if form.is_valid():
            invite = form.save(commit=False)
            invite.invited_by = request.user
            invite.save()
            send_depthead_invite_email(invite.email, invite.college, invite.title)
            return JsonResponse({'success': True, 'message': f"College Head invitation created for {invite.email}."})
        errors = ' '.join(
            error for error_list in form.errors.values() for error in error_list
        )
        return JsonResponse({'success': False, 'error': errors or 'Unable to create invitation.'}, status=400)
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)

@login_required
@role_required('superadmin')
def edit_depthead(request, user_id):
    depthead = get_object_or_404(User, id=user_id, role='depthead')
    if request.method == 'POST':
        new_role = request.POST.get('role')
        new_college = request.POST.get('college')
        new_title = request.POST.get('title')
        new_status = request.POST.get('account_status')

        if new_role not in dict(User.ROLE_CHOICES):
            return JsonResponse({'success': False, 'error': 'Invalid role selected.'}, status=400)
        if new_status not in ('active', 'deactivated'):
            return JsonResponse({'success': False, 'error': 'Invalid account status selected.'}, status=400)

        was_active = depthead.account_status == 'active'
        depthead.role = new_role
        depthead.college = new_college
        depthead.title = new_title
        depthead.account_status = new_status
        depthead.save()

        if was_active and new_status == 'deactivated':
            send_depthead_deactivated_email(depthead)

        return JsonResponse({
            'success': True,
            'message': f"Updated {depthead.username}.",
            'depthead': {
                'id': depthead.id,
                'name': depthead.get_full_name() or depthead.username,
                'email': depthead.email,
                'college': depthead.college,
                'title_display': depthead.get_title_display() or '—',
                'status': depthead.account_status,
                'status_display': depthead.get_account_status_display(),
            }
        })
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)


@login_required
@role_required('superadmin')
def superadmin_dashboard(request):
    colleges = College.objects.all().order_by('name')
    total_colleges = colleges.count()
    total_faculty = User.objects.filter(role='faculty', account_status='active').count()
    total_consultations = ConsultationRequest.objects.count()

    college_data = []
    for college in colleges:
        faculty_qs = FacultyProfile.objects.filter(college_id__iexact=college.code)
        faculty_ids = list(faculty_qs.values_list('faculty_id', flat=True))
        consultations = ConsultationRequest.objects.filter(faculty_id__in=faculty_ids)
        available_count = faculty_qs.filter(current_status='available').count()
        faculty_count = faculty_qs.count()
        college_data.append({
            'code': college.code,
            'name': college.name,
            'total_consultations': consultations.count(),
            'active_faculty': faculty_count,
            'availability_rate': round((available_count / faculty_count * 100), 0) if faculty_count else 0,
        })

    return render(request, 'superadmin/superadminDashboard.html', {
        'total_colleges': total_colleges,
        'total_faculty': total_faculty,
        'total_consultations': total_consultations,
        'colleges': colleges,
        'college_data_json': college_data,
    })

@login_required
@role_required('superadmin')
def manage_colleges(request):
    colleges = College.objects.all().order_by('name')

    #dictionary mapping college codes to their respective college heads
    #use upper() to ensure that the college codes match regardless
    heads_by_college = {}
    depthead_qs = User.objects.filter(role='depthead').exclude(college='').exclude(college__isnull=True)
    for u in depthead_qs:
        key = u.college.upper()
        heads_by_college.setdefault(key, []).append(u)

    for college in colleges:
        college.head_users = heads_by_college.get(college.code.upper(), [])

    return render(request, 'superadmin/manageColleges.html', {
        'colleges': colleges,
    })

@login_required
@role_required('superadmin')
def manage_admins(request):
    depthead_accounts = User.objects.filter(role='depthead')
    return render(request, 'superadmin/manageAdmins.html', {
        'depthead_accounts': depthead_accounts,
        'dept_head_form': DeptHeadInviteForm(),
        'role_choices': User.ROLE_CHOICES,
        'title_choices': User.TITLE_CHOICES,
    })

@login_required
@role_required('superadmin')
def manage_faculty(request):
    faculty_users = list(User.objects.filter(
        role='faculty',
    ).select_related('faculty_profile').order_by(
        'college', 'first_name', 'last_name', 'username'
    ))
    mark_inactive_faculty(faculty_users)

    return render(request, 'superadmin/manageFaculty.html', {
        'pending_faculty': [u for u in faculty_users if u.account_status == 'pending'],
        'active_faculty': [u for u in faculty_users if u.account_status == 'active'],
        'college_choices': get_college_choices(),
    })

@login_required
def manage_students(request):
    student_accounts = User.objects.filter(role='student')
    return render(request, 'superadmin/manageStudents.html', {
        'student_accounts': student_accounts
    })


@login_required
def remove_student_superadmin(request, user_id):
    student_user = get_object_or_404(User, id=user_id, role='student')
    if request.method == 'POST':
        name = student_user.get_full_name() or student_user.username
        student_user.delete()
        return JsonResponse({'success': True, 'message': f"{name} removed."})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)

@login_required
@role_required('superadmin')
def create_college(request):
    if request.method == 'POST':
        form = CollegeForm(request.POST)
        if form.is_valid():
            college = form.save()
            messages.success(request, f"College '{college.name}' created with code {college.code}.")
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
    return redirect('superadmin:manage_colleges')

@login_required
@role_required('superadmin')
def edit_college(request, college_id):
    college = get_object_or_404(College, id=college_id)
    if request.method == 'POST':
        form = CollegeForm(request.POST, instance=college)
        if form.is_valid():
            form.save()
            messages.success(request, f"College '{college.name}' updated.")
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
    return redirect('superadmin:manage_colleges')

@login_required
@role_required('superadmin')
def delete_college(request, college_id):
    college = get_object_or_404(College, id=college_id)
    if request.method == 'POST':
        name = college.name
        college.delete()
        messages.success(request, f"College '{name}' removed.")
    return redirect('superadmin:manage_colleges')



@login_required
@role_required('superadmin')
def invite_faculty_superadmin(request):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if request.method == 'POST':
        requested_email = request.POST.get('email', '').strip()
        used_invite = FacultyInvite.objects.filter(
            email__iexact=requested_email,
            used=True,
        ).first()
        form = FacultySuperInviteForm(request.POST, instance=used_invite)
        if form.is_valid():
            invite = form.save(commit=False)
            invite.invited_by = request.user
            invite.used = False
            invite.save()
            send_faculty_invite_email(invite.email, invite.college)
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': f"Invitation created for {invite.email}.",
                }, status=201)
            messages.success(request, f"Invitation created for {invite.email}.")
        else:
            errors = ' '.join(
                error for error_list in form.errors.values() for error in error_list
            )
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'error': errors or 'Unable to create the faculty invitation.',
                }, status=400)
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
    return redirect('superadmin:manage_faculty')


@login_required
@role_required('superadmin')
def approve_faculty_superadmin(request, user_id):
    faculty_user = get_object_or_404(
        User, id=user_id, role='faculty', account_status='pending'
    )
    if request.method == 'POST':
        faculty_user.account_status = 'active'
        faculty_user.save()
        send_faculty_approved_email(faculty_user)
        return JsonResponse({
            'success': True,
            'message': f"{faculty_user.get_full_name() or faculty_user.username} approved.",
        })
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)


@login_required
@role_required('superadmin')
def decline_faculty_superadmin(request, user_id):
    faculty_user = get_object_or_404(
        User, id=user_id, role='faculty', account_status='pending'
    )
    if request.method == 'POST':
        faculty_user.account_status = 'declined'
        faculty_user.save()
        return JsonResponse({
            'success': True,
            'message': f"{faculty_user.get_full_name() or faculty_user.username} declined.",
        })
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)


@login_required
@role_required('superadmin')
def remove_faculty_superadmin(request, user_id):
    faculty_user = get_object_or_404(
        User, id=user_id, role='faculty', account_status='active'
    )
    if request.method == 'POST':
        name = faculty_user.get_full_name() or faculty_user.username
        email = faculty_user.email
        faculty_user.delete()
        send_faculty_removed_email(email, name)
        return JsonResponse({'success': True, 'message': f"{name} removed."})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)

