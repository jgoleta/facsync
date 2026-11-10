"""Pre-school applications are global records, accessible only to platform reviewers."""
import uuid

from django.conf import settings
from django.db import models


class SchoolInquiry(models.Model):
    STAGES = [('inquiry', 'Inquiry received'), ('verification_wait', 'Awaiting verification details'),
        ('verification_review', 'Verification submitted'), ('registration_wait', 'Invited to register'),
        ('registration_review', 'Awaiting approval'), ('approved', 'Approved'), ('rejected', 'Rejected')]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    representative_name = models.CharField(max_length=150)
    email = models.EmailField()
    position = models.CharField(max_length=150)
    school_name = models.CharField(max_length=150)
    stage = models.CharField(max_length=24, choices=STAGES, default='inquiry')
    website = models.URLField(blank=True)
    address = models.CharField(max_length=500, blank=True)
    domain = models.CharField(max_length=253, blank=True)
    official_name = models.CharField(max_length=150, blank=True)
    official_position = models.CharField(max_length=150, blank=True)
    contact_email = models.EmailField(blank=True)
    authority = models.TextField(max_length=2000, blank=True)
    evidence_path = models.CharField(max_length=300, blank=True)
    evidence_sha256 = models.CharField(max_length=64, blank=True)
    evidence_deleted_at = models.DateTimeField(null=True, blank=True)
    google_subject = models.CharField(max_length=255, blank=True)
    application = models.OneToOneField('core.SchoolRegistrationRequest', null=True, blank=True,
        on_delete=models.PROTECT, related_name='inquiry')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [models.UniqueConstraint(models.functions.Lower('email'),
            condition=~models.Q(stage__in=['approved', 'rejected']), name='school_inquiry_open_email'),
            models.CheckConstraint(condition=models.Q(stage__in=[
                'inquiry', 'verification_wait', 'verification_review',
                'registration_wait', 'registration_review', 'approved', 'rejected']),
                name='school_inquiry_valid_stage')]


class SchoolAccessLink(models.Model):
    inquiry = models.ForeignKey(SchoolInquiry, on_delete=models.PROTECT, related_name='links')
    purpose = models.CharField(max_length=12, choices=[('verification', 'Verification'), ('registration', 'Registration')])
    digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class SchoolInquiryEvent(models.Model):
    inquiry = models.ForeignKey(SchoolInquiry, on_delete=models.PROTECT, related_name='events')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=60)
    private_notes = models.TextField(max_length=2000, blank=True)
    applicant_message = models.TextField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def action_label(self):
        return {'inquiry_submitted': 'Inquiry submitted', 'send_verification': 'Verification form invited',
            'request_changes': 'Verification corrections requested', 'send_registration': 'Registration invited',
            'verification_submitted': 'Verification submitted', 'registration_submitted': 'Registration submitted',
            'reject': 'Inquiry rejected', 'final_approve': 'School approved', 'final_reject': 'Registration rejected',
            'evidence_retention_cleanup': 'Authorization letter deleted after retention period'}.get(self.action, self.action)

    class Meta:
        ordering = ['created_at', 'pk']
