# Isolated database connection benchmark

No project configuration or database records changed. CONN_MAX_AGE was changed only in the shell process and restored in finally.

## Effective settings

PostgreSQL via aws-1-ap-south-1.pooler.supabase.com:5432; AWS Mumbai (ap-south-1), Supabase shared session pooler. CONN_MAX_AGE=0, CONN_HEALTH_CHECKS=False, no Django OPTIONS pool configured. Credentials omitted.

## Method

Executed through manage.py shell. Four alternating rounds: 0, 60, 0, 60. Each round starts closed, simulates five request boundaries using close_old_connections, and executes six SELECT 1 calls per request. Three calls use Django cursor, three use the native driver cursor, interleaved. 120 SELECT executions total. No toolbar instrumentation or HTTP middleware runs.

Connection timing surrounds ensure_connection and includes network/authentication and Django connection initialization. Execute timing surrounds only cursor.execute after connection and cursor creation; fetch/assert follows outside timer. Boundary simulation is same-thread: it demonstrates reusable-worker behavior, not default threaded runserver behavior.

| CONN_MAX_AGE | Connections opened / boundaries | Django SELECT median (range), ms | Driver SELECT median (range), ms | Connect + first query median, ms |
|---|---|---|---|---|
| 0 | 10 / 10 | 106.649 (99.602-242.881) | 103.911 (99.210-208.290) | 886.416 |
| 60 | 2 / 10 | 100.044 (96.521-110.620) | 99.789 (96.489-427.170) | 101.373 |

New connection setup at age 0: 646.085-1020.432 ms. Reused connection checks at age 60 were near zero. The first request of each age-60 round still opened a connection (~660-664 ms).

## Interpretation

- Remote-query round-trip latency persists with a native driver and established connection. This is not primarily per-query middleware overhead.
- The experiment cannot separate network transit from Supabase pooler/backend scheduling; do not call the entire duration pure network latency.
- Small differences in SELECT medians and occasional spikes are time-varying latency, not evidence that CONN_MAX_AGE makes individual queries execute faster.
- Positive CONN_MAX_AGE can avoid connection establishment on subsequent same-worker/thread requests. It cannot remove the latency paid by each of 26-37 SQL calls.
- Installed Django ThreadedWSGIServer closes all thread connections on close_request; default threaded runserver therefore limits this benefit. No server configuration was changed.

## Sources

- https://docs.aws.amazon.com/global-infrastructure/latest/regions/aws-regions.html
- https://supabase.com/docs/guides/database/connecting-to-postgres
- https://docs.djangoproject.com/en/dev/ref/databases/
