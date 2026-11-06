from django import forms
from apps.core.colleges import get_college_choices, get_unit_choices
from apps.core.models import College, Department, DeptHeadInvite, FacultyInvite, Office, OfficeAdminInvite, User
from apps.core.invitations import validate_invite_identity
from apps.core.school_forms import SchoolBoundModelForm
from apps.core.education import LEVEL_CHOICES


class SchoolEducationForm(forms.Form):
    educational_levels = forms.MultipleChoiceField(choices=LEVEL_CHOICES, widget=forms.CheckboxSelectMultiple,
        label='Educational levels offered', error_messages={'required': 'Select at least one educational level.'})

class DeptHeadInviteForm(SchoolBoundModelForm):
    title = forms.ChoiceField(choices=User.TITLE_CHOICES, required=True)

    class Meta:
        model = DeptHeadInvite
        fields = ['email', 'departments', 'title']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['departments'].queryset = Department.objects.filter(
            school=self.instance.school, is_active=True).select_related('college')
        self.fields['departments'].required = True

    def clean(self):
        data = super().clean()
        departments = data.get('departments')
        if departments:
            first = departments[0]
            self.instance.college = first.college.code if first.college else ''
        return data

    def clean_email(self):
        return validate_invite_identity(self.cleaned_data['email'].strip().lower(), instance=self.instance)

class FacultySuperInviteForm(SchoolBoundModelForm):
    unit = forms.ChoiceField(choices=[], label='Department or office')

    class Meta:
        model = FacultyInvite
        fields = ['email']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['unit'].choices = academic_unit_choices(self.instance.school)

    def clean_email(self):
        return validate_invite_identity(self.cleaned_data['email'].strip().lower(), instance=self.instance)

    def clean(self):
        data = super().clean()
        unit = data.get('unit')
        if unit:
            department, office = resolve_academic_unit(unit, self.instance.school)
            self.instance.department = department
            self.instance.college = (department.college.code if department.college else '') if department else office.code
        return data


def academic_unit_choices(school):
    departments = Department.objects.filter(school=school, is_active=True).select_related('college')
    offices = Office.objects.filter(school=school).order_by('name')
    return [('', 'Select a department or office'),
            ('Departments', [(f'department:{item.pk}', item.name) for item in departments]),
            ('Offices', [(f'office:{item.pk}', item.name) for item in offices])]


def resolve_academic_unit(value, school):
    kind, _, pk = str(value).partition(':')
    if not pk.isdecimal():
        raise forms.ValidationError('Choose a department or office in your school.')
    if kind == 'department':
        department = Department.objects.filter(pk=pk, school=school, is_active=True).select_related('college').first()
        if department:
            return department, None
    elif kind == 'office':
        office = Office.objects.filter(pk=pk, school=school).first()
        if office:
            return None, office
    raise forms.ValidationError('Choose an active department or an office in your school.')


class DepartmentForm(SchoolBoundModelForm):
    class Meta:
        model = Department
        fields = ['name', 'code', 'college', 'description']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['college'].queryset = College.objects.filter(school=self.instance.school)
        self.fields['college'].empty_label = 'No college'
        if self.instance.pk:
            self.fields['code'].disabled = True

    def clean_code(self):
        return self.cleaned_data['code'].strip().upper()


class HeadAssignmentForm(forms.Form):
    title = forms.ChoiceField(choices=User.TITLE_CHOICES)
    departments = forms.ModelMultipleChoiceField(queryset=Department.objects.none())
    account_status = forms.ChoiceField(choices=[('active', 'Active'), ('deactivated', 'Deactivated')])

    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['departments'].queryset = Department.objects.filter(school=school, is_active=True).select_related('college')


class FacultyAssignmentForm(forms.Form):
    unit = forms.ChoiceField(choices=[])

    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school
        self.fields['unit'].choices = academic_unit_choices(school)

    def clean_unit(self):
        return resolve_academic_unit(self.cleaned_data['unit'], self.school)

class OfficeAdminInviteForm(SchoolBoundModelForm):
    office = forms.ChoiceField(choices=[])

    class Meta:
        model = OfficeAdminInvite
        fields = ['email', 'office']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.core.models import Office
        self.fields['office'].choices = [(o.code, o.name) for o in Office.objects.all().order_by('name')]

    def clean_email(self):
        return validate_invite_identity(self.cleaned_data['email'], instance=self.instance)
