"""Private onboarding PDFs, never stored in public profile-photo buckets."""
import hashlib
import logging
import re
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError

from .profile_photos import PhotoStorage, PhotoStorageError

logger = logging.getLogger(__name__)


class SchoolEvidenceStorage(PhotoStorage):
    def __init__(self):
        super().__init__()
        self.evidence_bucket = settings.SUPABASE_SCHOOL_EVIDENCE_BUCKET
        if not re.fullmatch(r'[A-Za-z0-9_-]+', self.evidence_bucket):
            raise PhotoStorageError('School document storage is not configured.')

    def valid_path(self, path):
        if not re.fullmatch(r'[0-9a-f-]{36}/[0-9a-f]{32}\.pdf', path):
            raise ValidationError('Invalid document reference.')
        return path

    def store(self, inquiry, upload):
        self.check_visibility(self.evidence_bucket, public=False)
        content = upload.read()
        path = f'{inquiry.pk}/{uuid.uuid4().hex}.pdf'
        self.request('POST', f'object/{self.evidence_bucket}/{path}', data=content,
            headers={'Content-Type': 'application/pdf', 'x-upsert': 'false', 'Cache-Control': 'no-store'})
        return path, hashlib.sha256(content).hexdigest()

    def download(self, path):
        self.check_visibility(self.evidence_bucket, public=False)
        return self.request('GET', f'object/authenticated/{self.evidence_bucket}/{self.valid_path(path)}').content

    def remove(self, path):
        self.check_visibility(self.evidence_bucket, public=False)
        self.request('DELETE', f'object/{self.evidence_bucket}', json={'prefixes': [self.valid_path(path)]})


def remove_evidence_safely(path):
    if path:
        try:
            SchoolEvidenceStorage().remove(path)
        except (PhotoStorageError, ValidationError):
            logger.warning('school_evidence_cleanup_failed')
