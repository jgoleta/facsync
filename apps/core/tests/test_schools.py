from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from apps.core.models import College, School, SchoolChangeLog, SchoolDomain, User


class SchoolFoundationTests(TestCase):
    def setUp(self):
        # Reserved role: authentication/UI choices are added in the admin phase.
        self.actor = User.objects.create_user(username='school-operator', role='systemadmin')
        self.adnu = School.objects.get(code='ADNU')

    def other_school(self):
        school = School(code='OTHER', name='Other institution')
        school.save(actor=self.actor)
        return school

    def assign_domain(self, school, value):
        domain = SchoolDomain(school=school, domain=value)
        domain.save(actor=self.actor)
        return domain

    def test_adnu_is_created_without_domain_or_account_promotion(self):
        self.assertTrue(self.adnu.is_active)
        self.assertFalse(self.adnu.domains.exists())
        self.assertEqual(self.adnu.colleges.count(), 7)
        self.assertFalse(SchoolChangeLog.objects.exists())

    def test_only_schoolless_active_system_admin_can_edit(self):
        actors = [None, User.objects.create_user(username='head', role='depthead', school=self.adnu),
                  User.objects.create_user(username='super', role='superadmin', school=self.adnu),
                  User.objects.create_user(username='inactive', role='systemadmin', account_status='deactivated'),
                  User(pk=9999, username='scoped', role='systemadmin', school=self.adnu)]
        for actor in actors:
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                self.adnu.save(actor=actor)
            with self.subTest(domain_actor=actor), self.assertRaises(PermissionDenied):
                self.assign_domain_with_actor(actor)

    def assign_domain_with_actor(self, actor):
        SchoolDomain(school=self.adnu, domain='adnu.edu.ph').save(actor=actor)

    def test_name_and_suspension_edits_record_actor_time_old_and_new(self):
        self.adnu.name = 'Renamed ADNU'
        self.adnu.is_active = False
        self.adnu.save(actor=self.actor)
        logs = {row.field: row for row in self.adnu.changes.all()}
        self.assertEqual(logs['name'].old_value, 'Ateneo de Naga University')
        self.assertEqual(logs['name'].new_value, 'Renamed ADNU')
        self.assertEqual(logs['is_active'].old_value, True)
        self.assertEqual(logs['is_active'].new_value, False)
        self.assertEqual(logs['name'].actor, self.actor)
        self.assertIsNotNone(logs['name'].changed_at)
        self.actor.delete()
        logs['name'].refresh_from_db()
        self.assertIsNone(logs['name'].actor_id)
        self.assertEqual(logs['name'].actor_label, 'school-operator')

    def test_code_is_locked_and_queryset_edits_cannot_bypass_audit(self):
        self.adnu.code = 'RENAMED'
        with self.assertRaises(ValidationError):
            self.adnu.save(actor=self.actor)
        with self.assertRaises(PermissionDenied):
            School.objects.filter(pk=self.adnu.pk).update(code='RENAMED')
        with self.assertRaises(PermissionDenied):
            SchoolDomain.objects.bulk_create([SchoolDomain(school=self.adnu, domain='adnu.edu.ph')])
        self.adnu.refresh_from_db()
        self.assertEqual(self.adnu.code, 'ADNU')

    def test_domains_normalize_validate_and_are_unique_between_schools(self):
        domain = self.assign_domain(self.adnu, ' ADNU.EDU.PH ')
        self.assertEqual(domain.domain, 'adnu.edu.ph')
        log = self.adnu.changes.get(field='domains')
        self.assertEqual(log.old_value, [])
        self.assertEqual(log.new_value, ['adnu.edu.ph'])
        with self.assertRaises(ValidationError):
            self.assign_domain(self.other_school(), 'ADNU.edu.ph')
        for value in ['gmail.com','edu.ph','fake.edu.ph.evil.com','https://adnu.edu.ph','@adnu.edu.ph','*.adnu.edu.ph','bad_.edu.ph','-bad.edu.ph']:
            with self.subTest(domain=value), self.assertRaises(ValidationError):
                self.assign_domain(self.adnu, value)

    def test_domain_removal_and_rename_are_audited(self):
        domain = self.assign_domain(self.adnu, 'adnu.edu.ph')
        self.assign_domain(self.adnu, 'students.adnu.edu.ph')
        domain.domain = 'staff.adnu.edu.ph'
        domain.save(actor=self.actor)
        domain.delete(actor=self.actor)
        self.assertEqual(list(self.adnu.domains.values_list('domain', flat=True)), ['students.adnu.edu.ph'])
        with self.assertRaises(ValidationError):
            self.adnu.domains.get().delete(actor=self.actor)

    def test_schools_and_history_cannot_be_deleted_or_rewritten(self):
        other = self.other_school()
        with self.assertRaises(ProtectedError):
            other.delete()
        with self.assertRaises(ProtectedError):
            School.objects.filter(pk=other.pk).delete()
        log = other.changes.first()
        with self.assertRaises(ProtectedError):
            log.delete()
        log.new_value = 'tampered'
        with self.assertRaises(PermissionDenied):
            log.save()
        with self.assertRaises(PermissionDenied):
            SchoolChangeLog.objects.filter(pk=log.pk).update(new_value='tampered')

    def test_college_names_codes_and_generation_are_per_school(self):
        other = self.other_school()
        ccs = College.objects.get(school=self.adnu, code='CCS')
        College.objects.create(school=other, code=ccs.code, name=ccs.name)
        with self.assertRaises(IntegrityError), transaction.atomic():
            College.objects.create(school=other, code='ccs', name='Duplicate code')
        with self.assertRaises(IntegrityError), transaction.atomic():
            College.objects.create(school=other, code='OTHER', name=ccs.name.lower())
        generated = College.objects.create(school=other, name='College of Business and Accountancy')
        self.assertEqual(generated.code, 'CBA')
