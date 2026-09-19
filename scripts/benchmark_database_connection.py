"""SELECT-only connection benchmark; run via manage.py shell. No persisted settings changes."""
import json
from pathlib import Path
from statistics import median
from time import perf_counter
from django.db import connection, close_old_connections

cfg = connection.settings_dict
report = {'settings': {k: cfg.get(k) for k in ('ENGINE','HOST','PORT','CONN_MAX_AGE','CONN_HEALTH_CHECKS')}, 'pool_option_configured': bool(cfg.get('OPTIONS', {}).get('pool')), 'rounds': []}
original_age = cfg['CONN_MAX_AGE']
def execute_only(raw=False):
    # Cursor creation is outside the timer; connection is already established.
    with (connection.connection.cursor() if raw else connection.cursor()) as cursor:
        start = perf_counter()
        cursor.execute('SELECT 1')
        elapsed = (perf_counter() - start) * 1000
        assert cursor.fetchone() == (1,)
    return elapsed
try:
    for age in (0,60,0,60):
        connection.close()
        cfg['CONN_MAX_AGE'] = age
        rows=[]
        for request in range(5):
            close_old_connections()
            reused=connection.connection is not None
            start=perf_counter()
            connection.ensure_connection()
            connect_ms=(perf_counter()-start)*1000
            # Alternating wrappers controls for short-term network drift.
            timings=[execute_only(raw=(i%2==1)) for i in range(6)]
            rows.append({'request':request+1,'reused':reused,'connect_ms':round(connect_ms,3),'django_execute_ms':[round(x,3) for x in timings[::2]],'driver_execute_ms':[round(x,3) for x in timings[1::2]]})
            close_old_connections()
        report['rounds'].append({'conn_max_age':age,'requests':rows})
        print('Completed CONN_MAX_AGE',age,'connection median',round(median(r['connect_ms'] for r in rows),3),'SELECT median',round(median(x for r in rows for x in r['django_execute_ms']),3),flush=True)
finally:
    connection.close()
    cfg['CONN_MAX_AGE']=original_age
Path('docs/database-connection-benchmark.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report['settings']),flush=True)
