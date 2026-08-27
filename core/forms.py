from django import forms
from .models import College, User
from .colleges import COLLEGE_CHOICES, get_college_choices
from django.utils import timezone
from core.models import CollegeAnnouncement

class StudentProfileForm(forms.ModelForm):
    college = forms.ChoiceField(choices=get_college_choices)

    class Meta:
        model = User
        fields = ['student_id', 'college', 'year_level']

class FacultyProfileSetupForm(forms.Form):
    faculty_id = forms.CharField(max_length=64, label="Faculty ID")
    office_location = forms.CharField(max_length=128, label="Office / Room")

class FacultyRegistrationForm(forms.ModelForm):
    college = forms.ChoiceField(choices=get_college_choices)
    office_location = forms.CharField(max_length=128, label="Office / Room")
    faculty_id = forms.CharField(max_length=64, label="Faculty ID")

    class Meta:
        model = User
        fields = ['college']  #office_location, faculty_id go to FacultyProfile


class CollegeAnnouncementForm(forms.ModelForm):
    expiry_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        help_text="Leave blank to auto-expire 7 days after posting."
    )

    class Meta:
        model = CollegeAnnouncement
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

class CollegeForm(forms.ModelForm):
    class Meta:
        model = College
        fields = ['name', 'description']

class CollegeDescriptionForm(forms.ModelForm):
    class Meta:
        model = College
        fields = ['description']
