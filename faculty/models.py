from django.conf import settings
from django.db import models


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
    department_id = models.CharField(max_length=64, db_column='department_id')
    office_location = models.CharField(max_length=128, blank=True)
    current_status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='available')
    status_note = models.TextField(blank=True)
    status_updated_at = models.DateTimeField(null=True, blank=True)
    last_calendar_sync_at = models.DateTimeField(null=True, blank=True)
    photo_url = models.URLField(blank=True)
    biography = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = 'Faculty Profile'
        verbose_name_plural = 'Faculty Profiles'

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.faculty_id})"


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
        return f"{self.faculty} status changed from {self.status} at {self.changed_at}"


class ScheduleEvent(models.Model):
    EVENT_TYPES = [
        ('busy', 'Busy'),
        ('unavailable', 'Unavailable'),
        ('on-leave', 'On Leave'),
        ('virtual', 'Virtual Only'),
    ]

    faculty = models.ForeignKey(FacultyProfile, on_delete=models.CASCADE, related_name='schedule_events')
    title = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    event_type = models.CharField(max_length=16, choices=EVENT_TYPES, default='busy')
    date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['date', 'start_time']
        verbose_name = 'Schedule Event'
        verbose_name_plural = 'Schedule Events'

    def __str__(self):
        return f"{self.title} — {self.faculty} on {self.date}"


class ConsultationRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('declined', 'Declined'),
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
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    faculty_note = models.TextField(blank=True)

    class Meta:
        ordering = ['-date']
        verbose_name = 'Consultation Request'
        verbose_name_plural = 'Consultation Requests'

    def __str__(self):
        return f"Consultation request {self.request_id} for {self.faculty} on {self.date}"


class WalkInQueue(models.Model):
    QUEUE_STATUS_CHOICES = [
        ('waiting', 'Waiting'),
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
    student_message = models.TextField(blank=True)
    faculty_note = models.TextField(blank=True)

    class Meta:
        ordering = ['position', 'joined_at']
        verbose_name = 'Walk-In Queue'
        verbose_name_plural = 'Walk-In Queues'

    def __str__(self):
        return f"Walk-in queue {self.queue_id} for {self.user} with {self.faculty}"
