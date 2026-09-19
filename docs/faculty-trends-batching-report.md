# Faculty Trends batching verification

## Live SQL profiling

Same profiling script, CCS account with three active faculty, two requests per page. Original baseline retained.

| Run | Before queries | Before SQL ms | After queries | After SQL ms | After similar / duplicate queries |
|---|---:|---:|---:|---:|---:|
| 1 | 26 | 3611.665 | 8 | 1005.583 | 0 / 0 |
| 2 | 26 | 3476.181 | 8 | 966.755 | 0 / 0 |

SQL timing includes network variability and uses different measurement times; the query-count reduction is deterministic. Connection reuse/health checks are now enabled. These are toolbar SQLPanel counts, not a browser waterfall. As in the baseline, authentication uses an in-memory session; the normal database session lookup is excluded.

## Fixed-clock parity and scaling

- Frozen old implementation retained as a test-only oracle.
- 3 faculty: four service queries, nine full-page queries including database session lookup.
- 15 faculty: the same four service queries and nine full-page queries.
- Compared complete service payloads and page contexts (trends, chart bars, schedule availability, consultation dates). All matched.
- Covered missing history, carry-in only, partial observation, changes exactly at window boundaries, future updates, non-available status values, no consultations, negative/zero/positive approval durations, missing approvals, outside-period consultations, inactive faculty, other-college faculty, empty roster, and past/future reporting periods.

## Tests

- Focused analytics, schedule and batching tests: 41 passed.
- Full baseline before batching: 173 tests, 21 failures and 3 errors.
- Full suite after batching: 175 tests, same 21 failures and 3 errors. Exact failure/error test identifiers matched.

## Scope

Faculty Trends now batches consultation counts, approval timestamps and status history; carry-in status and latest update are SQL subqueries on the roster query. The existing timeline integration was extracted into a query-free helper without changing its arithmetic. Shared aggregator query behavior is unchanged: Overview, Peak Analytics and Student Behavior still measured 37 queries each. No displayed calculation or template was changed.
