"""Restore a staging backup, migrate and reverse using local in-memory SQLite."""
import json
import hashlib
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.test'

import django
django.setup()

from django.core import serializers
from django.core.serializers.python import Deserializer
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor


def export(apps):
    tables = set(connection.introspection.table_names())
    models = sorted([
        model for model in apps.get_models()
        if not model._meta.proxy and model._meta.managed and model._meta.db_table in tables
    ], key=lambda model: model._meta.label)
    records = (obj for model in models for obj in model._base_manager.order_by('pk').iterator())
    return json.loads(serializers.serialize('json', records))


def main():
    if connection.vendor != 'sqlite' or connection.settings_dict['NAME'] != ':memory:':
        raise RuntimeError('Rehearsal requires isolated in-memory SQLite.')
    folder = ROOT / '.staging-backups' / 'before-school-v1'
    metadata = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    fixture = folder / 'data-physical.json'
    if hashlib.sha256(fixture.read_bytes()).hexdigest() != metadata['physical_fixture']['sha256']:
        raise RuntimeError('Backup checksum failed.')
    records = json.loads(fixture.read_text(encoding='utf-8'))
    executor = MigrationExecutor(connection)
    old_nodes = {tuple(node) for node in metadata['applied_migrations']}
    old_leaves = sorted(node for node in old_nodes if not any(
        child.key in old_nodes for child in executor.loader.graph.node_map[node].children
    ))
    executor.migrate(old_leaves)
    old = executor.loader.project_state(old_leaves).apps
    with transaction.atomic(), connection.constraint_checks_disabled(), patch.object(
        Deserializer, '_get_model_from_node', staticmethod(old.get_model),
    ):
        for obj in Deserializer(records):
            obj.save()
    connection.check_constraints()
    if export(old) != records:
        raise RuntimeError('Restored backup differs from original IDs/data.')
    print(f'PASS: restored all {len(records)} backup objects with original IDs into throwaway SQLite.')

    executor = MigrationExecutor(connection)
    new_leaves = executor.loader.graph.leaf_nodes()
    executor.migrate(new_leaves)
    new = executor.loader.project_state(new_leaves).apps
    adnu = new.get_model('core', 'School').objects.get(code='ADNU')
    users = new.get_model('core', 'User').objects
    if users.exclude(role='systemadmin').exclude(school_id=adnu.pk).exists():
        raise RuntimeError('Backfill left existing school users unattached.')
    if new.get_model('core', 'SchoolDomain').objects.exists():
        raise RuntimeError('Migration unexpectedly assigned a domain.')
    from apps.core.management.commands.seed_demo_data import fingerprint
    from apps.core.management.commands.seed_staging_data import MODELS, KEY
    manifest = new.get_model('core', 'DemoDataBatch').objects.get(key=KEY).manifest
    for current_model in MODELS:
        model = new.get_model(current_model._meta.label)
        for obj in model.objects.filter(pk__in=manifest[model._meta.label]):
            if fingerprint(obj) != manifest[model._meta.label][str(obj.pk)]:
                raise RuntimeError('Owned sample manifest changed unexpectedly.')
    print('PASS: existing users attached; domains unassigned; owned sample manifest valid.')

    executor = MigrationExecutor(connection)
    executor.migrate(old_leaves)
    reverted = executor.loader.project_state(old_leaves).apps
    if export(reverted) != records:
        raise RuntimeError('Rollback did not reproduce the original backup exactly.')
    print('PASS: rollback reproduces all original backup objects and ownership fingerprints exactly.')


if __name__ == '__main__':
    try:
        main()
    finally:
        connection.close()
