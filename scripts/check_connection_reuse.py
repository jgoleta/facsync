import importlib
import json
from django.db import connection, close_old_connections
from django.conf import settings
from time import perf_counter
assert connection.settings_dict['CONN_MAX_AGE'] == 60
assert connection.settings_dict['CONN_HEALTH_CHECKS'] is True
connection.ensure_connection()
first = connection.connection
close_old_connections()
with connection.cursor() as cursor:
    cursor.execute('SELECT 1')
    assert cursor.fetchone() == (1,)
assert connection.connection is first
# Simulate a dropped idle driver connection before the next request.
first.close()
close_old_connections()
with connection.cursor() as cursor:
    cursor.execute('SELECT 1')
    assert cursor.fetchone() == (1,)
assert connection.connection is not first
# Simulate the age deadline passing, without waiting a minute.
connection.close_at = perf_counter() - 1
close_old_connections()
assert connection.connection is None
base = importlib.import_module('config.settings.base')
assert 'CONN_MAX_AGE' not in base.DATABASES['default']
print(json.dumps({'settings':settings.SETTINGS_MODULE,'reuse':True,'dropped_connection_recovered':True,'expired_connection_closed':True,'base_unchanged':True}))
connection.close()
