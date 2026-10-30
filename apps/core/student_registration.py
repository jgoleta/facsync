"""Resolve verified student identities against System Admin domain assignments."""
from allauth.core.exceptions import ImmediateHttpResponse
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.shortcuts import redirect

from .models import School, SchoolDomain

EDU_ONLY = 'FacSync supports .edu.ph institutional accounts only'
UNREGISTERED = 'Your institution is not yet registered with FacSync'
SUSPENDED = 'Your school’s access to FacSync has been suspended. Please contact your school’s Super Admin.'


def reject_registration(request, message):
    messages.error(request, message)
    raise ImmediateHttpResponse(redirect('core:register'))


def student_school(request, email, *, expected_school_id=None, lock=False):
    if not email:
        reject_registration(request, 'Please sign in with a verified Google account.')
    try:
        validate_email(email)
    except ValidationError:
        reject_registration(request, EDU_ONLY)
    domain = email.rsplit('@', 1)[1].lower()
    if not domain.endswith('.edu.ph'):
        reject_registration(request, EDU_ONLY)
    school_id = SchoolDomain.objects.filter(domain=domain).values_list('school_id', flat=True).first()
    if school_id is None:
        reject_registration(request, UNREGISTERED)
    schools = School.objects.select_for_update() if lock else School.objects
    school = schools.get(pk=school_id)
    # Domain edits and suspension lock this school too. Recheck the assignment
    # after acquiring its lock so signup cannot commit against a removed domain.
    if lock and not SchoolDomain.objects.filter(domain=domain, school_id=school_id).exists():
        reject_registration(request, UNREGISTERED)
    if not school.is_active:
        reject_registration(request, SUSPENDED)
    if expected_school_id is not None and expected_school_id != school.pk:
        reject_registration(request, 'Your institution’s registration details changed. Please start registration again.')
    return school
