from apps.core.account_lifecycle import access_response, with_consultation_counts
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from apps.core.decorators import role_required
from django.contrib import messages
from django.http import JsonResponse
import logging
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from apps.core.colleges import get_college_choices, get_unit_choices
from apps.core.faculty import mark_inactive_faculty
from .forms import DeptHeadInviteForm, FacultySuperInviteForm, OfficeAdminInviteForm, HeadAssignmentForm
from .assignment_services import lock_departments
from .department_views import form_error
from apps.core.models import User, College, Department, DeptHeadInvite, Office, FacultyInvite, OfficeAdminInvite, OfficeClosure, CollegeAnnouncement, School
from apps.core.forms import CollegeForm, OfficeForm
from apps.core.services import (
    send_depthead_invite_email,
    send_depthead_deactivated_email,
    send_faculty_invite_email,
    send_faculty_removed_email,
    send_office_admin_invite_email,
)
from apps.faculty.models import FacultyProfile, ConsultationRequest

logger = logging.getLogger(__name__)


@login_required
@role_required('superadmin')
def school_settings(request):
    from .forms import SchoolDetailsForm, SchoolEducationForm
    details_action = request.method == 'POST' and request.POST.get('action') == 'school_details'
    domain = request.user.school.domains.order_by('pk').first()
    details_form = SchoolDetailsForm(request.POST if details_action else None, school=request.user.school,
        initial={'name': request.user.school.name, 'domain': domain.domain if domain else ''})
    form = SchoolEducationForm(request.POST if request.method == 'POST' and not details_action else None,
        initial={'educational_levels': request.user.school.educational_levels})
    if request.method == 'POST':
        if details_action:
            if details_form.is_valid():
                try:
                    request.user.school.set_school_details(actor=request.user, **details_form.cleaned_data)
                except ValidationError as error:
                    details_form.add_error(None, error.messages)
                except IntegrityError:
                    details_form.add_error('domain', 'This domain is already assigned to another school.')
                else:
                    return JsonResponse({'success': True, 'message': 'School details updated.'})
            return form_error(details_form)
        if form.is_valid():
            try:
                request.user.school.set_educational_levels(form.cleaned_data['educational_levels'], actor=request.user)
            except ValidationError as error:
                form.add_error(None, error)
            else:
                return JsonResponse({'success': True, 'message': 'School educational levels updated.'})
        return form_error(form)
    return render(request, 'schooladmin/schoolSettings.html', {'form': form, 'details_form': details_form})


def _send_saved_email(sender, *args):
    try:
        sender(*args)
        return True
    except Exception as error:
        logger.warning('admin_assignment_email_failed category=%s', type(error).__name__)
        return False


def _save_head_invitation(request, invite=None):
    try:
        with transaction.atomic():
            if invite is not None:
                invite = get_object_or_404(DeptHeadInvite.objects.select_for_update(), pk=invite.pk, used=False)
            form = DeptHeadInviteForm(request.POST, instance=invite)
            if not form.is_valid():
                return form_error(form)
            departments = lock_departments(form.cleaned_data['departments'], request.user.school)
            saved = form.save(commit=False)
            if not saved.pk:
                saved.invited_by = request.user
            saved.save()
            saved.departments.set(departments)
    except (ValidationError, IntegrityError) as error:
        message = ' '.join(error.messages) if isinstance(error, ValidationError) else 'This invitation already exists. Refresh and try again.'
        return JsonResponse({'success': False, 'error': message}, status=400)
    sent = _send_saved_email(send_depthead_invite_email, saved.email, ', '.join(d.name for d in departments), saved.title)
    return JsonResponse({'success': True, 'email_sent': sent, 'message':
        'Head invitation saved and emailed.' if sent else 'Head invitation saved, but the email could not be sent.'})

@login_required
@role_required('superadmin')
def invite_depthead(request):
    if request.method == 'POST':
        return _save_head_invitation(request)
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)

@login_required
@role_required('superadmin')
def edit_depthead(request, user_id):
    if request.method == 'POST':
        if request.POST.get('role', 'depthead') != 'depthead':
            return JsonResponse({'success': False, 'error': 'Use this form to manage head assignments, not change account roles.'}, status=400)
        form = HeadAssignmentForm(request.POST, school=request.user.school)
        if not form.is_valid():
            return form_error(form)
        try:
            with transaction.atomic():
                departments = lock_departments(form.cleaned_data['departments'], request.user.school)
                depthead = get_object_or_404(User.objects.select_for_update(), pk=user_id, role='depthead')
                was_active = depthead.is_active and depthead.account_status == 'active'
                depthead.title = form.cleaned_data['title']
                depthead.account_status = form.cleaned_data['account_status']
                depthead.is_active = depthead.account_status == 'active'
                first = departments[0]
                depthead.college = first.college.code if first.college else ''
                depthead.save(update_fields=['title', 'account_status', 'is_active', 'college'])
                depthead.managed_departments.set(departments)
        except ValidationError as error:
            return JsonResponse({'success': False, 'error': ' '.join(error.messages)}, status=400)
        sent = True
        if was_active and depthead.account_status == 'deactivated' and depthead.email:
            sent = _send_saved_email(send_depthead_deactivated_email, depthead)
        return JsonResponse({'success': True, 'email_sent': sent, 'message':
            'Head assignments saved.' if sent else 'Head assignments saved, but the deactivation email could not be sent.'})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)


@login_required
@role_required('superadmin')
def edit_head_invite(request, invite_id):
    invite = get_object_or_404(DeptHeadInvite, pk=invite_id, used=False)
    if request.method == 'POST':
        return _save_head_invitation(request, invite)
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)


@login_required
@role_required('superadmin')
def remove_depthead(request, user_id):
    depthead = get_object_or_404(User, id=user_id, role='depthead')
    if request.method == 'POST':
        response = access_response(depthead, reactivate=request.POST.get('action') == 'reactivate')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return response
        messages.success(request, 'Account access updated. Consultation history is preserved.')
        return redirect('superadmin:manage_admins')
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)


@login_required
@role_required('superadmin')
def delete_depthead(request, user_id):
    depthead = get_object_or_404(User, id=user_id, role='depthead')
    if request.method == 'POST':
        try:
            with transaction.atomic():
                depthead.delete()
        except ProtectedError:
            return JsonResponse({'success': False, 'error':
                'This Department Head has linked consultation history or records and cannot be removed. Deactivate the account instead.'}, status=409)
        return JsonResponse({'success': True, 'message': 'Department Head account removed.'})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)


@login_required
@role_required('superadmin')
def remove_office_admin(request, user_id):
    office_admin = get_object_or_404(User, id=user_id, role='officeadmin')
    if request.method == 'POST':
        return access_response(office_admin, reactivate=request.POST.get('action') == 'reactivate')
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)


@login_required
@role_required('superadmin')
def delete_office_admin(request, user_id):
    office_admin = get_object_or_404(User, id=user_id, role='officeadmin')
    if request.method == 'POST':
        try:
            with transaction.atomic():
                office_admin.delete()
        except ProtectedError:
            return JsonResponse({'success': False, 'error':
                'This Office Admin has linked records and cannot be removed. Deactivate the account instead.'}, status=409)
        return JsonResponse({'success': True, 'message': 'Office Admin account removed.'})
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

    if not request.user.school.offers_college:
        departments = Department.objects.all().order_by('name')
        total_colleges = departments.count()
        college_data = []
        for department in departments:
            faculty_qs = FacultyProfile.objects.filter(user__department=department)
            count = faculty_qs.count()
            college_data.append({'code': department.code, 'name': department.name,
                'total_consultations': ConsultationRequest.objects.filter(faculty__in=faculty_qs).count(),
                'active_faculty': count,
                'availability_rate': round(faculty_qs.filter(current_status='available').count() / count * 100, 0) if count else 0})
        colleges = departments

    return render(request, 'schooladmin/schoolAdminDashboard.html', {
        'total_colleges': total_colleges,
        'total_faculty': total_faculty,
        'total_consultations': total_consultations,
        'colleges': colleges,
        'college_data_json': college_data,
    })

@login_required
@role_required('superadmin')
def manage_colleges(request):
    colleges = College.objects.all().prefetch_related('departments').order_by('name')
    from django.db.models import Count
    from .forms import DepartmentForm
    departments = Department.objects.select_related('college').annotate(
        member_count=Count('members', distinct=True), head_count=Count('head_assignments', distinct=True))
    colleges_page = Paginator(colleges, 8).get_page(request.GET.get('colleges_page'))
    departments_page = Paginator(departments, 8).get_page(request.GET.get('departments_page'))
    return render(request, 'schooladmin/manageAcademicUnits.html', {
        'colleges': colleges_page,
        'departments': departments_page,
        'department_form': DepartmentForm(),
    })

@login_required
@role_required('superadmin')
def manage_offices(request):
    offices = Office.objects.all().order_by('name')
    for office in offices:
        office.head_users = User.objects.filter(role='officeadmin', college__iexact=office.code)
    return render(request, 'schooladmin/manageOffices.html', {'offices': offices})

@login_required
@role_required('superadmin')
def manage_admins(request):
    depthead_accounts = list(with_consultation_counts(User.objects.filter(role='depthead')).prefetch_related('managed_departments__college'))
    for user in depthead_accounts:
        user.department_ids = ','.join(str(item.pk) for item in user.managed_departments.all())
        user.department_names = ', '.join(item.name for item in user.managed_departments.all())
        user.college_labels = ', '.join(sorted({item.college.name for item in user.managed_departments.all() if item.college}))
    invites = list(DeptHeadInvite.objects.filter(used=False).prefetch_related('departments__college'))
    for invite in invites:
        invite.department_ids = ','.join(str(item.pk) for item in invite.departments.all())
        invite.department_names = ', '.join(item.name for item in invite.departments.all())
        invite.invite_type = 'head'
    office_admin_accounts = list(User.objects.filter(role='officeadmin').order_by('email'))
    office_invites = list(OfficeAdminInvite.objects.filter(used=False).order_by('email'))
    for invite in office_invites:
        invite.invite_type = 'office'
    admin_invites = sorted(invites + office_invites, key=lambda invite: (invite.email or '').casefold())
    return render(request, 'schooladmin/manageAdmins.html', {
        'depthead_accounts': Paginator(depthead_accounts, 8).get_page(request.GET.get('depthead_page')),
        'admin_invites': Paginator(admin_invites, 8).get_page(request.GET.get('admin_invites_page')),
        'departments': Department.objects.filter(is_active=True).select_related('college'),
        'office_admin_accounts': Paginator(office_admin_accounts, 8).get_page(request.GET.get('office_admin_page')),
        'college_choices': get_college_choices(),
        'dept_head_form': DeptHeadInviteForm(),
        'role_choices': [choice for choice in User.ROLE_CHOICES if choice[0] in {'student', 'faculty', 'depthead'}],
        'title_choices': User.TITLE_CHOICES,
        'office_admin_form': OfficeAdminInviteForm(),
    })

@login_required
@role_required('superadmin')
def manage_faculty(request):
    faculty_users = list(with_consultation_counts(User.objects.filter(
        role='faculty',
    )).select_related('faculty_profile', 'department__college').order_by(
        'college', 'first_name', 'last_name', 'username'
    ))
    mark_inactive_faculty(faculty_users)
    offices = {office.code.casefold(): office for office in Office.objects.all()}
    for user in faculty_users:
        office = offices.get(str(user.college or '').casefold()) if not user.department_id else None
        user.unit_value = f'department:{user.department_id}' if user.department_id else f'office:{office.pk}' if office else ''
        user.unit_label = user.department.name if user.department_id else office.name if office else 'Not assigned'
        user.college_label = user.department.college.name if user.department_id and user.department.college else ''
        user.college_filter = str(user.department.college_id) if user.department_id and user.department.college_id else ''
    invites = list(FacultyInvite.objects.filter(used=False).select_related('department__college'))
    for invite in invites:
        office = offices.get(str(invite.college or '').casefold())
        invite.unit_label = invite.department.name if invite.department_id else office.name if office else invite.college

    return render(request, 'schooladmin/manageFaculty.html', {
        'active_faculty': Paginator(faculty_users, 12).get_page(request.GET.get('faculty_page')),
        'college_choices': get_unit_choices(),
        'faculty_invite_form': FacultySuperInviteForm(),
        'faculty_invites': Paginator(invites, 12).get_page(request.GET.get('faculty_invites_page')),
        'colleges': College.objects.all(),
    })

@login_required
@role_required('superadmin')
def manage_students(request):
    student_accounts = with_consultation_counts(User.objects.filter(role='student')).select_related('department__college')
    return render(request, 'schooladmin/manageStudents.html', {
        'student_accounts': Paginator(student_accounts, 12).get_page(request.GET.get('students_page'))
    })


@login_required
@role_required('superadmin')
def remove_student_superadmin(request, user_id):
    student_user = get_object_or_404(User, id=user_id, role='student')
    if request.method == 'POST':
        if request.POST.get('action') == 'delete':
            try:
                with transaction.atomic():
                    student_user.delete()
            except ProtectedError:
                return JsonResponse({'success': False, 'error':
                    'This student has consultation history and cannot be deleted. Deactivate the account instead; history will be preserved.'}, status=409)
            return JsonResponse({'success': True, 'message': 'Student account permanently removed.'})
        return access_response(student_user, reactivate=request.POST.get('action') == 'reactivate')
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)

@login_required
@role_required('superadmin')
def create_college(request):
    if not request.user.school.offers_college:
        return JsonResponse({'error': 'College is not an offered educational level.'}, status=403)
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
def create_office(request):
    if request.method == 'POST':
        form = OfficeForm(request.POST)
        if form.is_valid():
            office = form.save()
            messages.success(request, f"Office '{office.name}' created with code {office.code}.")
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
    return redirect('superadmin:manage_offices')

@login_required
@role_required('superadmin')
def delete_office(request, office_id):
    if request.method == 'POST':
        with transaction.atomic():
            get_object_or_404(School.objects.select_for_update(), pk=request.user.school_id, is_active=True)
            office = get_object_or_404(Office.objects.select_for_update(), id=office_id)
            code = office.code
            referenced = (
                User.objects.filter(college__iexact=code).exists()
                or FacultyProfile.objects.filter(college_id__iexact=code).exists()
                or FacultyInvite.objects.filter(college__iexact=code).exists()
                or DeptHeadInvite.objects.filter(college__iexact=code).exists()
                or OfficeAdminInvite.objects.filter(office__iexact=code).exists()
                or OfficeClosure.objects.filter(college__iexact=code).exists()
                or CollegeAnnouncement.objects.filter(college__iexact=code).exists()
            )
            if referenced:
                message = 'This office is still referenced by accounts, invitations or history. Keep it to preserve those records.'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': message}, status=409)
                messages.error(request, message)
            else:
                office.delete()
                messages.success(request, f"Office '{office.name}' removed.")
    return redirect('superadmin:manage_offices')

@login_required
@role_required('superadmin')
def invite_office_admin(request):
    if request.method == 'POST':
        try:
            with transaction.atomic():
                get_object_or_404(School.objects.select_for_update(), pk=request.user.school_id, is_active=True)
                email = request.POST.get('email', '').strip().lower()
                existing = OfficeAdminInvite.objects.filter(email__iexact=email, used=False,
                                                            office=request.POST.get('office')).first()
                form = OfficeAdminInviteForm(request.POST, instance=existing)
                if not form.is_valid():
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return form_error(form)
                    for errors in form.errors.values():
                        for error in errors:
                            messages.error(request, error)
                    return redirect('superadmin:manage_admins')
                if existing:
                    return _office_invite_result(request, 'This invitation already exists. Use Resend for the saved invitation.')
                invite = form.save(commit=False)
                invite.invited_by = request.user
                invite.save()
        except (ValidationError, IntegrityError):
            message = 'This email is already registered or has a pending invitation. Refresh the list before retrying.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': message}, status=400)
            messages.error(request, message)
            return redirect('superadmin:manage_admins')
        sent = _deliver_office_invite(invite)
        return _office_invite_result(request, 'Office Admin invitation saved and emailed.' if sent else
                                    'Invitation saved, but the email could not be sent. Use Resend to try delivery again.', sent)
    return redirect('superadmin:manage_admins')


def _deliver_office_invite(invite):
    if not (invite.email or '').strip():
        return False
    try:
        sent = bool(send_office_admin_invite_email(invite.email, invite.office))
        if not sent:
            logger.warning('office_admin_invite_email_not_accepted invite_id=%s', invite.pk)
        return sent
    except Exception as error:
        logger.warning('office_admin_invite_email_failed invite_id=%s category=%s', invite.pk, type(error).__name__)
        return False


def _office_invite_result(request, message, sent=None):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        result = {'success': True, 'message': message}
        if sent is not None:
            result['email_sent'] = sent
        return JsonResponse(result)
    (messages.warning if sent is False else messages.success)(request, message)
    return redirect('superadmin:manage_admins')


@login_required
@role_required('superadmin')
def resend_office_admin_invite(request, invite_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Only POST requests are allowed.'}, status=405)
    with transaction.atomic():
        get_object_or_404(School.objects.select_for_update(), pk=request.user.school_id, is_active=True)
        invite = get_object_or_404(OfficeAdminInvite.objects.select_for_update(), pk=invite_id, used=False)
        if (not Office.objects.filter(code__iexact=invite.office).exists()
                or User._base_manager.filter(email__iexact=invite.email).exists()):
            message = 'This invitation is no longer available. Refresh the account list.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': message}, status=400)
            messages.error(request, message)
            return redirect('superadmin:manage_admins')
    sent = _deliver_office_invite(invite)
    return _office_invite_result(request, 'Invitation emailed.' if sent else
                                'Invitation remains saved, but the email could not be sent.', sent)

@login_required
@role_required('superadmin')
def edit_college(request, college_id):
    if not request.user.school.offers_college:
        return JsonResponse({'error': 'College is not an offered educational level.'}, status=403)
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
    if not request.user.school.offers_college:
        return JsonResponse({'error': 'College is not an offered educational level.'}, status=403)
    college = get_object_or_404(College, id=college_id)
    if request.method == 'POST':
        name = college.name
        try:
            college.delete()
            messages.success(request, f"College '{name}' removed.")
        except ProtectedError:
            messages.error(request, 'This college still groups departments. Reassign those departments before deleting the college.')
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
            try:
                with transaction.atomic():
                    invite = form.save(commit=False)
                    if invite.department:
                        invite.department = lock_departments([invite.department], request.user.school)[0]
                    invite.invited_by = request.user
                    invite.used = False
                    invite.save()
            except (ValidationError, IntegrityError):
                return JsonResponse({'success': False, 'error': 'The assignment or invitation changed. Refresh and try again.'}, status=400)
            office = Office.objects.filter(code=invite.college).first() if not invite.department_id else None
            label = invite.department.name if invite.department_id else (office.name if office else invite.college)
            sent = _send_saved_email(send_faculty_invite_email, invite.email, label)
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': 'Faculty invitation saved and emailed.' if sent else 'Faculty invitation saved, but the email could not be sent.',
                    'email_sent': sent,
                }, status=201)
            messages.success(request, 'Faculty invitation saved and emailed.' if sent else 'Faculty invitation saved, but the email could not be sent.')
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
def remove_faculty_superadmin(request, user_id):
    faculty_user = get_object_or_404(User, id=user_id, role='faculty')
    if request.method == 'POST':
        return access_response(faculty_user, reactivate=request.POST.get('action') == 'reactivate')
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)


@login_required
@role_required('superadmin')
def delete_faculty_superadmin(request, user_id):
    faculty_user = get_object_or_404(User, id=user_id, role='faculty')
    if request.method == 'POST':
        try:
            with transaction.atomic():
                faculty_user.delete()
        except ProtectedError:
            return JsonResponse({'success': False, 'error':
                'This faculty account has consultation history or linked records and cannot be removed. Deactivate the account instead.'}, status=409)
        return JsonResponse({'success': True, 'message': 'Faculty account removed.'})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)

