"""Own-account photo management; private student images never enter directory data."""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .models import User
from .profile_photos import PhotoStorage, PhotoStorageError, delete_photo_safely, normalize_photo


@login_required
@require_POST
@never_cache
def profile_photo(request):
    if request.user.role not in {'student', 'faculty'} or request.user.account_status != 'active':
        return JsonResponse({'error': 'Photo changes are unavailable for this account.'}, status=403)
    action = request.POST.get('action')
    if action not in {'upload', 'remove'}:
        return JsonResponse({'error': 'Choose upload or remove.'}, status=400)
    new_url = ''
    try:
        if action == 'upload':
            content = normalize_photo(request.FILES.get('photo'))
            new_url = PhotoStorage().upload(request.user, content)
        try:
            with transaction.atomic():
                user = User.objects.select_for_update().get(pk=request.user.pk)
                old_url = user.uploaded_photo_url
                user.uploaded_photo_url = new_url
                user.save(update_fields=['uploaded_photo_url'])
                transaction.on_commit(lambda: delete_photo_safely(user.pk, old_url))
        except Exception:
            delete_photo_safely(request.user.pk, new_url)
            raise
    except ValidationError as exc:
        return JsonResponse({'error': exc.messages[0]}, status=400)
    except PhotoStorageError as exc:
        return JsonResponse({'error': str(exc)}, status=503)
    return JsonResponse({'avatar_url': user.avatar_url, 'has_upload': bool(new_url)})


@require_GET
@never_cache
def profile_photo_image(request, user_id):
    # Return no image (rather than an HTML login redirect) for anonymous/other users.
    if (not request.user.is_authenticated or request.user.pk != user_id
            or request.user.role != 'student' or request.user.account_status != 'active'):
        return HttpResponse(status=403)
    if not request.user.uploaded_photo_url:
        return HttpResponse(status=404)
    try:
        url = PhotoStorage().signed_student_url(request.user)
    except PhotoStorageError:
        return HttpResponse(status=503)
    response = HttpResponseRedirect(url)
    response['Referrer-Policy'] = 'no-referrer'
    return response
