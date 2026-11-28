from django import forms
from django.db.models import Q
from apps.core.colleges import get_college_choices, get_unit_choices
from apps.core.models import College, Department, DeptHeadInvite, FacultyInvite, Office, OfficeAdminInvite, User
from apps.core.invitations import validate_invite_identity
from apps.core.school_forms import SchoolBoundModelForm, UnitStudentLevelsMixin
from apps.core.education import LEVEL_CHOICES
from apps.core.school_models import SchoolDomain, validate_school_domain


class SchoolDetailsForm(forms.Form):
    name = forms.CharField(max_length=150, label='School name')
    domain = forms.CharField(max_length=253, label='School email domain',
        help_text='One exact school-owned domain, without @ or https://. Personal email providers are not allowed.')

    def __init__(self, *args, school, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)

    def clean_domain(self):
        domain = self.cleaned_data['domain'].strip().lower()
        validate_school_domain(domain)
        if SchoolDomain.objects.filter(domain__iexact=domain).exclude(school=self.school).exists():
            raise forms.ValidationError('This domain is already assigned to another school.')
        return domain


class SchoolEducationForm(forms.Form):
    educational_levels = forms.MultipleChoiceField(choices=LEVEL_CHOICES, widget=forms.CheckboxSelectMultiple,
        label='Educational levels offered', error_messages={'required': 'Select at least one educational level.'})

class DeptHeadInviteForm(SchoolBoundModelForm):
    title = forms.ChoiceField(choices=User.TITLE_CHOICES, required=True)
    faculty_id = forms.CharField(max_length=64, required=False, label='Faculty ID')

    class Meta:
        model = DeptHeadInvite
        fields = ['email', 'departments', 'title', 'include_faculty_access', 'faculty_id', 'faculty_department']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['departments'].queryset = Department.objects.filter(
            school=self.instance.school, is_active=True).select_related('college')
        self.fields['departments'].required = True
        self.fields['faculty_department'].queryset = self.fields['departments'].queryset

    def clean(self):
        data = super().clean()
        departments = data.get('departments')
        if departments:
            first = departments[0]
            self.instance.college = first.college.code if first.college else ''
        if data.get('include_faculty_access'):
            faculty_id = (data.get('faculty_id') or '').strip()
            if not faculty_id:
                self.add_error('faculty_id', 'Enter a Faculty ID when including Faculty access.')
            else:
                from apps.faculty.models import FacultyProfile
                reserved = DeptHeadInvite._base_manager.filter(used=False, faculty_id=faculty_id).exclude(pk=self.instance.pk).exists()
                reserved = reserved or OfficeAdminInvite._base_manager.filter(used=False, faculty_id=faculty_id).exists()
                if FacultyProfile._base_manager.filter(pk=faculty_id).exists() or reserved:
                    self.add_error('faculty_id', 'This Faculty ID is already in use.')
            home = data.get('faculty_department')
            if departments:
                if home is None and len(departments) == 1:
                    home = data['faculty_department'] = departments[0]
                if home is None:
                    self.add_error('faculty_department', 'Choose the Faculty home department.')
                elif home.pk not in {d.pk for d in departments}:
                    self.add_error('faculty_department', 'Choose one of the departments this administrator will manage.')
                elif home.college_id and not home.college.is_active:
                    self.add_error('faculty_department', 'Choose a department in an active college.')
        else:
            data['faculty_id'] = ''
            data['faculty_department'] = None
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
    offices = Office.objects.filter(school=school, is_active=True).order_by('name')
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
        office = Office.objects.filter(pk=pk, school=school, is_active=True).first()
        if office:
            return None, office
    raise forms.ValidationError('Choose an active department or an office in your school.')


class DepartmentForm(UnitStudentLevelsMixin, SchoolBoundModelForm):
    class Meta:
        model = Department
        fields = ['name', 'code', 'college', 'description', 'student_levels']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['college'].queryset = College.objects.filter(school=self.instance.school).filter(Q(is_active=True) | Q(pk=self.instance.college_id))
        self.fields['college'].empty_label = 'No college'
        if not self.instance.school.offers_college:
            self.fields.pop('college')
        if self.instance.pk:
            self.fields['code'].disabled = True

    def clean_description(self):
        if self.instance.pk and 'description' not in self.data:
            return self.instance.description
        return self.cleaned_data['description']

    def clean_code(self):
        return self.cleaned_data['code'].strip().upper()

    def clean(self):
        data = super().clean()
        if not self.instance.school.offers_college and self.data.get('college'):
            raise forms.ValidationError('College assignments are unavailable while College is not an offered educational level.')
        return data


class OfficeStudentLevelsForm(UnitStudentLevelsMixin, SchoolBoundModelForm):
    class Meta:
        model = Office
        fields = ['student_levels']


class HeadAssignmentForm(forms.Form):
    title = forms.ChoiceField(choices=User.TITLE_CHOICES)
    departments = forms.ModelMultipleChoiceField(queryset=Department.objects.none())

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
    faculty_id = forms.CharField(max_length=64, required=True, label='Faculty ID')

    class Meta:
        model = OfficeAdminInvite
        fields = ['email', 'office', 'faculty_id']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.core.models import Office
        self.fields['office'].choices = [(o.code, o.name) for o in Office.objects.filter(is_active=True).order_by('name')]

    def clean_email(self):
        return validate_invite_identity(self.cleaned_data['email'].strip().lower(), instance=self.instance)

    def clean_faculty_id(self):
        value = self.cleaned_data['faculty_id'].strip()
        from apps.faculty.models import FacultyProfile
        if FacultyProfile._base_manager.filter(pk=value).exists():
            raise forms.ValidationError('This Faculty ID is already in use.')
        return value
