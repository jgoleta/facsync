from django.conf import settings
from django.db import models
from core.colleges import get_college_label


class FacultyProfile(models.Model):
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('busy', 'Busy'),
        ('virtual_only', 'Virtual Only'),
        ('on_leave', 'On Leave'),
        ('unavailable', 'Unavailable'),
    ]

    faculty_id = models.CharField(max_length=64, primary_key=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='faculty_profile', db_column='user_id')
    college_id = models.CharField(max_length=64, db_column='college_id')
    office_location = models.CharField(max_length=128, blank=True)
    biography = models.TextField(blank=True)
    current_status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='available')
    status_note = models.TextField(blank=True)
    status_updated_at = models.DateTimeField(null=True, blank=True)
    # Manual status is retained so a failed/revoked calendar sync can safely
    # fall back to the faculty member's last explicit status.
    manual_status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='available')
    manual_status_override = models.BooleanField(default=False)
    manual_status_expires_at = models.DateTimeField(null=True, blank=True)
    # Preserve the previous connected-calendar behavior for existing users;
    # disconnecting explicitly turns this off.
    sync_enabled = models.BooleanField(default=True)
    walk_ins_enabled = models.BooleanField(default=False)
    last_calendar_sync_at = models.DateTimeField(null=True, blank=True)
    schedule_last_updated_at = models.DateTimeField(null=True, blank=True)
    photo_url = models.URLField(blank=True)
    biography = models.TextField(blank=True, default='')

    @property
    def college_name(self):
        """Return the full college name, including for legacy CCS records."""
        return get_college_label(self.college_id)

    class Meta:
        verbose_name = 'Faculty Profile'
        verbose_name_plural = 'Faculty Profiles'

    def __str__(self):
        """Display the faculty member's name and stable profile identifier."""
        return f"{self.user.get_full_name() or self.user.username} ({self.faculty_id})"


class GoogleCalendarConnection(models.Model):
    """OAuth credentials used to synchronize one faculty member's calendar."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='google_calendar_connection',
    )
    google_user_id = models.CharField(max_length=255)
    calendar_id = models.CharField(max_length=1024, default='primary')
    access_token = models.TextField()
    refresh_token = models.TextField(blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    connected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_sync_error = models.TextField(blank=True)

    def __str__(self):
        """Display which user owns this Google Calendar connection."""
        return f"Google Calendar for {self.user}"


class StatusHistory(models.Model):
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('busy', 'Busy'),
        ('virtual_only', 'Virtual Only'),
        ('on_leave', 'On Leave'),
        ('unavailable', 'Unavailable'),
    ]

    history_id = models.CharField(max_length=64, primary_key=True, unique=True)
    faculty = models.ForeignKey(
        FacultyProfile,
        on_delete=models.CASCADE,
        related_name='status_history',
        db_column='faculty_id',
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES)
    changed_at = models.DateTimeField()

    class Meta:
        ordering = ['-changed_at']
        verbose_name = 'Status History'
        verbose_name_plural = 'Status Histories'

    def __str__(self):
        """Describe the faculty status-history entry."""
        return f"{self.faculty} status changed from {self.status} at {self.changed_at}"


class ScheduleEvent(models.Model):
    WEEKDAY_CHOICES = [
        ('monday', 'Monday'),
        ('tuesday', 'Tuesday'),
        ('wednesday', 'Wednesday'),
        ('thursday', 'Thursday'),
        ('friday', 'Friday'),
        ('saturday', 'Saturday'),
        ('sunday', 'Sunday'),
    ]
    EVENT_TYPES = [
        ('busy', 'Busy'),
        ('unavailable', 'Unavailable'),
        ('on-leave', 'On Leave'),
        ('virtual', 'Virtual Only'),
    ]

    faculty = models.ForeignKey(FacultyProfile, on_delete=models.CASCADE, related_name='schedule_events')
    title = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=128, blank=True)
    schedule_status = models.CharField(max_length=32, blank=True)
    event_type = models.CharField(max_length=16, choices=EVENT_TYPES, default='busy')
    date = models.DateField(null=True, blank=True)
    day_of_week = models.CharField(max_length=9, choices=WEEKDAY_CHOICES, blank=True)
    start_month = models.PositiveSmallIntegerField(null=True, blank=True)
    end_month = models.PositiveSmallIntegerField(null=True, blank=True)
    recurrence_start_date = models.DateField(null=True, blank=True)
    recurrence_end_date = models.DateField(null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    google_event_id = models.CharField(max_length=1024, null=True, blank=True, db_index=True)
    google_calendar_id = models.CharField(max_length=1024, null=True, blank=True)
    managed_by_facsync = models.BooleanField(default=False)
    sync_state = models.CharField(max_length=16, default='local')
    sync_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['date', 'start_time']
        verbose_name = 'Schedule Event'
        verbose_name_plural = 'Schedule Events'

    def __str__(self):
        """Display the schedule event title, faculty, and date."""
        return f"{self.title} — {self.faculty} on {self.date}"


class ConsultationRequest(models.Model):
    AGENDA_CHOICES = [
        ('grade_consultation', 'Grade Consultation'),
        ('project_consultation', 'Project Consultation'),
        ('general_concern', 'General Concern / Talk'),
        ('academic_advising', 'Academic Advising'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('declined', 'Declined'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]

    request_id = models.CharField(max_length=64, primary_key=True, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='student_consultation_requests',
        db_column='user_id',
    )
    faculty = models.ForeignKey(
        FacultyProfile,
        on_delete=models.CASCADE,
        related_name='consultation_requests',
        db_column='faculty_id',
    )
    date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    agenda = models.CharField(max_length=32, choices=AGENDA_CHOICES, default='general_concern')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    student_message = models.TextField(blank=True, default='')
    faculty_note = models.TextField(blank=True)
    google_event_id = models.CharField(max_length=1024, null=True, blank=True, db_index=True)
    google_calendar_id = models.CharField(max_length=1024, null=True, blank=True)
    calendar_sync_status = models.CharField(max_length=16, default='not_configured')
    calendar_sync_error = models.TextField(blank=True)
    last_calendar_sync_at = models.DateTimeField(null=True, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-date']
        verbose_name = 'Consultation Request'
        verbose_name_plural = 'Consultation Requests'

    def __str__(self):
        """Display the consultation identifier and faculty member."""
        return f"Consultation request {self.request_id} for {self.faculty} on {self.date}"


class WalkInQueue(models.Model):
    QUEUE_STATUS_CHOICES = [
        ('waiting', 'Waiting'),
        ('called', 'Called to Office'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    queue_id = models.CharField(max_length=64, primary_key=True, unique=True)
    faculty = models.ForeignKey(
        FacultyProfile,
        on_delete=models.CASCADE,
        related_name='walk_in_queues',
        db_column='faculty_id',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='walk_in_queues',
        db_column='user_id',
    )
    position = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=QUEUE_STATUS_CHOICES, default='waiting')
    joined_at = models.DateTimeField()
    served_at = models.DateTimeField(null=True, blank=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    student_message = models.TextField(blank=True)
    faculty_note = models.TextField(blank=True)

    class Meta:
        ordering = ['position', 'joined_at']
        verbose_name = 'Walk-In Queue'
        verbose_name_plural = 'Walk-In Queues'

    def __str__(self):
        """Display the walk-in queue identifier and participants."""
        return f"Walk-in queue {self.queue_id} for {self.user} with {self.faculty}"
