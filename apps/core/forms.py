from django import forms
from zoneinfo import ZoneInfo
from .models import College, Department, Office, User
from .education import LEVEL_CHOICES, YEAR_CHOICES
from .colleges import COLLEGE_CHOICES, get_unit_choices
from django.utils import timezone
from apps.core.models import CollegeAnnouncement
from .school_forms import SchoolBoundModelForm

class StudentProfileForm(SchoolBoundModelForm):
    educational_level = forms.ChoiceField(choices=[], label='Educational level')
    year_level = forms.ChoiceField(choices=[], label='Grade / year')
    department = forms.ModelChoiceField(queryset=Department.objects.none(), required=False)

    class Meta:
        model = User
        fields = ['student_id', 'educational_level', 'year_level', 'department']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        offered = self.instance.school.educational_levels
        self.fields['educational_level'].choices = [('', 'Select your level')] + [(k, v) for k, v in LEVEL_CHOICES if k in offered]
        self.fields['department'].queryset = Department.objects.filter(school=self.instance.school, is_active=True).select_related('college')
        self.fields['department'].empty_label = 'Select your department'
        self.fields['department'].help_text = 'Only active departments in your school are listed. Contact your Super Admin if yours is missing.'
        self.fields['student_id'].required = True
        self.fields['student_id'].error_messages['required'] = 'Enter your Student ID.'
        if len(offered) == 1:
            self.initial['educational_level'] = offered[0]
        level = self.data.get('educational_level') if self.is_bound else self.initial.get('educational_level', '')
        self.fields['year_level'].choices = [('', 'Select your grade / year')] + YEAR_CHOICES.get(level, [])
        if len(offered) == 1 and (not self.is_bound or self.data.get('educational_level') == offered[0]):
            self.fields['educational_level'].widget = forms.HiddenInput()

    def clean(self):
        data = super().clean()
        level, department = data.get('educational_level'), data.get('department')
        if level == 'college':
            if not department:
                self.add_error('department', 'Select an active department in your school.')
            else:
                self.instance.college = department.college.code if department.college else ''
        elif level:
            if department:
                self.add_error('department', 'A department is only needed for college students.')
            self.instance.department = None
            self.instance.college = None
        return data

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
    student_levels = forms.MultipleChoiceField(choices=[], required=False, label='Student educational levels', widget=forms.CheckboxSelectMultiple)
    expiry_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'id': 'ann-expiry'}),
        help_text="Leave blank to auto-expire 7 days after posting."
    )

    class Meta:
        model = CollegeAnnouncement
        fields = ['message', 'audience', 'student_levels']
        widgets = {'audience': forms.Select(attrs={'id': 'ann-audience'})}

    def __init__(self, *args, target_levels=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.target_levels = target_levels
        if target_levels:
            self.fields['student_levels'].choices = [(k, v) for k, v in LEVEL_CHOICES if k in self.instance.school.educational_levels]
        else:
            self.fields.pop('student_levels')
        self.fields['expiry_date'].widget.attrs['min'] = timezone.localdate(timezone=ZoneInfo('Asia/Manila')).isoformat()

    def clean(self):
        data = super().clean()
        if self.target_levels:
            if data.get('audience') in ('students', 'both') and not data.get('student_levels'):
                self.add_error('student_levels', 'Select at least one student educational level.')
            elif data.get('audience') == 'faculty':
                data['student_levels'] = []
        return data

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
        fields = ['name', 'code', 'description']

    def clean_name(self):
        value = self.cleaned_data['name']
        if College.objects.filter(name__iexact=value).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('A college with this name already exists in your school.')
        return value

    def clean_code(self):
        return self.cleaned_data['code'].strip().upper()

class CollegeDescriptionForm(SchoolBoundModelForm):
    class Meta:
        model = College
        fields = ['description']

class OfficeForm(SchoolBoundModelForm):
    class Meta:
        model = Office
        fields = ['name', 'code', 'description']

    def clean_name(self):
        value = self.cleaned_data['name']
        if Office.objects.filter(name__iexact=value).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('An office with this name already exists in your school.')
        return value

    def clean_code(self):
        return self.cleaned_data['code'].strip().upper()

class OfficeDescriptionForm(SchoolBoundModelForm):
    class Meta:
        model = Office
        fields = ['description']
