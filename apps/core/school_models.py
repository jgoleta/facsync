"""School identity and audited edits restricted to System Admins."""
import re

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import RegexValidator
from django.db import models, router, transaction
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Lower


def validate_school_domain(value):
    pattern = r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+edu\.ph'
    if len(value) > 253 or not re.fullmatch(pattern, value):
        raise ValidationError('Enter an institutional domain ending in .edu.ph, without @, a URL or a wildcard.')


def require_system_admin(actor):
    if (actor is None or not actor.pk or actor.role != 'systemadmin'
            or actor.school_id is not None or not actor.is_active
            or actor.account_status != 'active'):
        raise PermissionDenied('Only a schoolless System Admin can manage schools and domains.')


class ManagedSchoolQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionDenied('Use an audited school/domain save with a System Admin actor.')

    def bulk_create(self, *args, **kwargs):
        raise PermissionDenied('Use an audited school/domain save with a System Admin actor.')

    def bulk_update(self, *args, **kwargs):
        raise PermissionDenied('Use an audited school/domain save with a System Admin actor.')

    def delete(self):
        raise ProtectedError('Schools are suspended, never deleted; domain removal requires an actor.', [])


class School(models.Model):
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=20, unique=True, validators=[
        RegexValidator(r'^[A-Z][A-Z0-9_-]{1,19}$', 'Use a 2–20 character school code starting with a letter.'),
    ])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = ManagedSchoolQuerySet.as_manager()

    class Meta:
        ordering = ['name']
        constraints = [models.UniqueConstraint(Lower('code'), name='school_code_ci_unique')]

    def __str__(self):
        return self.name

    def save(self, *args, actor=None, **kwargs):
        require_system_admin(actor)
        alias = kwargs.get('using') or router.db_for_write(type(self), instance=self)
        self.code = self.code.strip().upper()
        self.name = self.name.strip()
        with transaction.atomic(using=alias):
            old = type(self).objects.using(alias).select_for_update().filter(pk=self.pk).first() if self.pk else None
            if old and old.code != self.code:
                raise ValidationError({'code': 'A school code is locked after creation.'})
            self.full_clean()
            super().save(*args, **kwargs)
            fields = kwargs.get('update_fields')
            for field in ('name', 'is_active'):
                if fields is not None and field not in fields:
                    continue
                previous = getattr(old, field) if old else None
                if previous != getattr(self, field):
                    SchoolChangeLog.objects.using(alias).create(
                        school=self, actor=actor, actor_label=actor.username,
                        field=field, old_value=previous, new_value=getattr(self, field),
                    )

    def delete(self, *args, **kwargs):
        raise ProtectedError('Schools are suspended, never deleted.', [self])


class SchoolDomain(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name='domains')
    domain = models.CharField(max_length=253, validators=[validate_school_domain])
    created_at = models.DateTimeField(auto_now_add=True)
    objects = ManagedSchoolQuerySet.as_manager()

    class Meta:
        ordering = ['domain']
        constraints = [
            models.UniqueConstraint(Lower('domain'), name='school_domain_ci_unique'),
            models.CheckConstraint(condition=models.Q(domain=Lower('domain')), name='school_domain_lowercase'),
            models.CheckConstraint(condition=models.Q(domain__endswith='.edu.ph'), name='school_domain_edu_ph'),
        ]

    def __str__(self):
        return self.domain

    def _domain_list(self, alias):
        return list(type(self).objects.using(alias).filter(school_id=self.school_id).order_by('domain').values_list('domain', flat=True))

    def save(self, *args, actor=None, **kwargs):
        require_system_admin(actor)
        alias = kwargs.get('using') or router.db_for_write(type(self), instance=self)
        self.domain = self.domain.strip().lower()
        with transaction.atomic(using=alias):
            School.objects.using(alias).select_for_update().get(pk=self.school_id)
            old = type(self).objects.using(alias).filter(pk=self.pk).first() if self.pk else None
            if old and old.school_id != self.school_id:
                raise ValidationError('A domain cannot be moved to another school. Remove it and assign it explicitly.')
            before = self._domain_list(alias)
            self.full_clean()
            super().save(*args, **kwargs)
            self._log_change(actor, alias, before)

    def _log_change(self, actor, alias, before):
        after = self._domain_list(alias)
        if before != after:
            SchoolChangeLog.objects.using(alias).create(
                school_id=self.school_id, actor=actor, actor_label=actor.username,
                field='domains', old_value=before, new_value=after,
            )

    def delete(self, *args, actor=None, **kwargs):
        require_system_admin(actor)
        alias = kwargs.get('using') or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=alias):
            School.objects.using(alias).select_for_update().get(pk=self.school_id)
            before = self._domain_list(alias)
            if len(before) <= 1:
                raise ValidationError('An institution must retain at least one assigned domain. Replace the last domain instead.')
            result = super().delete(*args, **kwargs)
            self._log_change(actor, alias, before)
            return result


class ImmutableLogQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionDenied('School history cannot be edited.')

    def bulk_update(self, *args, **kwargs):
        raise PermissionDenied('School history cannot be edited.')

    def delete(self):
        raise ProtectedError('School history cannot be deleted.', [])


class SchoolChangeLog(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name='changes')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='school_changes')
    actor_label = models.CharField(max_length=150)
    changed_at = models.DateTimeField(auto_now_add=True)
    field = models.CharField(max_length=16, choices=[('name', 'Name'), ('domains', 'Domains'), ('is_active', 'Active')])
    old_value = models.JSONField(null=True)
    new_value = models.JSONField(null=True)
    objects = ImmutableLogQuerySet.as_manager()

    class Meta:
        ordering = ['-changed_at', '-pk']

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionDenied('School history cannot be edited.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ProtectedError('School history cannot be deleted.', [self])
