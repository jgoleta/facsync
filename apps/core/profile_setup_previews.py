"""Read-only screenshot preview using the real Faculty setup template."""
from django.conf import settings
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .forms import FacultyProfileSetupForm


@never_cache
@require_GET
def faculty_profile_preview(request):
    if (not settings.DEBUG or settings.SETTINGS_MODULE != 'config.settings.development'
            or not getattr(settings, 'PROFILE_SETUP_PREVIEWS', False)):
        raise Http404
    form = FacultyProfileSetupForm(initial={'faculty_id': 'FAC-2026-001', 'office_location': 'Room 201'})
    response = render(request, 'core/facultyProfileSetup.html', {'form': form, 'preview_mode': True})
    response['X-Robots-Tag'] = 'noindex, nofollow'
    return response
