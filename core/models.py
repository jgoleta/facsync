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