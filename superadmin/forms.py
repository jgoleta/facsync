from django import forms
from core.models import DeptHeadInvite
from core.forms import DEPARTMENT_CHOICES

class DeptHeadInviteForm(forms.ModelForm):
    department = forms.ChoiceField(choices=DEPARTMENT_CHOICES)

    class Meta:
        model = DeptHeadInvite
        fields = ['email', 'department']

    def clean_email(self):
        email = self.cleaned_data['email']
        if DeptHeadInvite.objects.filter(email__iexact=email, used=False).exists():
            raise forms.ValidationError("This email already has a pending Dept Head invite.")
        return email