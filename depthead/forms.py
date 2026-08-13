from django import forms
from core.models import FacultyInvite

class FacultyInviteForm(forms.ModelForm):
    class Meta:
        model = FacultyInvite
        fields = ['email']

    def clean_email(self):
        email = self.cleaned_data['email']
        if FacultyInvite.objects.filter(email__iexact=email, used=False).exists():
            raise forms.ValidationError("This email already has a pending invite.")
        return email