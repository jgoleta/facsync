from django.conf import settings
from django.db import models
from apps.faculty.models import StatusHistory as FacultyStatusHistory
from apps.faculty.models import WalkInQueue as FacultyWalkInQueue


class StudentWalkInQueue(FacultyWalkInQueue):
    class Meta:
        proxy = True
        app_label = 'students'
        verbose_name = 'Student Walk-In Queue'
        verbose_name_plural = 'Student Walk-In Queues'


class StudentStatusHistory(FacultyStatusHistory):
    class Meta:
        proxy = True
        app_label = 'students'
        verbose_name = 'Student Status History'
        verbose_name_plural = 'Student Status Histories'


class FacultyStatusSubscription(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='faculty_status_subscriptions',
    )
    faculty = models.ForeignKey(
        'faculty.FacultyProfile',
        on_delete=models.CASCADE,
        related_name='student_status_subscriptions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'faculty'],
                name='unique_student_faculty_status_subscription',
            ),
        ]

    def __str__(self):
        return f'{self.student} follows {self.faculty}'
