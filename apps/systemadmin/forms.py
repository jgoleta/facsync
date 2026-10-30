import re

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.invitations import validate_invite_identity
from apps.core.models import School, SchoolDomain, SuperAdminInvite, User
from apps.core.school_models import validate_school_domain


class SchoolForm(forms.ModelForm):
    domains = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}),
        help_text='One domain per line. Domains must end in .edu.ph and can belong to only one school.')

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
        if len(domains) != len(set(domains)):
            raise ValidationError('Enter each domain only once.')
        for domain in domains:
            validate_school_domain(domain)
        if SchoolDomain.objects.filter(domain__in=domains).exclude(school_id=self.instance.pk).exists():
            raise ValidationError('One of these domains is already assigned to another school.')
        return sorted(domains)

    def save(self, *, actor):
        # New domains go first so replacing the final domain never leaves a gap.
        with transaction.atomic():
            school = super().save(commit=False)
            school.save(actor=actor)
            desired = set(self.cleaned_data['domains'])
            existing = {item.domain: item for item in school.domains.all()}
            for domain in sorted(desired - existing.keys()):
                SchoolDomain(school=school, domain=domain).save(actor=actor)
            for domain in sorted(existing.keys() - desired):
                existing[domain].delete(actor=actor)
            return school


class SuperAdminInviteForm(forms.ModelForm):
    class Meta:
        model = SuperAdminInvite
        fields = ['email', 'school']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['school'].queryset = School.objects.filter(is_active=True)
        self.fields['email'].help_text = 'Use the Google account they will sign in with. Any email domain is allowed.'

    def clean_email(self):
        return validate_invite_identity(self.cleaned_data['email'].strip().lower(), instance=self.instance)


class SuperAdminEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name']
