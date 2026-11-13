from django.contrib.auth.models import AbstractUser
from datetime import timedelta
from django.utils import timezone
from django.db import models
from django.conf import settings
from .colleges import get_college_label

from apps.core.colleges import COLLEGE_CHOICES
from .school_models import School, SchoolDomain, SchoolChangeLog
from .school_request_models import SchoolRegistrationRequest
from .school_onboarding_models import SchoolInquiry, SchoolAccessLink, SchoolInquiryEvent
from .school_scope import SchoolScopedModel, SchoolUserManager
from .education import LEVEL_CHOICES, YEAR_CHOICES, default_levels, validate_announcement_levels
from .school_admin_access import default_school_admin_permissions, validate_school_admin_permissions


class User(AbstractUser, SchoolScopedModel):
    objects = SchoolUserManager()
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('faculty', 'Faculty'),
        ('depthead', 'College Head'),
        ('officeadmin', 'Office Admin'),
        ('superadmin', 'School Admin'),
        ('systemadmin', 'Super Admin'),
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

    TITLE_CHOICES = [
    ('chairperson', 'Department Head'),
    ('dean', 'College Head'),
    ]

    title = models.CharField(max_length=20, choices=TITLE_CHOICES, blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    account_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    school_admin_full_access = models.BooleanField(default=True)
    school_admin_permissions = models.JSONField(default=default_school_admin_permissions,
        validators=[validate_school_admin_permissions])
    college = models.CharField(max_length=100, blank=True, null=True)
    # Nullable only during the staged rollout; existing records are backfilled.
    school = models.ForeignKey(School, on_delete=models.PROTECT, null=True, blank=True, related_name='users')
    # Academic home for faculty/college students; head access uses assignments.
    # Nullable while the existing college/office flows remain in service.
    department = models.ForeignKey('core.Department', on_delete=models.PROTECT, null=True, blank=True,
                                   related_name='members')
    managed_departments = models.ManyToManyField('core.Department', through='core.DepartmentHeadAssignment',
                                                related_name='heads', blank=True)
    profile_completed = models.BooleanField(default=False)
    student_id = models.CharField(max_length=20, blank=True, null=True)
    educational_level = models.CharField(max_length=12, choices=LEVEL_CHOICES, blank=True, default='')
    year_level = models.CharField(max_length=2, blank=True, null=True)
    google_photo_url = models.URLField(max_length=2048, blank=True)
    uploaded_photo_url = models.URLField(max_length=2048, blank=True)

    @property
    def avatar_url(self):
        """Private uploads are resolved through an owner-only view, never a public URL."""
        from django.urls import reverse
        from .profile_photos import safe_photo_url
        if self.uploaded_photo_url:
            if self.role == 'student':
                return reverse('core:profile_photo_image', args=[self.pk])
            return safe_photo_url(self.uploaded_photo_url)
        return safe_photo_url(self.google_photo_url)

    @property
    def avatar_initials(self):
        return (''.join(part[0] for part in (self.first_name, self.last_name) if part)
                or self.username[:1] or '?').upper()

    @property
    def college_name(self):
        """Return the full college name, including for legacy CCS records."""
        return get_college_label(self.college)

    @property
    def school_admin_access(self):
        from .school_admin_access import feature_access
        return feature_access(self)

    @property
    def school_admin_access_label(self):
        from .school_admin_access import permission_labels
        return 'Full access' if self.school_admin_full_access else ', '.join(permission_labels(self.school_admin_permissions))

    def get_year_level_display(self):
        return dict(YEAR_CHOICES.get(self.educational_level or 'college', [])).get(self.year_level, self.year_level or '')

class SuperAdminInvite(SchoolScopedModel):
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name='superadmin_invites')
    email = models.EmailField()
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                  related_name='superadmin_invites_sent')
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    school_admin_full_access = models.BooleanField(default=True)
    school_admin_permissions = models.JSONField(default=default_school_admin_permissions,
        validators=[validate_school_admin_permissions])

    @property
    def school_admin_access_label(self):
        from .school_admin_access import permission_labels
        return 'Full access' if self.school_admin_full_access else ', '.join(permission_labels(self.school_admin_permissions))

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(models.functions.Lower('email'), name='superadmin_invite_email_ci_unique')]

    def __str__(self):
        return f'School Admin invite for {self.email} ({self.school.code})'


class FacultyInvite(SchoolScopedModel):
    school = models.ForeignKey(School, on_delete=models.PROTECT, null=True, blank=True, related_name='faculty_invites')
    email = models.EmailField(unique=True)
    college = models.CharField(max_length=100)
    department = models.ForeignKey('core.Department', on_delete=models.PROTECT, null=True, blank=True,
                                   related_name='faculty_invites')
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='invites_sent')
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)  

    def __str__(self):
        return f"Invite for {self.email} ({self.college})"

class DeptHeadInvite(SchoolScopedModel):
    school = models.ForeignKey(School, on_delete=models.PROTECT, null=True, blank=True, related_name='head_invites')
    email = models.EmailField(unique=True)
    college = models.CharField(max_length=100)
    departments = models.ManyToManyField('core.Department', through='core.DepartmentInviteAssignment',
                                         related_name='head_invites', blank=True)
    title = models.CharField(max_length=20, choices=User.TITLE_CHOICES, blank=True, null=True)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='depthead_invites_sent')
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    def __str__(self):
        return f"College Head invite for {self.email} ({self.college})"

class OfficeAdminInvite(SchoolScopedModel):
    school = models.ForeignKey(School, on_delete=models.PROTECT, null=True, blank=True, related_name='office_admin_invites')
    email = models.EmailField(unique=True)
    office = models.CharField(max_length=100)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='office_admin_invites_sent')
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    def __str__(self):
        return f"Office Admin invite for {self.email} ({self.office})"

class OfficeClosure(SchoolScopedModel):
    school = models.ForeignKey(School, on_delete=models.PROTECT, null=True, blank=True, related_name='closures')
    college = models.CharField(max_length=100)
    department = models.OneToOneField('core.Department', on_delete=models.PROTECT, null=True, blank=True,
                                      related_name='closure')
    is_closed = models.BooleanField(default=False)
    reason = models.TextField(blank=True)
    closure_start = models.DateField(null=True, blank=True)
    closure_end = models.DateField(null=True, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='office_closures_updated')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(models.functions.Lower('college'), models.F('school'),
            condition=models.Q(department__isnull=True), name='closure_school_office_unique')]

    def __str__(self):
        return f"{self.college} - {'Closed' if self.is_closed else 'Open'}"

class College(SchoolScopedModel):
    school = models.ForeignKey(School, on_delete=models.PROTECT, null=True, blank=True, related_name='colleges')
    code = models.CharField(max_length=20, blank=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    schedule_template = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(models.functions.Lower('code'), models.F('school'), name='college_school_code_unique'),
            models.UniqueConstraint(models.functions.Lower('name'), models.F('school'), name='college_school_name_unique'),
        ]

    def generate_code(self):
        #skip words so College of Computer Studies = CCS not COCS
        skip_words = {'of', 'and', 'the', 'for'}
        words = [w for w in self.name.split() if w.lower() not in skip_words]
        base_code = ''.join(w[0].upper() for w in words) or 'COL'

        code = base_code
        counter = 1
        while College.objects.filter(school_id=self.school_id, code__iexact=code).exclude(pk=self.pk).exists():
            counter += 1
            code = f"{base_code}{counter}"
        return code

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self.generate_code()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Office(SchoolScopedModel):
    school = models.ForeignKey(School, on_delete=models.PROTECT, null=True, blank=True, related_name='offices')
    code = models.CharField(max_length=20, blank=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    student_levels = models.JSONField(default=list, blank=True, validators=[validate_announcement_levels])
    schedule_template = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def student_levels_label(self):
        from .education import student_levels_label
        return student_levels_label(self.student_levels)

    class Meta:
        constraints = [
            models.UniqueConstraint(models.functions.Lower('code'), models.F('school'), name='office_school_code_unique'),
            models.UniqueConstraint(models.functions.Lower('name'), models.F('school'), name='office_school_name_unique'),
        ]

    def generate_code(self):
        words = [w for w in self.name.split() if w.lower() not in {'of', 'and', 'the', 'for'}]
        base_code = ''.join(w[0].upper() for w in words) or 'OFF'
        code, counter = base_code, 1
        while Office.objects.filter(school_id=self.school_id, code__iexact=code).exclude(pk=self.pk).exists():
            counter += 1
            code = f'{base_code}{counter}'
        return code

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self.generate_code()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class CollegeAnnouncement(SchoolScopedModel):
    school = models.ForeignKey(School, on_delete=models.PROTECT, null=True, blank=True, related_name='announcements')
    AUDIENCE_CHOICES = [('faculty', 'Faculty'), ('students', 'Students'), ('both', 'Both')]
    audience = models.CharField(max_length=8, choices=AUDIENCE_CHOICES, default='both')
    student_levels = models.JSONField(default=default_levels, blank=True, validators=[validate_announcement_levels])
    college = models.CharField(max_length=20, choices=COLLEGE_CHOICES)
    department = models.ForeignKey('core.Department', on_delete=models.PROTECT, null=True, blank=True,
                                   related_name='announcements')
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
        return f"{self.get_college_display()}: {self.message[:40]}"


class DemoDataBatch(SchoolScopedModel):
    """Exact ownership manifest for reversible, explicitly approved demo seeds."""

    key = models.SlugField(max_length=40, unique=True)
    college = models.ForeignKey(College, on_delete=models.PROTECT)
    manifest = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class Notification(SchoolScopedModel):
    TYPE_CHOICES = [
        ('consultation_request', 'Consultation request'),
        ('booking_confirmation', 'Booking confirmation'),
        ('announcement', 'College announcement'),
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


from .department_models import Department, DepartmentHeadAssignment, DepartmentInviteAssignment  # noqa: E402,F401
