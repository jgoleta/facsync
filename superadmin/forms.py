from django import forms
from core.colleges import get_college_choices
from core.models import DeptHeadInvite, FacultyInvite, User

class DeptHeadInviteForm(forms.ModelForm):
    college = forms.ChoiceField(choices=get_college_choices)
    title = forms.ChoiceField(choices=User.TITLE_CHOICES, required=True)

    class Meta:
        model = DeptHeadInvite
        fields = ['email', 'college']

    def clean_email(self):
        email = self.cleaned_data['email']
        if DeptHeadInvite.objects.filter(email__iexact=email, used=False).exists():
            raise forms.ValidationError("This email already has a pending College Head invite.")
        return email

class FacultySuperInviteForm(forms.ModelForm):
    college = forms.ChoiceField(choices=[])

    class Meta:
        model = FacultyInvite
        fields = ['email', 'college']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['college'].choices = get_college_choices()

    def clean_email(self):
        email = self.cleaned_data['email']
        if FacultyInvite.objects.filter(email__iexact=email, used=False).exists():
            raise forms.ValidationError("This email already has a pending invite.")
        return email
