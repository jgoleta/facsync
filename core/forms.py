from django import forms
from .models import User

DEPARTMENT_CHOICES = [
    ('chss', 'College of Humanities and Social Sciences'),
    ('cba', 'College of Business and Accountancy'),
    ('ccs', 'College of Computer Studies'),
    ('ced', 'College of Education'),
    ('csea', 'College of Science, Engineering, and Architecture'),
    ('con', 'College of Nursing'),
    ('col', 'College of Law'),
]

class StudentProfileForm(forms.ModelForm):
    department = forms.ChoiceField(choices=DEPARTMENT_CHOICES)

    class Meta:
        model = User
        fields = ['student_id', 'department', 'year_level']