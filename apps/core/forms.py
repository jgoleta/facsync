from django import forms
from .models import College, User
from .colleges import COLLEGE_CHOICES, get_college_choices
from django.utils import timezone
from apps.core.models import CollegeAnnouncement
from .school_forms import SchoolBoundModelForm

class StudentProfileForm(SchoolBoundModelForm):
    college = forms.ChoiceField(choices=get_college_choices)

    class Meta:
        model = User
        fields = ['student_id', 'college', 'year_level']

class FacultyProfileSetupForm(forms.Form):
    faculty_id = forms.CharField(max_length=64, label="Faculty ID")
    office_location = forms.CharField(max_length=128, label="Office / Room")

    def clean_faculty_id(self):
        from apps.faculty.models import FacultyProfile
        value = self.cleaned_data['faculty_id']
        # Profile IDs remain globally unique; reveal no owner or institution.
        if FacultyProfile._base_manager.filter(pk=value).exists():
            raise forms.ValidationError('This faculty identifier is unavailable.')
        return value

class CollegeAnnouncementForm(SchoolBoundModelForm):
    expiry_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        help_text="Leave blank to auto-expire 7 days after posting."
    )

    class Meta:
        model = CollegeAnnouncement
        fields = ['message', 'audience']
        widgets = {'audience': forms.Select(attrs={'id': 'ann-audience'})}

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

class CollegeForm(SchoolBoundModelForm):
    class Meta:
        model = College
        fields = ['name', 'description']

    def clean_name(self):
        value = self.cleaned_data['name']
        if College.objects.filter(name__iexact=value).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('A college with this name already exists in your school.')
        return value

class CollegeDescriptionForm(SchoolBoundModelForm):
    class Meta:
        model = College
        fields = ['description']
