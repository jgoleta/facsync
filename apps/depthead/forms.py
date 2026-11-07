from django import forms
from django.core.validators import MaxValueValidator
from apps.core.models import Department, FacultyInvite, OfficeClosure
from .services.shared_windows import DURATION_CHOICES
from datetime import date, timedelta
from apps.core.school_forms import SchoolBoundModelForm


class AnalyticsDateRangeForm(forms.Form):
    start_date = forms.DateField(label='Start date', input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}))
    end_date = forms.DateField(label='End date', input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'max': '9999-12-30'}),
        # Analytics uses an exclusive next-day boundary.
        validators=[MaxValueValidator(date(9999, 12, 30))])

    def clean(self):
        data = super().clean()
        if data.get('start_date') and data.get('end_date') and data['start_date'] > data['end_date']:
            self.add_error('end_date', 'End date must be on or after the start date.')
        elif data.get('start_date') and data.get('end_date'):
            try:
                data['start_date'] - timedelta(days=(data['end_date'] - data['start_date']).days + 1)
            except OverflowError:
                self.add_error('start_date', 'Choose a later start date or a shorter date range.')
        return data


class WeekDaySelect(forms.Select):
    def __init__(self, *, disabled_dates, **kwargs):
        super().__init__(**kwargs)
        self.disabled_dates = disabled_dates

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if str(value) in self.disabled_dates:
            option['attrs']['disabled'] = True
        return option


class SharedWindowForm(forms.Form):
    date = forms.DateField()
    duration = forms.TypedChoiceField(choices=DURATION_CHOICES, coerce=int)

    def __init__(self, *args, week, **kwargs):
        super().__init__(*args, **kwargs)
        self.week = week
        self.fields['date'].initial = week['today'] if not week['ended'] else week['week_end']
        self.fields['duration'].initial = 120
        days = [week['week_start'] + timedelta(days=offset) for offset in range(5)]
        self.fields['date'].widget = WeekDaySelect(
            choices=[(day.isoformat(), f'{day:%a}, {day:%b} {day.day}') for day in days],
            disabled_dates={day.isoformat() for day in days if day < week['today'] and not week['ended']},
        )

    def clean_date(self):
        day = self.cleaned_data['date']
        if ((not self.week['ended'] and day < self.week['today'])
                or not self.week['week_start'] <= day <= self.week['week_end']):
            raise forms.ValidationError('Choose a remaining Monday–Friday date in the current week.')
        return day

class FacultyInviteForm(SchoolBoundModelForm):
    department = forms.ModelChoiceField(queryset=Department.objects.none(), required=False)
    class Meta:
        model = FacultyInvite
        fields = ['email', 'department']

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and user.role == 'depthead':
            from .scope import managed_departments
            self.fields['department'].queryset = managed_departments(user)
            self.fields['department'].required = True
        else:
            self.fields.pop('department')

    def clean_email(self):
        from apps.core.invitations import validate_invite_identity
        return validate_invite_identity(self.cleaned_data['email'], instance=self.instance)

class OfficeClosureForm(SchoolBoundModelForm):
    class Meta:
        model = OfficeClosure
        fields = ['is_closed', 'reason', 'closure_start', 'closure_end']
        widgets = {
            'is_closed': forms.CheckboxInput(attrs={'class': 'toggle-switch', 'id': 'closure-toggle'}),
            'reason': forms.Textarea(attrs={'rows': 2}),
            'closure_start': forms.DateInput(attrs={'type': 'date'}),
            'closure_end': forms.DateInput(attrs={'type': 'date'}),
        }
