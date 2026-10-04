import logging
from hmac import compare_digest

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .services.status_scheduler import run_status_scheduler


@csrf_exempt  # Machine endpoint: authenticated by a separate bearer secret, never cookies.
@require_POST
@never_cache
def automatic_status(request):
    secret = getattr(settings, 'STATUS_SCHEDULER_SECRET', '')
    supplied = request.headers.get('Authorization', '')
    if not secret or not compare_digest(supplied.encode(), f'Bearer {secret}'.encode()):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    if not settings.AUTOMATIC_STATUS_EMAIL_QUEUE_ENABLED:
        return JsonResponse({'error': 'Automatic status scheduler is disabled'}, status=503)
    if not settings.BREVO_API_KEY or not settings.DEFAULT_FROM_EMAIL:
        return JsonResponse({'error': 'Status email transport is not configured'}, status=503)
    try:
        result = run_status_scheduler()
        failed = result.get('check_errors') or result.get('email_failed') or result.get('email_unknown')
        return JsonResponse(result, status=503 if failed else 200)
    except Exception:
        logging.getLogger(__name__).warning('Automatic status scheduler failed; inspect delivery records.')
        return JsonResponse({'error': 'Scheduled processing failed'}, status=503)
