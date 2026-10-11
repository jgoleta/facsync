from django import forms
from apps.core.models import FacultyInvite, OfficeClosure
from .services.shared_windows import DURATION_CHOICES


class SharedWindowForm(forms.Form):
    date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    duration = forms.TypedChoiceField(choices=DURATION_CHOICES, coerce=int)

    def __init__(self, *args, week, **kwargs):
        super().__init__(*args, **kwargs)
        self.week = week
        self.fields['date'].initial = week['today'] if not week['ended'] else week['week_end']
        self.fields['duration'].initial = 120
        self.fields['date'].widget.attrs.update(
            min=(week['week_start'] if week['ended'] else week['today']).isoformat(),
            max=week['week_end'].isoformat(),
        )

    def clean_date(self):
        day = self.cleaned_data['date']
        if ((not self.week['ended'] and day < self.week['today'])
                or not self.week['week_start'] <= day <= self.week['week_end']):
            raise forms.ValidationError('Choose a remaining Monday–Friday date in the current week.')
        return day

class FacultyInviteForm(forms.ModelForm):
    class Meta:
        model = FacultyInvite
        fields = ['email']

    def clean_email(self):
        email = self.cleaned_data['email']
        if FacultyInvite.objects.filter(email__iexact=email, used=False).exists():
            raise forms.ValidationError("This email already has a pending invite.")
        return email

class OfficeClosureForm(forms.ModelForm):
    class Meta:
        model = OfficeClosure
        fields = ['is_closed', 'reason', 'closure_start', 'closure_end']
        widgets = {
            'is_closed': forms.CheckboxInput(attrs={'class': 'toggle-switch', 'id': 'closure-toggle'}),
            'reason': forms.Textarea(attrs={'rows': 2}),
            'closure_start': forms.DateInput(attrs={'type': 'date'}),
            'closure_end': forms.DateInput(attrs={'type': 'date'}),
        }
