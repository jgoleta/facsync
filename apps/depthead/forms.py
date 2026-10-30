from django import forms
from apps.core.models import FacultyInvite, OfficeClosure
from .services.shared_windows import DURATION_CHOICES
from datetime import timedelta
from apps.core.school_forms import SchoolBoundModelForm


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
    class Meta:
        model = FacultyInvite
        fields = ['email']

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
