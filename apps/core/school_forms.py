from django import forms
from django.core.exceptions import PermissionDenied

from .school_scope import require_school


class SchoolBoundModelForm(forms.ModelForm):
    """Bind ownership before validation; never accept it from submitted fields."""
    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        school = require_school(school)
        if self.instance.school_id is not None and self.instance.school_id != school.pk:
            raise PermissionDenied('This form belongs to another school.')
        self.instance.school = school


class UnitStudentLevelsMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .education import LEVEL_CHOICES
        self.fields['student_levels'] = forms.MultipleChoiceField(
            label='Educational levels served', required=True, widget=forms.CheckboxSelectMultiple,
            choices=[(key, label) for key, label in LEVEL_CHOICES if key in self.instance.school.educational_levels],
            error_messages={'required': 'Select at least one educational level served by this department or office.'})

    def clean_student_levels(self):
        from .education import ordered_levels
        return ordered_levels(self.cleaned_data['student_levels'])
