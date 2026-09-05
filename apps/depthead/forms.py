from django import forms
from apps.core.models import FacultyInvite, OfficeClosure

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