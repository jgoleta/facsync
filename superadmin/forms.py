from django import forms
from core.departments import get_department_choices
from core.models import DeptHeadInvite

class DeptHeadInviteForm(forms.ModelForm):
    department = forms.ChoiceField(choices=get_department_choices)

    class Meta:
        model = DeptHeadInvite
        fields = ['email', 'department']

    def clean_email(self):
        email = self.cleaned_data['email']
        if DeptHeadInvite.objects.filter(email__iexact=email, used=False).exists():
            raise forms.ValidationError("This email already has a pending Dept Head invite.")
        return email