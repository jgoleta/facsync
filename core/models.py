from django.contrib.auth.models import AbstractUser
from datetime import timedelta
from django.utils import timezone
from django.db import models
from django.conf import settings
from .departments import get_department_label

from core.departments import DEPARTMENT_CHOICES


class User(AbstractUser):
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('faculty', 'Faculty'),
        ('depthead', 'Department Head'),
        ('superadmin', 'Super Admin'),
    ]
    
    STATUS_CHOICES = [
    ('active', 'Active'),
    ('pending', 'Pending'),
    ('declined', 'Declined'),
    ('deactivated', 'Deactivated'),
    ]

    YEAR_LEVEL_CHOICES = [
        ('1', '1st Year'),
        ('2', '2nd Year'),
        ('3', '3rd Year'),
        ('4', '4th Year'),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    account_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    department = models.CharField(max_length=100, blank=True, null=True)  
    profile_completed = models.BooleanField(default=False)
    student_id = models.CharField(max_length=20, blank=True, null=True)
    year_level = models.CharField(max_length=1, choices=YEAR_LEVEL_CHOICES, blank=True, null=True)

    @property
    def department_name(self):
        """Return the full department name, including for legacy CCS records."""
        return get_department_label(self.department)

class FacultyInvite(models.Model):
    email = models.EmailField(unique=True)
    department = models.CharField(max_length=100)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='invites_sent')
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)  

    def __str__(self):
        return f"Invite for {self.email} ({self.department})"

class DeptHeadInvite(models.Model):
    email = models.EmailField(unique=True)
    department = models.CharField(max_length=100)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='depthead_invites_sent')
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    def __str__(self):
        return f"Dept Head invite for {self.email} ({self.department})"

class OfficeClosure(models.Model):
    department = models.CharField(max_length=100, unique=True)
    is_closed = models.BooleanField(default=False)
    reason = models.TextField(blank=True)
    closure_start = models.DateField(null=True, blank=True)
    closure_end = models.DateField(null=True, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='office_closures_updated')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.department} - {'Closed' if self.is_closed else 'Open'}"

class Department(models.Model):
    code = models.CharField(max_length=20, unique=True, blank=True)
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def generate_code(self):
        #skip words so College of Computer Studies = CCS not COCS
        skip_words = {'of', 'and', 'the', 'for'}
        words = [w for w in self.name.split() if w.lower() not in skip_words]
        base_code = ''.join(w[0].upper() for w in words) or 'DEPT'

        code = base_code
        counter = 1
        while Department.objects.filter(code=code).exclude(pk=self.pk).exists():
            counter += 1
            code = f"{base_code}{counter}"
        return code

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self.generate_code()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class DepartmentAnnouncement(models.Model):
    department = models.CharField(max_length=20, choices=DEPARTMENT_CHOICES)
    message = models.TextField()
    posted_at = models.DateTimeField(auto_now_add=True)
    expiry = models.DateTimeField()
    posted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        ordering = ['-posted_at']

    def save(self, *args, **kwargs):
        if not self.expiry:
            self.expiry = timezone.now() + timedelta(days=7)
        super().save(*args, **kwargs)

    @property
    def is_active(self):
        return timezone.now() < self.expiry

    def __str__(self):
        return f"{self.get_department_display()}: {self.message[:40]}"


class Notification(models.Model):
    TYPE_CHOICES = [
        ('consultation_request', 'Consultation request'),
        ('booking_confirmation', 'Booking confirmation'),
        ('announcement', 'Department announcement'),
        ('faculty_status_update', 'Faculty status update'),
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    notification_type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    title = models.CharField(max_length=160)
    message = models.TextField()
    url = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} for {self.recipient}"
