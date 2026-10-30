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
