from django import forms
from django.core.exceptions import ValidationError

from .school_domains import school_domain_from_email


class SchoolInquiryForm(forms.Form):
    representative_name = forms.CharField(max_length=150, label='Your full name')
    email = forms.EmailField(label='School-issued Google email')
    position = forms.CharField(max_length=150, label='Your position at the school')
    school_name = forms.CharField(max_length=150)
    declaration = forms.BooleanField(label='I am authorized to contact FacSync on behalf of this school.')
    website_confirmation = forms.CharField(required=False, widget=forms.HiddenInput)

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        school_domain_from_email(email)
        return email

    def clean_website_confirmation(self):
        if self.cleaned_data.get('website_confirmation'):
            raise ValidationError('Unable to submit this inquiry.')
        return ''


class SchoolVerificationForm(forms.Form):
    website = forms.URLField(label='Official school website')
    address = forms.CharField(max_length=500, label='School address')
    official_name = forms.CharField(max_length=150, label='Authorizing official’s full name')
    official_position = forms.CharField(max_length=150, label='Authorizing official’s position')
    contact_email = forms.EmailField(label='Official school contact email')
    authority = forms.CharField(max_length=2000, widget=forms.Textarea(attrs={'rows': 4}),
        label='Explain your authority to register and manage the school')
    letter = forms.FileField(label='Authorization letter (PDF, up to 5 MB)', help_text=(
        'The letter should authorize you to register the school and serve as its first School Admin. '
        'Do not upload IDs or a separate signature image. Redact unrelated personal information. '
        'Evidence is private and deleted 90 days after approval or rejection.'))
    declaration = forms.BooleanField(label='I have permission to submit these details and this authorization letter.')

    def __init__(self, *args, domain, **kwargs):
        self.domain = domain
        super().__init__(*args, **kwargs)

    def clean_contact_email(self):
        email = self.cleaned_data['contact_email'].lower()
        if school_domain_from_email(email) != self.domain:
            raise ValidationError('Use an official contact on the school domain shown above.')
        return email

    def clean_letter(self):
        upload = self.cleaned_data['letter']
        if not upload.name.lower().endswith('.pdf') or not 0 < upload.size <= 5 * 1024 * 1024:
            raise ValidationError('Upload one PDF file no larger than 5 MB.')
        content = upload.read(5 * 1024 * 1024 + 1)
        upload.seek(0)
        if not content.startswith(b'%PDF-') or b'%%EOF' not in content[-1024:]:
            raise ValidationError('This file does not appear to be a complete PDF. Export the letter as PDF and try again.')
        return upload


class SchoolInquiryReviewForm(forms.Form):
    action = forms.ChoiceField(choices=[('send_verification', 'Send verification form'),
        ('request_changes', 'Request verification corrections'),
        ('send_registration', 'Send registration invitation'), ('reject', 'Reject inquiry')])
    private_notes = forms.CharField(max_length=2000, required=False, widget=forms.Textarea(attrs={'rows': 4}),
        label='Private review notes', help_text='Required before inviting registration. Record independently checked sources and confirmation of authority.')
    applicant_message = forms.CharField(max_length=1000, required=False, widget=forms.Textarea(attrs={'rows': 3}),
        label='Message to applicant', help_text='Explain required corrections or the reason for rejection. Never include private review notes.')

    def clean(self):
        data = super().clean()
        if data.get('action') == 'send_registration' and not data.get('private_notes'):
            self.add_error('private_notes', 'Record how authority was verified before inviting registration.')
        if data.get('action') == 'reject' and not data.get('applicant_message'):
            self.add_error('applicant_message', 'Give a reason that can be shared with the applicant.')
        if data.get('action') == 'request_changes' and not data.get('applicant_message'):
            self.add_error('applicant_message', 'Explain what the applicant needs to correct.')
        return data
