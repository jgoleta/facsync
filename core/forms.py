from django import forms
from .models import Department, User
from .departments import DEPARTMENT_CHOICES, get_department_choices
from django.utils import timezone
from core.models import DepartmentAnnouncement

class StudentProfileForm(forms.ModelForm):
    department = forms.ChoiceField(choices=get_department_choices())

    class Meta:
        model = User
        fields = ['student_id', 'department', 'year_level']

class FacultyProfileSetupForm(forms.Form):
    faculty_id = forms.CharField(max_length=64, label="Faculty ID")
    office_location = forms.CharField(max_length=128, label="Office / Room")

class FacultyRegistrationForm(forms.ModelForm):
    department = forms.ChoiceField(choices=get_department_choices())
    office_location = forms.CharField(max_length=128, label="Office / Room")
    faculty_id = forms.CharField(max_length=64, label="Faculty ID")

    class Meta:
        model = User
        fields = ['department']  #office_location, faculty_id go to FacultyProfile


class DepartmentAnnouncementForm(forms.ModelForm):
    expiry_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        help_text="Leave blank to auto-expire 7 days after posting."
    )

    class Meta:
        model = DepartmentAnnouncement
        fields = ['message']

    def save(self, commit=True):
        instance = super().save(commit=False)
        expiry_date = self.cleaned_data.get('expiry_date')
        if expiry_date:
            instance.expiry = timezone.make_aware(
                timezone.datetime.combine(expiry_date, timezone.datetime.max.time())
            )
        if commit:
            instance.save()
        return instance

class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'description']

class DepartmentDescriptionForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['description']