from hmac import compare_digest

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .school_evidence_cleanup import cleanup_school_evidence


@csrf_exempt
@require_POST
@never_cache
def cleanup_evidence(request):
    secret = settings.SCHOOL_EVIDENCE_CLEANUP_SECRET
    supplied = request.headers.get('Authorization', '')
    if not secret or not compare_digest(supplied.encode(), ('Bearer ' + secret).encode()):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    result = cleanup_school_evidence(apply=True)
    return JsonResponse(result, status=503 if result['failed'] else 200)
