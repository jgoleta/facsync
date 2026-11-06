"""School applications exist before either a school or an applicant account."""
import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower


class SchoolRegistrationRequest(models.Model):
    STATUS_CHOICES = [('pending', 'Pending review'), ('approved', 'Approved'), ('rejected', 'Rejected')]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    google_subject = models.CharField(max_length=255, editable=False)
    applicant_email = models.EmailField(editable=False)
    representative_name = models.CharField(max_length=150)
    position = models.CharField(max_length=150)
    school_name = models.CharField(max_length=150)
    school_code = models.CharField(max_length=20)
    domain = models.CharField(max_length=253, editable=False)
    educational_levels = models.JSONField()
    contact_email = models.EmailField()
    website = models.URLField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='school_requests_reviewed')
    reviewer_label = models.CharField(max_length=150, blank=True)
    verification_notes = models.TextField(max_length=2000, blank=True)
    decision_reason = models.TextField(max_length=1000, blank=True)
    approved_school = models.ForeignKey('core.School', on_delete=models.PROTECT, null=True, blank=True)
    invitation = models.ForeignKey('core.SuperAdminInvite', on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        indexes = [models.Index(fields=['status', 'created_at'], name='school_request_status_date')]
        constraints = [
            models.UniqueConstraint(Lower('applicant_email'), condition=models.Q(status='pending'), name='school_request_pending_email'),
            models.UniqueConstraint(fields=['google_subject'], condition=models.Q(status='pending'), name='school_request_pending_google'),
            models.CheckConstraint(condition=models.Q(status__in=['pending', 'approved', 'rejected']), name='school_request_valid_status'),
        ]

    def __str__(self):
        return f'{self.school_name} ({self.get_status_display()})'
