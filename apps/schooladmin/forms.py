from django import forms
from django.db.models import Q
from apps.core.colleges import get_college_choices, get_unit_choices
from apps.core.models import College, Department, DeptHeadInvite, FacultyInvite, Office, OfficeAdminInvite, User
from apps.core.invitations import unique_registered_user, validate_invite_identity
from apps.core.school_forms import SchoolBoundModelForm, UnitStudentLevelsMixin
from apps.core.education import LEVEL_CHOICES
from apps.core.role_access import has_role
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

def resolve_head_departments(form, data):
    if data.get('title') == 'dean':
        college = data.get('assigned_college')
        if not college:
            form.add_error('assigned_college', 'Choose a college.')
            data['departments'] = []
        else:
            data['departments'] = list(form.fields['departments'].queryset.filter(college=college))
            if not data['departments']:
                form.add_error('assigned_college', 'This college has no active departments.')
    elif not data.get('departments'):
        form.add_error('departments', 'Choose a department.')
    return list(data.get('departments') or [])


class DeptHeadInviteForm(SchoolBoundModelForm):
    assigned_college = forms.ModelChoiceField(queryset=College.objects.none(), required=False)
    title = forms.ChoiceField(choices=User.TITLE_CHOICES, required=True)
    educational_level = forms.ChoiceField(choices=[], required=True, label='Educational level')
    departments = forms.ModelMultipleChoiceField(queryset=Department.objects.none(), required=False)
    faculty_department = forms.ModelChoiceField(queryset=Department.objects.none(), required=False)

    class Meta:
        model = DeptHeadInvite
        fields = ['email', 'educational_level', 'departments', 'title', 'include_faculty_access', 'faculty_department']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        department_queryset = Department.objects.filter(
            school=self.instance.school, is_active=True).select_related('college')
        self.fields['departments'].queryset = department_queryset
        self.fields['assigned_college'].queryset = College.objects.filter(school=self.instance.school, is_active=True)
        self.fields['faculty_department'].queryset = department_queryset
        self.fields['educational_level'].choices = [
            ('', 'Select an educational level'),
            *[(key, label) for key, label in LEVEL_CHOICES if key in self.instance.school.educational_levels],
        ]

    def clean(self):
        data = super().clean()
        departments = resolve_head_departments(self, data)
        level = data.get('educational_level')
        if data.get('title') == 'dean' and level != 'college':
            self.add_error('title', 'College Head is only available for College departments.')
        if data.get('title') == 'chairperson' and len(departments) > 1:
            self.add_error('departments', 'Department Heads can be assigned to only one department.')
        if data.get('title') != 'dean' and level and any(level not in (department.student_levels or []) for department in departments):
            self.add_error('departments', 'Choose departments that serve the selected educational level.')
        if departments:
            self.instance.college = departments[0].college.code if departments[0].college else ''
        if data.get('include_faculty_access') and not getattr(self, 'existing_faculty', None):
            home = data.get('faculty_department')
            if len(departments) == 1:
                data['faculty_department'] = departments[0]
            elif home is None:
                self.add_error('faculty_department', 'Choose the Faculty home department.')
            elif home.pk not in {department.pk for department in departments}:
                self.add_error('faculty_department', 'Choose one of the selected departments.')
        else:
            data['faculty_department'] = None
        return data

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        existing = unique_registered_user(email)
        if existing and existing.school_id == self.instance.school_id and has_role(existing, 'faculty'):
            self.existing_faculty = existing
            return email
        return validate_invite_identity(email, instance=self.instance)

class AcademicUnitFilterSelect(forms.Select):
    """Expose the academic level served by each assignment option to the UI."""

    def __init__(self, *args, unit_levels=None, **kwargs):
        self.unit_levels = unit_levels or {}
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        levels = self.unit_levels.get(str(value), ())
        if levels:
            option['attrs']['data-educational-levels'] = ','.join(levels)
        return option


class FacultySuperInviteForm(SchoolBoundModelForm):
    educational_level = forms.ChoiceField(choices=[], label='Educational level or office')
    unit = forms.ChoiceField(choices=[], label='Department or office', widget=AcademicUnitFilterSelect)

    class Meta:
        model = FacultyInvite
        fields = ['email']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        school = self.instance.school
        self.fields['educational_level'].choices = [
            ('', 'Select an educational level or office'),
            *[(key, label) for key, label in LEVEL_CHOICES if key in school.educational_levels],
            ('office', 'Office'),
        ]
        self.fields['unit'].choices = academic_unit_choices(school)
        departments = Department.objects.filter(school=school, is_active=True)
        offices = Office.objects.filter(school=school, is_active=True)
        self.fields['unit'].widget.unit_levels = {
            f'department:{department.pk}': tuple(department.student_levels or [])
            for department in departments
        }
        self.fields['unit'].widget.unit_levels.update({
            f'office:{office.pk}': ('office',)
            for office in offices
        })

    def clean(self):
        data = super().clean()
        unit = data.get('unit')
        level = data.get('educational_level')
        if unit and level:
            department, office = resolve_academic_unit(unit, self.instance.school)
            if level == 'office' and not office:
                self.add_error('unit', 'Choose an office for the Office filter.')
            elif level != 'office' and office:
                self.add_error('unit', 'Choose a department for the selected educational level.')
            elif department and level not in (department.student_levels or []):
                self.add_error('unit', 'Choose a department that serves the selected educational level.')
            else:
                self.instance.department = department
                self.instance.college = (department.college.code if department.college else '') if department else office.code
        return data

    def clean_email(self):
        return validate_invite_identity(self.cleaned_data['email'].strip().lower(), instance=self.instance)

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
        fields = ['name', 'code', 'student_levels', 'college']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['student_levels'] = forms.ChoiceField(
            choices=[('', 'Select an educational level'),
                     *[(key, label) for key, label in LEVEL_CHOICES
                       if key in self.instance.school.educational_levels]],
            required=True, label='Educational level',
        )
        self.fields['college'].queryset = College.objects.filter(school=self.instance.school).filter(Q(is_active=True) | Q(pk=self.instance.college_id))
        self.fields['college'].empty_label = 'No college'
        if not self.instance.school.offers_college:
            self.fields.pop('college')
        if self.instance.pk:
            self.fields['code'].disabled = True

    def clean_code(self):
        return self.cleaned_data['code'].strip().upper()

    def clean_student_levels(self):
        return [self.cleaned_data['student_levels']]

    def clean(self):
        data = super().clean()
        if not self.instance.school.offers_college and self.data.get('college'):
            raise forms.ValidationError('College assignments are unavailable while College is not an offered educational level.')
        if data.get('student_levels') != ['college']:
            self.instance.college = None
        return data


class OfficeStudentLevelsForm(UnitStudentLevelsMixin, SchoolBoundModelForm):
    class Meta:
        model = Office
        fields = ['student_levels']


class HeadAssignmentForm(forms.Form):
    assigned_college = forms.ModelChoiceField(queryset=College.objects.none(), required=False)
    title = forms.ChoiceField(choices=User.TITLE_CHOICES)
    educational_level = forms.ChoiceField(choices=[], required=True)
    departments = forms.ModelMultipleChoiceField(queryset=Department.objects.none(), required=False)

    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['departments'].queryset = Department.objects.filter(school=school, is_active=True).select_related('college')
        self.fields['assigned_college'].queryset = College.objects.filter(school=school, is_active=True)
        self.fields['educational_level'].choices = [
            ('', 'Select an educational level'),
            *[(key, label) for key, label in LEVEL_CHOICES if key in school.educational_levels],
        ]

    def clean(self):
        data = super().clean()
        departments = resolve_head_departments(self, data)
        level = data.get('educational_level')
        if data.get('title') == 'dean' and level != 'college':
            self.add_error('title', 'College Head is only available for College departments.')
        if data.get('title') == 'chairperson' and len(departments) > 1:
            self.add_error('departments', 'Department Heads can be assigned to only one department.')
        if data.get('title') != 'dean' and level and any(level not in (department.student_levels or []) for department in departments):
            self.add_error('departments', 'Choose departments that serve the selected educational level.')
        return data


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
        fields = ['email', 'office', 'include_faculty_access']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.core.models import Office
        self.fields['office'].choices = [(o.code, o.name) for o in Office.objects.filter(is_active=True).order_by('name')]

    def clean_email(self):
        return validate_invite_identity(self.cleaned_data['email'].strip().lower(), instance=self.instance)
