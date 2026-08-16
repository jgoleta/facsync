"""Department labels shared by forms, views, and API responses."""

DEPARTMENT_CHOICES = [
    ('chss', 'College of Humanities and Social Sciences'),
    ('cba', 'College of Business and Accountancy'),
    ('ccs', 'College of Computer Studies'),
    ('ced', 'College of Education'),
    ('csea', 'College of Science, Engineering, and Architecture'),
    ('con', 'College of Nursing'),
    ('col', 'College of Law'),
]

DEPARTMENT_LABELS = dict(DEPARTMENT_CHOICES)


def get_department_label(value):
    """Return the full department name for a stored code or abbreviation."""
    # Normalize legacy values such as CCS while preserving already-full names.
    if value is None:
        return ''

    department = str(value).strip()
    if not department:
        return ''

    return DEPARTMENT_LABELS.get(department.lower(), {
        'CCS': 'College of Computer Studies',
    }.get(department.upper(), department))
