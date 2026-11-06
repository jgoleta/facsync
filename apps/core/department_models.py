"""Department foundation. Existing HTTP permission rules are switched separately."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower

from .school_scope import SchoolScopedModel, prepare_school_write


class Department(SchoolScopedModel):
    school = models.ForeignKey('core.School', on_delete=models.PROTECT, related_name='departments')
    college = models.ForeignKey('core.College', on_delete=models.PROTECT, null=True, blank=True,
                                related_name='departments')
    code = models.CharField(max_length=20, validators=[
        RegexValidator(r'^[A-Z][A-Z0-9_-]{1,19}$', 'Use a 2–20 character department code starting with a letter.'),
    ])
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    schedule_template = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(Lower('code'), models.F('school'), name='department_school_code_unique'),
            models.UniqueConstraint(Lower('name'), models.F('school'), name='department_school_name_unique'),
        ]

    def clean(self):
        super().clean()
        college_school = (self._meta.get_field('college').remote_field.model._base_manager
                          .filter(pk=self.college_id).values_list('school_id', flat=True).first()) if self.college_id else None
        if self.college_id and college_school != self.school_id:
            raise ValidationError({'college': 'The college must belong to the department’s school.'})
        if self.pk:
            previous = type(self)._base_manager.filter(pk=self.pk).values('school_id', 'code').first()
            if previous and (previous['school_id'] != self.school_id or previous['code'] != self.code):
                raise ValidationError('A department’s school and code cannot be changed after creation.')

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        self.name = self.name.strip()
        prepare_school_write(self)
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class DepartmentHeadAssignment(SchoolScopedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='department_head_assignments')
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='head_assignments')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'department'], name='head_department_unique')]


class DepartmentInviteAssignment(SchoolScopedModel):
    invite = models.ForeignKey('core.DeptHeadInvite', on_delete=models.CASCADE,
                               related_name='department_assignments')
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='invite_assignments')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['invite', 'department'], name='invite_department_unique')]


def validate_department_links(instance):
    """Optional links cannot bypass school boundaries, including bulk inserts."""
    label = instance._meta.label_lower
    if label == 'core.user' and instance.role == 'student' and instance.educational_level:
        from .education import YEAR_CHOICES
        from .school_models import School
        offered = School._base_manager.filter(pk=instance.school_id).values_list('educational_levels', flat=True).first() or []
        if instance.educational_level not in offered:
            raise ValidationError('Choose an educational level offered by your school.')
        if instance.year_level and instance.year_level not in dict(YEAR_CHOICES[instance.educational_level]):
            raise ValidationError('Choose a valid grade or year for your educational level.')
        if instance.educational_level != 'college' and (instance.department_id or instance.college):
            raise ValidationError('Basic-education students do not have a college or department assignment.')
    if label in {'faculty.consultationrequest', 'faculty.walkinqueue'} and instance._state.adding:
        faculty_model = instance._meta.get_field('faculty').remote_field.model
        assigned = faculty_model._base_manager.filter(pk=instance.faculty_id).values_list('user__department_id', flat=True).first()
        if instance.department_id is not None and instance.department_id != assigned:
            raise ValidationError('A new consultation or walk-in must use the faculty member\'s department.')
        instance.department_id = assigned
    if label == 'core.department':
        instance.clean()
        return
    department_id = getattr(instance, 'department_id', None)
    if department_id is None:
        return
    # Resolve persisted owners: callers may pass a related object with a forged
    # pk and cached school/role attributes without saving that object first.
    def persisted(field):
        model = instance._meta.get_field(field).remote_field.model
        return model._base_manager.get(pk=getattr(instance, field + '_id'))

    department = persisted('department')
    if label == 'core.departmentheadassignment':
        user = persisted('user')
        if user.role != 'depthead':
            raise ValidationError('Only head accounts can receive department management assignments.')
        owner_school = user.school_id
    elif label == 'core.departmentinviteassignment':
        owner_school = persisted('invite').school_id
    elif label in {'faculty.consultationrequest', 'faculty.walkinqueue'}:
        owner_school = persisted('faculty').user.school_id
    else:
        owner_school = getattr(instance, 'school_id', None)
    if owner_school != department.school_id:
        raise ValidationError('The department must belong to the record’s school.')
    if label == 'core.user' and instance.role not in {'faculty', 'student'}:
        raise ValidationError('Academic home departments are for faculty and students; heads use assignments.')
    if label in {'core.user', 'core.facultyinvite', 'core.departmentheadassignment', 'core.departmentinviteassignment'}:
        if not department.is_active:
            raise ValidationError('Choose an active department.')
