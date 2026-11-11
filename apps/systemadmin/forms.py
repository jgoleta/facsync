import re

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.invitations import validate_invite_identity
from apps.core.models import School, SchoolDomain, SuperAdminInvite, User
from apps.core.school_models import validate_school_domain
from apps.core.school_admin_access import FEATURES


class SchoolForm(forms.ModelForm):
    domains = forms.CharField(label='School email domain', widget=forms.TextInput,
        help_text='One exact school-owned domain, without @ or https://. Personal email providers are not allowed.')

    class Meta:
        model = School
        fields = ['name', 'code']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['code'].disabled = True
            self.fields['code'].help_text = 'School codes are locked after creation.'
            self.fields['domains'].initial = '\n'.join(self.instance.domains.values_list('domain', flat=True))

    def clean_code(self):
        return self.cleaned_data['code'].strip().upper()

    def clean_domains(self):
        domains = [value.lower() for value in re.split(r'[\s,;]+', self.cleaned_data['domains'].strip()) if value]
        if not domains:
            raise ValidationError('Assign at least one institutional domain.')
        if len(domains) != 1:
            raise ValidationError('Assign exactly one email domain to this school.')
        for domain in domains:
            validate_school_domain(domain)
        if SchoolDomain.objects.filter(domain__in=domains).exclude(school_id=self.instance.pk).exists():
            raise ValidationError('One of these domains is already assigned to another school.')
        return sorted(domains)

    def save(self, *, actor):
        # Replace the existing row in place: the database permits one per school.
        with transaction.atomic():
            school = super().save(commit=False)
            school.save(actor=actor)
            domain = self.cleaned_data['domains'][0]
            existing = list(school.domains.select_for_update())
            if len(existing) > 1:
                raise ValidationError('This school has multiple domains. Resolve them before replacing its domain.')
            row = existing[0] if existing else SchoolDomain(school=school)
            if row.domain != domain:
                row.domain = domain
                row.save(actor=actor)
            return school


class SuperAdminInviteForm(forms.ModelForm):
    school_admin_permissions = forms.MultipleChoiceField(choices=FEATURES, required=False, widget=forms.CheckboxSelectMultiple)
    class Meta:
        model = SuperAdminInvite
        fields = ['email', 'school', 'school_admin_full_access', 'school_admin_permissions']
        labels = {'school_admin_full_access': 'Full School Admin access', 'school_admin_permissions': 'Feature access'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['school'].queryset = School.objects.filter(is_active=True)
        self.fields['email'].help_text = 'Use the Google account they will sign in with. Any email domain is allowed.'

    def clean_school_admin_permissions(self):
        return ['overview', *[key for key in self.cleaned_data['school_admin_permissions'] if key != 'overview']]

    def clean_email(self):
        return validate_invite_identity(self.cleaned_data['email'].strip().lower(), instance=self.instance)


class SuperAdminEditForm(forms.ModelForm):
    school_admin_permissions = forms.MultipleChoiceField(choices=FEATURES, required=False, widget=forms.CheckboxSelectMultiple)
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'school_admin_full_access', 'school_admin_permissions']
        labels = {'school_admin_full_access': 'Full School Admin access', 'school_admin_permissions': 'Feature access'}

    def clean_school_admin_permissions(self):
        return ['overview', *[key for key in self.cleaned_data['school_admin_permissions'] if key != 'overview']]
