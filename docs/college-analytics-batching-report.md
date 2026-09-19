# Shared college analytics batching verification

## Live measurements

Read-only SQL profiling against the existing CCS account with three active faculty, using the same script and two sequential requests per page. Before is the immediately preceding Faculty Trends-batched profile; both profiles use the connection reuse configuration. Original reports are retained.

| Page | Run | Before queries | After queries | Before SQL ms | After SQL ms | SQL reduction |
|---|---:|---:|---:|---:|---:|---:|
| Overview | 1 | 37 | 9 | 4132.552 | 1293.960 | 68.7% |
| Overview | 2 | 37 | 9 | 4199.146 | 1426.069 | 66.0% |
| Peak Analytics | 1 | 37 | 9 | 4104.693 | 1314.901 | 68.0% |
| Peak Analytics | 2 | 37 | 9 | 4346.170 | 2011.302 | 53.7% |
| Student Behavior | 1 | 37 | 9 | 4055.920 | 1497.751 | 63.1% |
| Student Behavior | 2 | 37 | 9 | 5397.844 | 999.484 | 81.5% |

The 76% query-count reduction is deterministic. SQL timing includes variable network round trips; measurements are separate runs, not isolated server execution times. The profiler excludes session loading, static assets and asynchronous requests (including Gemini). Django test-client page tests include the database session lookup and therefore count ten queries instead of nine.

## Implementation

- Seven aggregator queries: current scheduled-date consultation fields, previous-period conditional counts, submission timestamps, active roster with carry-in status subquery, in-window history, walk-in fields, college metadata.
- Current consultation rows are loaded once with only calculation fields; reducers reuse that period-bounded snapshot.
- Submission-date populations stay separate from scheduled-date populations. Previous-period counts use one conditional aggregate.
- Current availability reuses the historical roster; historical integration retains the existing pure calculation helper.
- Public helper names and original call signatures remain callable by the analytics browser. Optional keyword inputs enable reuse inside the aggregator.
- No payload schema, rounding, denominator, display template or Gemini logic changes. Memory usage scales with the selected period's rows; no all-time consultation or history fetch was introduced.

## Verification

- Frozen oracle: the complete pre-change analytics module, including helpers, is kept in tests/legacy_college_analytics.py.
- 3 and 15 faculty: seven aggregator queries, ten full-page queries (nine excluding session lookup) for each of Overview, Peak Analytics and Student Behavior.
- Entire payload equality and rendered HTML equality passed at a fixed clock at both roster sizes.
- Covered missing/carry-in/partial history, exact time boundaries, future history, missing approval/start/end timestamps, negative and zero durations, past/current/future/six-month periods, three timezones, submission-versus-scheduled population differences, empty and nonempty comparison periods, tied peaks, mixed statuses/agendas, inactive and other-college faculty, walk-in missing/negative/out-of-order timestamps, confidence dimensions and warning order.
- All 12 analytics-browser endpoint answers matched the frozen public-helper results with 15 faculty and populated edge-case data. Existing access-control, no-AI, repeated-fetch and Overview-only tests still pass.
- Live PostgreSQL fixed-clock comparisons: complete month-to-date and six-month payloads both matched exactly.
- All three JavaScript browser interaction tests pass (repeat/out-of-order replies, errors, Escape/focus/reset).
- Full baseline: 175 tests, 21 failures and 3 errors. Final: 178 tests, identical 21 failure and 3 error test identifiers; no new failing tests.
- Faculty Trends remains at eight profiler queries; its existing parity/scaling tests still pass.

## Files

- docs/college-head-query-profile-code-batched-faculty.json: before measurements
- docs/college-head-query-profile-code-batched-aggregator.json: after measurements
- apps/depthead/tests/test_college_analytics_batching.py: oracle, scaling, page and endpoint tests
