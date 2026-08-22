from django import forms
from core.departments import get_department_choices
from core.models import DeptHeadInvite, FacultyInvite

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

class FacultySuperInviteForm(forms.ModelForm):
    department = forms.ChoiceField(choices=[])

    class Meta:
        model = FacultyInvite
        fields = ['email', 'department']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].choices = get_department_choices()

    def clean_email(self):
        email = self.cleaned_data['email']
        if FacultyInvite.objects.filter(email__iexact=email, used=False).exists():
            raise forms.ValidationError("This email already has a pending invite.")
        return email