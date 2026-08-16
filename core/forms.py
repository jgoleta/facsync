from django import forms
from .models import User
from .departments import DEPARTMENT_CHOICES

class StudentProfileForm(forms.ModelForm):
    department = forms.ChoiceField(choices=DEPARTMENT_CHOICES)

    class Meta:
        model = User
        fields = ['student_id', 'department', 'year_level']

class FacultyProfileSetupForm(forms.Form):
    faculty_id = forms.CharField(max_length=64, label="Faculty ID")
    office_location = forms.CharField(max_length=128, label="Office / Room")

class FacultyRegistrationForm(forms.ModelForm):
    department = forms.ChoiceField(choices=DEPARTMENT_CHOICES)
    office_location = forms.CharField(max_length=128, label="Office / Room")
    faculty_id = forms.CharField(max_length=64, label="Faculty ID")

    class Meta:
        model = User
        fields = ['department']  #office_location, faculty_id go to FacultyProfile
