"""Request-local tenant boundaries, shared by ORM queries and service entry points.

Outside a request, maintenance commands may query globally. Data services require
an explicit school (or an existing scope); HTTP requests never use maintenance
mode for an authenticated school account. ContextVar state is reset on exit.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps

from django.contrib.auth.models import UserManager
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models

ALL_SCHOOLS = object()
_scope = ContextVar('facsync_school_scope', default=None)

PATHS = {
    'core.user': ('school_id',), 'core.college': ('school_id',),
    'core.facultyinvite': ('school_id',), 'core.deptheadinvite': ('school_id',),
    'core.superadmininvite': ('school_id',),
    'core.officeclosure': ('school_id',), 'core.collegeannouncement': ('school_id',),
    'core.notification': ('recipient__school_id',), 'core.demodatabatch': ('college__school_id',),
    'faculty.facultyprofile': ('user__school_id',),
    'faculty.googlecalendarconnection': ('user__school_id',),
    'faculty.statushistory': ('faculty__user__school_id',),
    'faculty.scheduleevent': ('faculty__user__school_id',),
    'faculty.consultationrequest': ('user__school_id', 'faculty__user__school_id'),
    'faculty.walkinqueue': ('user__school_id', 'faculty__user__school_id'),
    'faculty.statusemaildelivery': ('recipient__school_id', 'history__faculty__user__school_id'),
    'students.facultystatussubscription': ('student__school_id', 'faculty__user__school_id'),
    'depthead.collegeaiinsight': ('school_id',),
}


def current_school():
    return _scope.get()


@contextmanager
def school_scope(school):
    token = _scope.set(school)
    try:
        yield
    finally:
        _scope.reset(token)


def require_school(school=None):
    active = current_school()
    chosen = school if school is not None else active
    if chosen is None or chosen is ALL_SCHOOLS or not chosen.pk or not chosen.is_active:
        raise PermissionDenied('An active school scope is required.')
    if active is not None and active is not ALL_SCHOOLS and active.pk != chosen.pk:
        raise PermissionDenied('A request cannot change schools.')
    return chosen


def school_service(function):
    @wraps(function)
    def scoped(*args, school=None, **kwargs):
        with school_scope(require_school(school)):
            return function(*args, **kwargs)
    return scoped


def model_paths(model):
    return PATHS.get(model._meta.concrete_model._meta.label_lower, ())


def related_school(instance, path):
    value = instance
    for part in path.split('__'):
        value = getattr(value, part)
        if value is None:
            return None
    return value


def prepare_school_write(instance):
    scope = current_school()
    paths = model_paths(type(instance))
    direct = 'school_id' in paths
    if instance._meta.label_lower == 'core.superadmininvite':
        from .school_models import require_system_admin
        require_system_admin(instance.invited_by)
        if scope is not None and scope is not ALL_SCHOOLS:
            raise PermissionDenied('Only a System Admin can manage Super Admin invitations.')
    if direct and scope is not None and scope is not ALL_SCHOOLS and instance.school_id is None:
        instance.school_id = scope.pk
    if instance._meta.label_lower == 'core.user' and instance.role == 'systemadmin':
        if instance.school_id is not None or (scope is not None and scope is not ALL_SCHOOLS):
            raise PermissionDenied('System Admin accounts cannot belong to a school or be created by school accounts.')
    schools = [related_school(instance, path) for path in paths]
    # Prevent mixed-participant records even in maintenance/background operations.
    assigned = {value for value in schools if value is not None}
    if len(assigned) > 1 or (assigned and any(value is None for value in schools)):
        raise ValidationError('Related records must belong to the same school.')
    if scope is not None and scope is not ALL_SCHOOLS and paths:
        if any(value != scope.pk for value in schools):
            raise PermissionDenied('This record does not belong to your school.')
    if direct and instance.school_id:
        for field in ('invited_by', 'posted_by', 'updated_by'):
            if hasattr(instance, field + '_id') and getattr(instance, field + '_id'):
                owner = getattr(instance, field)
                if instance._meta.label_lower == 'core.superadmininvite' and field == 'invited_by':
                    continue
                if owner.school_id != instance.school_id:
                    raise ValidationError('The sender/author must belong to the assigned school.')


class SchoolQuerySet(models.QuerySet):
    def bulk_create(self, objs, **kwargs):
        objs = list(objs)
        for obj in objs:
            prepare_school_write(obj)
        return super().bulk_create(objs, **kwargs)

    def update(self, **kwargs):
        if current_school() is not None and current_school() is not ALL_SCHOOLS:
            ownership = {'school', 'school_id', 'user', 'user_id', 'faculty', 'faculty_id',
                         'student', 'student_id', 'recipient', 'recipient_id', 'history', 'history_id',
                         'invited_by', 'invited_by_id', 'posted_by', 'posted_by_id', 'updated_by', 'updated_by_id'}
            if ownership.intersection(kwargs):
                raise PermissionDenied('Ownership changes require a validated model save.')
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        objs = list(objs)
        for obj in objs:
            prepare_school_write(obj)
        return super().bulk_update(objs, fields, **kwargs)


class SchoolManagerMixin:
    def get_queryset(self):
        queryset = super().get_queryset()
        scope = current_school()
        if scope is not None and scope is not ALL_SCHOOLS:
            queryset = queryset.filter(**{path: scope.pk for path in model_paths(self.model)})
        return queryset


class SchoolManager(SchoolManagerMixin, models.Manager.from_queryset(SchoolQuerySet)):
    pass


class SchoolUserManager(SchoolManagerMixin, UserManager.from_queryset(SchoolQuerySet)):
    def get(self, *args, **kwargs):
        # Django's session backend resolves identity by pk before tenant scope
        # exists. Join its school once so the access check needs no extra query.
        if current_school() is None and ('pk' in kwargs or 'id' in kwargs):
            return self.get_queryset().select_related('school').get(*args, **kwargs)
        return super().get(*args, **kwargs)


class SchoolScopedModel(models.Model):
    objects = SchoolManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        scope = current_school()
        paths = model_paths(type(self))
        if scope is not None and scope is not ALL_SCHOOLS and self.pk is not None and paths:
            # Model.save() uses Django's unscoped base manager internally. Check
            # the persisted owner too, so forging a pk plus a new school/parent
            # cannot turn an otherwise valid object into a cross-school UPDATE.
            prior = type(self)._base_manager.filter(pk=self.pk).values_list(*paths).first()
            if prior is not None and any(value != scope.pk for value in prior):
                raise PermissionDenied('The existing record belongs to another school.')
        before = getattr(self, 'school_id', None)
        prepare_school_write(self)
        if before is None and getattr(self, 'school_id', None) is not None and kwargs.get('update_fields') is not None:
            kwargs['update_fields'] = set(kwargs['update_fields']) | {'school'}
        return super().save(*args, **kwargs)
