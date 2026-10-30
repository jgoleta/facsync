"""Offline checks: no credentials are read and no database is contacted."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

SCRIPT = Path(__file__).resolve().parents[1] / 'preflight_production.py'
spec = importlib.util.spec_from_file_location('production_preflight', SCRIPT)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class ProductionPreflightTests(unittest.TestCase):
    def configs(self):
        return [
            {'DB_NAME': 'postgres', 'DB_USER': 'postgres.prodref', 'DB_PASSWORD': 'dummy',
             'DB_HOST': 'aws-0-region.pooler.supabase.com', 'DB_PORT': '5432'},
            {'STAGING_DB_HOST': 'db.stageref.supabase.co', 'STAGING_DB_USER': 'postgres'},
            {'REHEARSAL_DB_HOST': 'db.copyref.supabase.co', 'REHEARSAL_DB_USER': 'postgres'},
        ]

    def test_direct_and_pooler_project_identity(self):
        self.assertEqual(preflight.project_reference('db.prodref.supabase.co', 'postgres'), 'prodref')
        self.assertEqual(preflight.project_reference('aws-0-region.pooler.supabase.com', 'postgres.prodref'), 'prodref')
        self.assertIsNone(preflight.project_reference('localhost', 'postgres'))

    def test_configuration_uses_explicit_files_and_requires_ssl(self):
        with patch.object(preflight, 'dotenv_values', side_effect=self.configs()):
            reference, config = preflight.configuration()
        self.assertEqual(reference, 'prodref')
        self.assertEqual(config['sslmode'], 'require')
        self.assertEqual(config['port'], 5432)

    def test_rejects_staging_and_rehearsal_targets(self):
        for other in ('stageref', 'copyref'):
            with self.subTest(other=other):
                configs = self.configs()
                configs[0]['DB_USER'] = 'postgres.' + other
                with patch.object(preflight, 'dotenv_values', side_effect=configs):
                    with self.assertRaises(preflight.Refused):
                        preflight.configuration()

    def test_rejects_transaction_pooler_port(self):
        configs = self.configs()
        configs[0]['DB_PORT'] = '6543'
        with patch.object(preflight, 'dotenv_values', side_effect=configs):
            with self.assertRaises(preflight.Refused):
                preflight.configuration()

    def test_preview_does_not_connect_or_build_graph(self):
        with patch.object(preflight, 'configuration', return_value=('prodref', {})), patch.object(
            preflight.sys, 'argv', ['preflight_production.py']
        ), patch.object(preflight, 'run_check') as run, patch.object(preflight, 'migration_graph') as graph, patch('builtins.print'):
            self.assertEqual(preflight.main(), 0)
        run.assert_not_called()
        graph.assert_not_called()

    def test_wrong_confirmation_refuses_before_connection(self):
        with patch.object(preflight, 'configuration', return_value=('prodref', {})), patch.object(
            preflight.sys, 'argv', ['preflight_production.py', '--project-ref', 'copyref']
        ), patch.object(preflight, 'run_check') as run:
            with self.assertRaises(preflight.Refused):
                preflight.main()
        run.assert_not_called()

    def test_session_is_read_only_and_always_rolls_back(self):
        for failure in (False, True):
            with self.subTest(failure=failure):
                connection = MagicMock()
                connect = MagicMock(return_value=connection)
                effect = preflight.Refused('test refusal') if failure else {'ready_for_migration_review': True}
                with patch.object(preflight, 'inspect_database', side_effect=[effect]):
                    if failure:
                        with self.assertRaises(preflight.Refused):
                            preflight.run_check({}, None, 'operator@example.invalid', connect=connect)
                    else:
                        preflight.run_check({}, None, 'operator@example.invalid', connect=connect)
                connection.set_session.assert_called_once_with(readonly=True, isolation_level='REPEATABLE READ', autocommit=False)
                connection.rollback.assert_called_once()
                connection.close.assert_called_once()
                connection.commit.assert_not_called()

    def test_refuses_if_read_only_not_enforced(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = ('off',)
        with self.assertRaises(preflight.Refused):
            preflight.inspect_database(cursor, None, 'operator@example.invalid')
        cursor.execute.assert_called_once_with('SHOW transaction_read_only')

    def test_pending_migration_allowlist_and_inconsistent_history(self):
        old = ('core', '0019_demodatabatch')
        plan = [old, *sorted(preflight.EXPECTED)]
        graph = SimpleNamespace(nodes=dict.fromkeys(plan),
                                node_map={old: SimpleNamespace(parents=[])},
                                leaf_nodes=lambda: [plan[-1]], forwards_plan=lambda leaf: plan)
        self.assertEqual(set(preflight.pending_migrations(graph, {old})), {'.'.join(x) for x in preflight.EXPECTED})
        graph.forwards_plan = lambda leaf: plan + [('core', '9999_unreviewed')]
        with self.assertRaises(preflight.Refused):
            preflight.pending_migrations(graph, {old})
        graph.node_map[old].parents = [SimpleNamespace(key=('core', 'missing'))]
        with self.assertRaises(preflight.Refused):
            preflight.pending_migrations(graph, {old})

    def test_data_report_detects_orphan_and_missing_replacement_without_personal_details(self):
        tables = {'django_migrations', 'core_college', *(table for table, _ in preflight.REFERENCES)}
        business_tables = [table for table in tables if table.startswith(('core_', 'faculty_', 'students_', 'depthead_'))]
        email = 'private-operator@example.invalid'
        for orphan, replacements in ((0, 1), (1, 1), (0, 0)):
            with self.subTest(orphan=orphan, replacements=replacements):
                cursor = MagicMock()
                cursor.fetchone.side_effect = [('on',), ('postgres',), *[(1,)] * len(business_tables), (orphan,), (replacements,)]
                references = [[('CCS2' if orphan and table == 'depthead_collegeaiinsight' else 'CCS',)]
                              for table, _ in preflight.REFERENCES]
                cursor.fetchall.side_effect = [
                    [(table,) for table in tables], [], [('CCS', 'Computing')],
                    *references, [('CCS', 'CCS')], [('superadmin', 2)],
                    [(1, 'superadmin', True, 'active')],
                ]
                with patch.object(preflight, 'pending_migrations', return_value=['reviewed']):
                    report = preflight.inspect_database(cursor, None, email)
                self.assertEqual(report['ready_for_migration_review'], not orphan and bool(replacements))
                self.assertEqual(report['ccs2_insight_rows'], orphan)
                self.assertEqual(report['other_active_superadmins'], replacements)
                self.assertNotIn(email, preflight.json.dumps(report))

    def test_real_migration_graph_does_not_open_a_database(self):
        with patch.object(preflight.psycopg2, 'connect', side_effect=AssertionError('No PostgreSQL permitted')), patch(
            'django.db.backends.sqlite3.base.DatabaseWrapper.get_new_connection',
            side_effect=AssertionError('Graph loading must not open SQLite either'),
        ):
            graph = preflight.migration_graph()
        self.assertTrue(preflight.EXPECTED.issubset(graph.nodes))


if __name__ == '__main__':
    unittest.main()
