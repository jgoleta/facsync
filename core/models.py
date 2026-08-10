from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings

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
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    account_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    department = models.CharField(max_length=100, blank=True, null=True)  

class FacultyInvite(models.Model):
    email = models.EmailField(unique=True)
    department = models.CharField(max_length=100)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='invites_sent')
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)  

    def __str__(self):
        return f"Invite for {self.email} ({self.department})"