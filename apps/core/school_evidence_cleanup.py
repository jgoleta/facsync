from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import SchoolInquiry, SchoolInquiryEvent
from .school_evidence import SchoolEvidenceStorage
from .profile_photos import PhotoStorageError


def cleanup_school_evidence(*, apply=False, limit=50):
    cutoff = timezone.now() - timedelta(days=90)
    candidates = SchoolInquiry.objects.filter(stage__in=['approved', 'rejected'],
        closed_at__lte=cutoff).exclude(evidence_path='').order_by('closed_at')
    result = {'eligible': candidates.count(), 'deleted': 0, 'failed': 0}
    if not apply:
        return result
    for pk in list(candidates.values_list('pk', flat=True)[:limit]):
        with transaction.atomic():
            item = SchoolInquiry.objects.select_for_update().get(pk=pk)
            if not item.evidence_path or not item.closed_at or item.closed_at > cutoff:
                continue
            try:
                SchoolEvidenceStorage().remove(item.evidence_path)
            except PhotoStorageError:
                result['failed'] += 1
                continue
            item.evidence_path = ''
            item.evidence_sha256 = ''
            item.evidence_deleted_at = timezone.now()
            item.save(update_fields=['evidence_path', 'evidence_sha256', 'evidence_deleted_at', 'updated_at'])
            SchoolInquiryEvent.objects.create(inquiry=item, action='evidence_retention_cleanup')
            result['deleted'] += 1
    return result
