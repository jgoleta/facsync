from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class SchoolRequestMigrationTests(TransactionTestCase):
    def test_new_request_table_preserves_existing_school_and_user(self):
        executor=MigrationExecutor(connection)
        before=[('core','0031_classify_existing_students')]
        executor.migrate(before)
        old=executor.loader.project_state(before).apps
        school=old.get_model('core','School').objects.get(code='ADNU')
        user=old.get_model('core','User').objects.create(username='request-migration-user',role='superadmin',school_id=school.pk)
        try:
            executor=MigrationExecutor(connection)
            executor.migrate([('core','0032_school_registration_request')])
            new=executor.loader.project_state([('core','0032_school_registration_request')]).apps
            saved=new.get_model('core','User').objects.get(pk=user.pk)
            self.assertEqual((saved.username,saved.role,saved.school_id),('request-migration-user','superadmin',school.pk))
            self.assertEqual(new.get_model('core','SchoolRegistrationRequest').objects.count(),0)
            self.assertEqual(new.get_model('core','School').objects.get(pk=school.pk).name,school.name)
        finally:
            executor=MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
