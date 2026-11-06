from django import forms
from django.core.exceptions import ValidationError

from .education import LEVEL_CHOICES
from .models import School, SchoolDomain
from .school_requests import email_domain


class SchoolRegistrationForm(forms.Form):
    school_name = forms.CharField(max_length=150, label='School name')
    school_code = forms.CharField(max_length=20, label='School abbreviation/code',
        help_text='For example ADNU. The code is locked once the school is approved.')
    educational_levels = forms.MultipleChoiceField(choices=LEVEL_CHOICES, initial=['college'],
        widget=forms.CheckboxSelectMultiple, label='Educational levels offered')
    representative_name = forms.CharField(max_length=150, label='Your name')
    position = forms.CharField(max_length=150, label='Your position at the school')
    contact_email = forms.EmailField(label='School contact email',
        help_text='An official contact on your school domain, preferably someone else who can confirm your authority.')
    website = forms.URLField(required=False, label='Official school website or contact page (optional)',
        help_text='The reviewer will independently check the school contact.')

    def __init__(self, *args, identity, **kwargs):
        self.identity = identity
        super().__init__(*args, **kwargs)

    def clean_school_code(self):
        code = self.cleaned_data['school_code'].strip().upper()
        School._meta.get_field('code').clean(code, None)
        if School.objects.filter(code__iexact=code).exists():
            raise ValidationError('This school code is already in use. Choose another code.')
        return code

    def clean_contact_email(self):
        email = self.cleaned_data['contact_email'].lower()
        if email_domain(email) != self.identity['domain']:
            raise ValidationError('Use an official contact email on the school domain shown above.')
        return email

    def clean(self):
        data = super().clean()
        if SchoolDomain.objects.filter(domain__iexact=self.identity['domain']).exists():
            raise ValidationError('This school domain is already registered. Contact your school\'s Super Admin.')
        return data


class SchoolRequestReviewForm(forms.Form):
    decision = forms.ChoiceField(choices=[('approve', 'Approve'), ('reject', 'Reject')])
    verification_notes = forms.CharField(required=False, max_length=2000, widget=forms.Textarea(attrs={'rows': 4}),
        help_text='Required for approval. Record the official source checked and how authority was confirmed. Private to FacSync Administration.')
    decision_reason = forms.CharField(required=False, max_length=1000, widget=forms.Textarea(attrs={'rows': 3}),
        label='Reason shared with applicant', help_text='Required for rejection. Do not include private verification notes.')

    def clean(self):
        data = super().clean()
        field = 'verification_notes' if data.get('decision') == 'approve' else 'decision_reason'
        if data.get('decision') and not data.get(field):
            self.add_error(field, 'Complete this field before submitting the decision.')
        return data
