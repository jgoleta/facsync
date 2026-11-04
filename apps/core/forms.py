from django import forms
from zoneinfo import ZoneInfo
from .models import College, Office, User
from .colleges import COLLEGE_CHOICES, get_unit_choices
from django.utils import timezone
from apps.core.models import CollegeAnnouncement
from .school_forms import SchoolBoundModelForm

class StudentProfileForm(SchoolBoundModelForm):
    college = forms.ChoiceField(choices=get_unit_choices)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, message in (
            ('student_id', 'Enter your Student ID.'),
            ('year_level', 'Select your year level.'),
        ):
            self.fields[name].required = True
            self.fields[name].error_messages['required'] = message

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
        widget=forms.DateInput(attrs={'type': 'date', 'id': 'ann-expiry'}),
        help_text="Leave blank to auto-expire 7 days after posting."
    )

    class Meta:
        model = CollegeAnnouncement
        fields = ['message', 'audience']
        widgets = {'audience': forms.Select(attrs={'id': 'ann-audience'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['expiry_date'].widget.attrs['min'] = timezone.localdate(timezone=ZoneInfo('Asia/Manila')).isoformat()

    def clean_expiry_date(self):
        value = self.cleaned_data['expiry_date']
        if value and value < timezone.localdate(timezone=ZoneInfo('Asia/Manila')):
            raise forms.ValidationError('Choose today or a future expiry date.')
        return value

    def save(self, commit=True):
        instance = super().save(commit=False)
        expiry_date = self.cleaned_data.get('expiry_date')
        if expiry_date:
            instance.expiry = timezone.make_aware(
                timezone.datetime.combine(expiry_date, timezone.datetime.max.time()),
                timezone=ZoneInfo('Asia/Manila'),
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

class OfficeForm(SchoolBoundModelForm):
    class Meta:
        model = Office
        fields = ['name', 'description']

    def clean_name(self):
        value = self.cleaned_data['name']
        if Office.objects.filter(name__iexact=value).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('An office with this name already exists in your school.')
        return value

class OfficeDescriptionForm(SchoolBoundModelForm):
    class Meta:
        model = Office
        fields = ['description']
