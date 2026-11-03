from django import forms
from apps.core.colleges import get_college_choices, get_unit_choices
from apps.core.models import DeptHeadInvite, FacultyInvite, OfficeAdminInvite, User
from apps.core.invitations import validate_invite_identity
from apps.core.school_forms import SchoolBoundModelForm

class DeptHeadInviteForm(SchoolBoundModelForm):
    college = forms.ChoiceField(choices=get_college_choices)
    title = forms.ChoiceField(choices=User.TITLE_CHOICES, required=True)

    class Meta:
        model = DeptHeadInvite
        fields = ['email', 'college', 'title']

    def clean_email(self):
        return validate_invite_identity(self.cleaned_data['email'], instance=self.instance)

class FacultySuperInviteForm(SchoolBoundModelForm):
    college = forms.ChoiceField(choices=[])

    class Meta:
        model = FacultyInvite
        fields = ['email', 'college']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['college'].choices = get_unit_choices()

class OfficeAdminInviteForm(SchoolBoundModelForm):
    office = forms.ChoiceField(choices=[])

    class Meta:
        model = OfficeAdminInvite
        fields = ['email', 'office']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.core.models import Office
        self.fields['office'].choices = [(o.code, o.name) for o in Office.objects.all().order_by('name')]

    def clean_email(self):
        return validate_invite_identity(self.cleaned_data['email'], instance=self.instance)
