"""College labels shared by forms, views, and API responses."""


COLLEGE_CHOICES = [
    ('chss', 'College of Humanities and Social Sciences'),
    ('cba', 'College of Business and Accountancy'),
    ('ccs', 'College of Computer Studies'),
    ('ced', 'College of Education'),
    ('csea', 'College of Science, Engineering, and Architecture'),
    ('con', 'College of Nursing'),
    ('col', 'College of Law'),
]

COLLEGE_LABELS = dict(COLLEGE_CHOICES)


def get_college_label(value):
    """Return the full college name for a stored code or abbreviation."""
    # Normalize legacy values such as CCS while preserving already-full names.
    if value is None:
        return ''

    college = str(value).strip()
    if not college:
        return ''

    return COLLEGE_LABELS.get(college.lower(), {
        'CCS': 'College of Computer Studies',
    }.get(college.upper(), college))

def get_college_choices():
    from apps.core.models import College
    return [(d.code, d.name) for d in College.objects.all().order_by('name')]