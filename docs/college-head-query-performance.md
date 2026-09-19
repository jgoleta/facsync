# College Head SQL profiling report

Measured 2026-09-18 using Django Debug Toolbar 8.0.0 SQLPanel against the configured PostgreSQL database. No analytics optimizations were made.

## Method and scope

- Actual authenticated Django client GET requests through development middleware and templates; toolbar injection verified for each response (HTTP 200).
- Existing testdepthead account: CED, zero active faculty. Supplemental existing code account: CCS, three active faculty. No accounts were created or modified.
- Authenticated session supplied in memory to avoid login/session database writes. The usual database session lookup is excluded; user lookup is included. These are measured page queries, not a browser waterfall.
- Two sequential requests per page. SQL times include database round trips; they are not PostgreSQL execution-plan timings. Toolbar instrumentation adds overhead. Connection/account setup precedes measured requests.
- JavaScript was not executed: Gemini insights, toolbar AJAX, static assets and interactive analytics fetches are excluded. No AI calls were made.
- Similar = identical parameterized SQL; duplicate = identical SQL and parameters. Counts include all queries in groups of at least two; repeats excludes the first query in each group. Similar and duplicate counts overlap.

## Findings

- CCS Faculty Trends: seven similar query groups, each executed three times (21 queries), matching seven per-faculty operations in get_faculty_trends. Zero exact duplicates does not rule out N+1.
- Overview, Peak Analytics and Student Behavior call the shared get_college_analytics aggregator, including two status-history queries per active faculty through get_historical_availability_proxy. Repeated consultation counts and date reads also occur.
- The measured SQL time largely accounts for the reported multi-second loading. A considerable fixed cost remains even for the empty CED roster. Network/server latency cannot be separated from SQL execution using these timings alone.

## CED / testdepthead (0 active faculty)

| Page | Run | SQL queries | SQL ms | Request wall ms | Duplicate queries / groups | Excess repeats | Similar queries / groups |
|---|---:|---:|---:|---:|---:|---:|---:|
| College Overview | 1 | 31 | 5083.748 | 8642.820 | 9 / 4 | 5 | 11 / 4 |
| College Overview | 2 | 31 | 4465.740 | 4801.720 | 9 / 4 | 5 | 11 / 4 |
| Peak Analytics | 1 | 30 | 3446.141 | 3823.716 | 7 / 3 | 4 | 9 / 3 |
| Peak Analytics | 2 | 30 | 4763.053 | 5145.914 | 7 / 3 | 4 | 9 / 3 |
| Faculty Trends | 1 | 3 | 363.189 | 450.540 | 0 / 0 | 0 | 0 / 0 |
| Faculty Trends | 2 | 3 | 517.637 | 634.112 | 0 / 0 | 0 | 0 / 0 |
| Student Behavior | 1 | 31 | 5112.857 | 5338.769 | 7 / 3 | 4 | 9 / 3 |
| Student Behavior | 2 | 31 | 4704.868 | 5027.457 | 7 / 3 | 4 | 9 / 3 |

### College Overview: five slowest SQL queries, run 2

SQL below retains parameter placeholders; parameter values and database results are not included.

1. **207.198 ms**

```sql
SELECT "core_user"."id", "core_user"."password", "core_user"."last_login", "core_user"."is_superuser", "core_user"."username", "core_user"."first_name", "core_user"."last_name", "core_user"."email", "core_user"."is_staff", "core_user"."is_active", "core_user"."date_joined", "core_user"."title", "core_user"."role", "core_user"."account_status", "core_user"."college", "core_user"."profile_completed", "core_user"."student_id", "core_user"."year_level" FROM "core_user" WHERE "core_user"."id" = %s LIMIT 21
```

2. **204.155 ms**

```sql
SELECT "faculty_consultationrequest"."requested_at" AS "requested_at", "faculty_consultationrequest"."approved_at" AS "approved_at" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s AND "faculty_consultationrequest"."approved_at" IS NOT NULL) ORDER BY "faculty_consultationrequest"."date" DESC
```

3. **203.381 ms**

```sql
SELECT "faculty_consultationrequest"."date" AS "date" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s AND "faculty_consultationrequest"."status" = %s) ORDER BY 1 DESC
```

4. **200.883 ms**

```sql
SELECT "faculty_walkinqueue"."queue_id", "faculty_walkinqueue"."joined_at", "faculty_walkinqueue"."served_at", "faculty_walkinqueue"."notified_at" FROM "faculty_walkinqueue" INNER JOIN "faculty_facultyprofile" ON ("faculty_walkinqueue"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_walkinqueue"."joined_at" >= %s AND "faculty_walkinqueue"."joined_at" < %s) ORDER BY "faculty_walkinqueue"."position" ASC, "faculty_walkinqueue"."joined_at" ASC
```

5. **198.844 ms**

```sql
SELECT "faculty_consultationrequest"."requested_at" AS "requested_at" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."requested_at" >= %s AND "faculty_consultationrequest"."requested_at" < %s) ORDER BY "faculty_consultationrequest"."date" DESC
```

Similar-query patterns:

Executed 4 times:
```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s)
```

Executed 3 times:
```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s AND "faculty_consultationrequest"."status" = %s)
```

Executed 2 times:
```sql
SELECT "core_college"."id", "core_college"."code", "core_college"."name", "core_college"."description", "core_college"."created_at" FROM "core_college" WHERE UPPER("core_college"."code"::text) = UPPER(%s) ORDER BY "core_college"."id" ASC LIMIT 1
```

Executed 2 times:
```sql
SELECT "faculty_consultationrequest"."date" AS "date" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s) ORDER BY 1 DESC
```

### Peak Analytics: five slowest SQL queries, run 2

SQL below retains parameter placeholders; parameter values and database results are not included.

1. **299.157 ms**

```sql
SELECT "faculty_consultationrequest"."date" AS "date" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s) ORDER BY 1 DESC
```

2. **206.559 ms**

```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s AND "faculty_consultationrequest"."start_time" IS NULL)
```

3. **201.918 ms**

```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s AND "faculty_consultationrequest"."status" = %s)
```

4. **200.076 ms**

```sql
SELECT COUNT(*) AS "__count" FROM "faculty_facultyprofile" INNER JOIN "core_user" ON ("faculty_facultyprofile"."user_id" = "core_user"."id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "core_user"."account_status" = %s AND "core_user"."role" = %s)
```

5. **199.652 ms**

```sql
SELECT "faculty_consultationrequest"."user_id" AS "user_id", COUNT("faculty_consultationrequest"."request_id") AS "request_count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s) GROUP BY 1
```

Similar-query patterns:

Executed 4 times:
```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s)
```

Executed 3 times:
```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s AND "faculty_consultationrequest"."status" = %s)
```

Executed 2 times:
```sql
SELECT "faculty_consultationrequest"."date" AS "date" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s) ORDER BY 1 DESC
```

### Faculty Trends: five slowest SQL queries, run 2

SQL below retains parameter placeholders; parameter values and database results are not included.

1. **218.686 ms**

```sql
SELECT "faculty_facultyprofile"."faculty_id", "faculty_facultyprofile"."user_id", "faculty_facultyprofile"."college_id", "faculty_facultyprofile"."office_location", "faculty_facultyprofile"."current_status", "faculty_facultyprofile"."status_note", "faculty_facultyprofile"."status_updated_at", "faculty_facultyprofile"."manual_status", "faculty_facultyprofile"."manual_status_override", "faculty_facultyprofile"."manual_status_expires_at", "faculty_facultyprofile"."sync_enabled", "faculty_facultyprofile"."walk_ins_enabled", "faculty_facultyprofile"."last_calendar_sync_at", "faculty_facultyprofile"."schedule_last_updated_at", "faculty_facultyprofile"."photo_url", "faculty_facultyprofile"."biography" FROM "faculty_facultyprofile" INNER JOIN "core_user" ON ("faculty_facultyprofile"."user_id" = "core_user"."id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "core_user"."account_status" = %s AND "core_user"."role" = %s) ORDER BY "faculty_facultyprofile"."faculty_id" ASC
```

2. **197.135 ms**

```sql
SELECT "faculty_facultyprofile"."faculty_id", "faculty_facultyprofile"."user_id", "faculty_facultyprofile"."college_id", "faculty_facultyprofile"."office_location", "faculty_facultyprofile"."current_status", "faculty_facultyprofile"."status_note", "faculty_facultyprofile"."status_updated_at", "faculty_facultyprofile"."manual_status", "faculty_facultyprofile"."manual_status_override", "faculty_facultyprofile"."manual_status_expires_at", "faculty_facultyprofile"."sync_enabled", "faculty_facultyprofile"."walk_ins_enabled", "faculty_facultyprofile"."last_calendar_sync_at", "faculty_facultyprofile"."schedule_last_updated_at", "faculty_facultyprofile"."photo_url", "faculty_facultyprofile"."biography", "core_user"."id", "core_user"."password", "core_user"."last_login", "core_user"."is_superuser", "core_user"."username", "core_user"."first_name", "core_user"."last_name", "core_user"."email", "core_user"."is_staff", "core_user"."is_active", "core_user"."date_joined", "core_user"."title", "core_user"."role", "core_user"."account_status", "core_user"."college", "core_user"."profile_completed", "core_user"."student_id", "core_user"."year_level" FROM "faculty_facultyprofile" INNER JOIN "core_user" ON ("faculty_facultyprofile"."user_id" = "core_user"."id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "core_user"."account_status" = %s AND "core_user"."role" = %s) ORDER BY "faculty_facultyprofile"."faculty_id" ASC
```

3. **101.817 ms**

```sql
SELECT "core_user"."id", "core_user"."password", "core_user"."last_login", "core_user"."is_superuser", "core_user"."username", "core_user"."first_name", "core_user"."last_name", "core_user"."email", "core_user"."is_staff", "core_user"."is_active", "core_user"."date_joined", "core_user"."title", "core_user"."role", "core_user"."account_status", "core_user"."college", "core_user"."profile_completed", "core_user"."student_id", "core_user"."year_level" FROM "core_user" WHERE "core_user"."id" = %s LIMIT 21
```

Only 3 queries executed; there are no fourth/fifth queries to report.

Similar-query patterns:

### Student Behavior: five slowest SQL queries, run 2

SQL below retains parameter placeholders; parameter values and database results are not included.

1. **208.075 ms**

```sql
SELECT "faculty_consultationrequest"."agenda" AS "agenda", COUNT("faculty_consultationrequest"."request_id") AS "count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s) GROUP BY 1
```

2. **203.903 ms**

```sql
SELECT "faculty_consultationrequest"."date" AS "date" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s AND "faculty_consultationrequest"."status" = %s) ORDER BY 1 DESC
```

3. **202.170 ms**

```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s)
```

4. **201.763 ms**

```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s AND "faculty_consultationrequest"."status" = %s)
```

5. **200.377 ms**

```sql
SELECT "faculty_consultationrequest"."date" AS "date" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s) ORDER BY 1 DESC
```

Similar-query patterns:

Executed 4 times:
```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s)
```

Executed 3 times:
```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s AND "faculty_consultationrequest"."status" = %s)
```

Executed 2 times:
```sql
SELECT "faculty_consultationrequest"."date" AS "date" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s) ORDER BY 1 DESC
```
## CCS / code (3 active faculty)

| Page | Run | SQL queries | SQL ms | Request wall ms | Duplicate queries / groups | Excess repeats | Similar queries / groups |
|---|---:|---:|---:|---:|---:|---:|---:|
| College Overview | 1 | 37 | 4749.629 | 7778.239 | 9 / 4 | 5 | 17 / 6 |
| College Overview | 2 | 37 | 4889.148 | 5379.477 | 9 / 4 | 5 | 17 / 6 |
| Peak Analytics | 1 | 37 | 3703.630 | 4062.523 | 7 / 3 | 4 | 15 / 5 |
| Peak Analytics | 2 | 37 | 4539.514 | 4842.125 | 7 / 3 | 4 | 15 / 5 |
| Faculty Trends | 1 | 26 | 3611.665 | 3872.068 | 0 / 0 | 0 | 21 / 7 |
| Faculty Trends | 2 | 26 | 3476.181 | 3775.992 | 0 / 0 | 0 | 21 / 7 |
| Student Behavior | 1 | 37 | 5170.714 | 5462.376 | 7 / 3 | 4 | 15 / 5 |
| Student Behavior | 2 | 37 | 3992.820 | 4367.806 | 7 / 3 | 4 | 15 / 5 |

### College Overview: five slowest SQL queries, run 2

SQL below retains parameter placeholders; parameter values and database results are not included.

1. **288.567 ms**

```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s)
```

2. **209.420 ms**

```sql
SELECT "faculty_statushistory"."history_id", "faculty_statushistory"."faculty_id", "faculty_statushistory"."status", "faculty_statushistory"."changed_at" FROM "faculty_statushistory" WHERE ("faculty_statushistory"."changed_at" >= %s AND "faculty_statushistory"."changed_at" < %s AND "faculty_statushistory"."faculty_id" = %s) ORDER BY "faculty_statushistory"."changed_at" ASC
```

3. **207.328 ms**

```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s AND "faculty_consultationrequest"."start_time" IS NULL)
```

4. **202.913 ms**

```sql
SELECT "faculty_consultationrequest"."status" AS "status", COUNT("faculty_consultationrequest"."request_id") AS "count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s) GROUP BY 1
```

5. **199.671 ms**

```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s)
```

Similar-query patterns:

Executed 4 times:
```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s)
```

Executed 3 times:
```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s AND "faculty_consultationrequest"."status" = %s)
```

Executed 3 times:
```sql
SELECT "faculty_statushistory"."history_id", "faculty_statushistory"."faculty_id", "faculty_statushistory"."status", "faculty_statushistory"."changed_at" FROM "faculty_statushistory" WHERE ("faculty_statushistory"."changed_at" < %s AND "faculty_statushistory"."faculty_id" = %s) ORDER BY "faculty_statushistory"."changed_at" DESC LIMIT 1
```

Executed 3 times:
```sql
SELECT "faculty_statushistory"."history_id", "faculty_statushistory"."faculty_id", "faculty_statushistory"."status", "faculty_statushistory"."changed_at" FROM "faculty_statushistory" WHERE ("faculty_statushistory"."changed_at" >= %s AND "faculty_statushistory"."changed_at" < %s AND "faculty_statushistory"."faculty_id" = %s) ORDER BY "faculty_statushistory"."changed_at" ASC
```

Executed 2 times:
```sql
SELECT "core_college"."id", "core_college"."code", "core_college"."name", "core_college"."description", "core_college"."created_at" FROM "core_college" WHERE UPPER("core_college"."code"::text) = UPPER(%s) ORDER BY "core_college"."id" ASC LIMIT 1
```

Executed 2 times:
```sql
SELECT "faculty_consultationrequest"."date" AS "date" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s) ORDER BY 1 DESC
```

### Peak Analytics: five slowest SQL queries, run 2

SQL below retains parameter placeholders; parameter values and database results are not included.

1. **286.862 ms**

```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s)
```

2. **252.525 ms**

```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s AND "faculty_consultationrequest"."approved_at" IS NOT NULL)
```

3. **250.395 ms**

```sql
SELECT "faculty_facultyprofile"."faculty_id", "faculty_facultyprofile"."user_id", "faculty_facultyprofile"."college_id", "faculty_facultyprofile"."office_location", "faculty_facultyprofile"."current_status", "faculty_facultyprofile"."status_note", "faculty_facultyprofile"."status_updated_at", "faculty_facultyprofile"."manual_status", "faculty_facultyprofile"."manual_status_override", "faculty_facultyprofile"."manual_status_expires_at", "faculty_facultyprofile"."sync_enabled", "faculty_facultyprofile"."walk_ins_enabled", "faculty_facultyprofile"."last_calendar_sync_at", "faculty_facultyprofile"."schedule_last_updated_at", "faculty_facultyprofile"."photo_url", "faculty_facultyprofile"."biography", "core_user"."id", "core_user"."password", "core_user"."last_login", "core_user"."is_superuser", "core_user"."username", "core_user"."first_name", "core_user"."last_name", "core_user"."email", "core_user"."is_staff", "core_user"."is_active", "core_user"."date_joined", "core_user"."title", "core_user"."role", "core_user"."account_status", "core_user"."college", "core_user"."profile_completed", "core_user"."student_id", "core_user"."year_level" FROM "faculty_facultyprofile" INNER JOIN "core_user" ON ("faculty_facultyprofile"."user_id" = "core_user"."id") WHERE "faculty_facultyprofile"."faculty_id" IN (%s)
```

4. **240.552 ms**

```sql
SELECT "faculty_statushistory"."history_id", "faculty_statushistory"."faculty_id", "faculty_statushistory"."status", "faculty_statushistory"."changed_at" FROM "faculty_statushistory" WHERE ("faculty_statushistory"."changed_at" >= %s AND "faculty_statushistory"."changed_at" < %s AND "faculty_statushistory"."faculty_id" = %s) ORDER BY "faculty_statushistory"."changed_at" ASC
```

5. **200.382 ms**

```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s AND "faculty_consultationrequest"."status" = %s)
```

Similar-query patterns:

Executed 4 times:
```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s)
```

Executed 3 times:
```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s AND "faculty_consultationrequest"."status" = %s)
```

Executed 3 times:
```sql
SELECT "faculty_statushistory"."history_id", "faculty_statushistory"."faculty_id", "faculty_statushistory"."status", "faculty_statushistory"."changed_at" FROM "faculty_statushistory" WHERE ("faculty_statushistory"."changed_at" < %s AND "faculty_statushistory"."faculty_id" = %s) ORDER BY "faculty_statushistory"."changed_at" DESC LIMIT 1
```

Executed 3 times:
```sql
SELECT "faculty_statushistory"."history_id", "faculty_statushistory"."faculty_id", "faculty_statushistory"."status", "faculty_statushistory"."changed_at" FROM "faculty_statushistory" WHERE ("faculty_statushistory"."changed_at" >= %s AND "faculty_statushistory"."changed_at" < %s AND "faculty_statushistory"."faculty_id" = %s) ORDER BY "faculty_statushistory"."changed_at" ASC
```

Executed 2 times:
```sql
SELECT "faculty_consultationrequest"."date" AS "date" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s) ORDER BY 1 DESC
```

### Faculty Trends: five slowest SQL queries, run 2

SQL below retains parameter placeholders; parameter values and database results are not included.

1. **296.277 ms**

```sql
SELECT "faculty_statushistory"."history_id", "faculty_statushistory"."faculty_id", "faculty_statushistory"."status", "faculty_statushistory"."changed_at" FROM "faculty_statushistory" WHERE "faculty_statushistory"."faculty_id" = %s ORDER BY "faculty_statushistory"."changed_at" DESC LIMIT 1
```

2. **204.884 ms**

```sql
SELECT "faculty_statushistory"."history_id", "faculty_statushistory"."faculty_id", "faculty_statushistory"."status", "faculty_statushistory"."changed_at" FROM "faculty_statushistory" WHERE ("faculty_statushistory"."changed_at" >= %s AND "faculty_statushistory"."changed_at" < %s AND "faculty_statushistory"."faculty_id" = %s) ORDER BY "faculty_statushistory"."changed_at" ASC
```

3. **203.637 ms**

```sql
SELECT "faculty_facultyprofile"."faculty_id", "faculty_facultyprofile"."user_id", "faculty_facultyprofile"."college_id", "faculty_facultyprofile"."office_location", "faculty_facultyprofile"."current_status", "faculty_facultyprofile"."status_note", "faculty_facultyprofile"."status_updated_at", "faculty_facultyprofile"."manual_status", "faculty_facultyprofile"."manual_status_override", "faculty_facultyprofile"."manual_status_expires_at", "faculty_facultyprofile"."sync_enabled", "faculty_facultyprofile"."walk_ins_enabled", "faculty_facultyprofile"."last_calendar_sync_at", "faculty_facultyprofile"."schedule_last_updated_at", "faculty_facultyprofile"."photo_url", "faculty_facultyprofile"."biography", "core_user"."id", "core_user"."password", "core_user"."last_login", "core_user"."is_superuser", "core_user"."username", "core_user"."first_name", "core_user"."last_name", "core_user"."email", "core_user"."is_staff", "core_user"."is_active", "core_user"."date_joined", "core_user"."title", "core_user"."role", "core_user"."account_status", "core_user"."college", "core_user"."profile_completed", "core_user"."student_id", "core_user"."year_level" FROM "faculty_facultyprofile" INNER JOIN "core_user" ON ("faculty_facultyprofile"."user_id" = "core_user"."id") WHERE "faculty_facultyprofile"."faculty_id" IN (%s, %s, %s)
```

4. **202.542 ms**

```sql
SELECT COUNT(*) AS "__count" FROM "faculty_statushistory" WHERE ("faculty_statushistory"."changed_at" >= %s AND "faculty_statushistory"."changed_at" < %s AND "faculty_statushistory"."faculty_id" = %s)
```

5. **202.510 ms**

```sql
SELECT "faculty_statushistory"."history_id", "faculty_statushistory"."faculty_id", "faculty_statushistory"."status", "faculty_statushistory"."changed_at" FROM "faculty_statushistory" WHERE ("faculty_statushistory"."changed_at" < %s AND "faculty_statushistory"."faculty_id" = %s) ORDER BY "faculty_statushistory"."changed_at" DESC LIMIT 1
```

Similar-query patterns:

Executed 3 times:
```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s AND "faculty_consultationrequest"."faculty_id" = %s)
```

Executed 3 times:
```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s AND "faculty_consultationrequest"."faculty_id" = %s AND "faculty_consultationrequest"."status" = %s)
```

Executed 3 times:
```sql
SELECT COUNT(*) AS "__count" FROM "faculty_statushistory" WHERE ("faculty_statushistory"."changed_at" >= %s AND "faculty_statushistory"."changed_at" < %s AND "faculty_statushistory"."faculty_id" = %s)
```

Executed 3 times:
```sql
SELECT "faculty_consultationrequest"."requested_at" AS "requested_at", "faculty_consultationrequest"."approved_at" AS "approved_at" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s AND "faculty_consultationrequest"."faculty_id" = %s AND "faculty_consultationrequest"."approved_at" IS NOT NULL) ORDER BY "faculty_consultationrequest"."date" DESC
```

Executed 3 times:
```sql
SELECT "faculty_statushistory"."history_id", "faculty_statushistory"."faculty_id", "faculty_statushistory"."status", "faculty_statushistory"."changed_at" FROM "faculty_statushistory" WHERE ("faculty_statushistory"."changed_at" < %s AND "faculty_statushistory"."faculty_id" = %s) ORDER BY "faculty_statushistory"."changed_at" DESC LIMIT 1
```

Executed 3 times:
```sql
SELECT "faculty_statushistory"."history_id", "faculty_statushistory"."faculty_id", "faculty_statushistory"."status", "faculty_statushistory"."changed_at" FROM "faculty_statushistory" WHERE ("faculty_statushistory"."changed_at" >= %s AND "faculty_statushistory"."changed_at" < %s AND "faculty_statushistory"."faculty_id" = %s) ORDER BY "faculty_statushistory"."changed_at" ASC
```

Executed 3 times:
```sql
SELECT "faculty_statushistory"."history_id", "faculty_statushistory"."faculty_id", "faculty_statushistory"."status", "faculty_statushistory"."changed_at" FROM "faculty_statushistory" WHERE "faculty_statushistory"."faculty_id" = %s ORDER BY "faculty_statushistory"."changed_at" DESC LIMIT 1
```

### Student Behavior: five slowest SQL queries, run 2

SQL below retains parameter placeholders; parameter values and database results are not included.

1. **200.789 ms**

```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s AND "faculty_consultationrequest"."end_time" IS NULL)
```

2. **199.206 ms**

```sql
SELECT "faculty_consultationrequest"."date" AS "date" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s) ORDER BY 1 DESC
```

3. **177.265 ms**

```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s)
```

4. **116.715 ms**

```sql
SELECT "core_user"."id", "core_user"."password", "core_user"."last_login", "core_user"."is_superuser", "core_user"."username", "core_user"."first_name", "core_user"."last_name", "core_user"."email", "core_user"."is_staff", "core_user"."is_active", "core_user"."date_joined", "core_user"."title", "core_user"."role", "core_user"."account_status", "core_user"."college", "core_user"."profile_completed", "core_user"."student_id", "core_user"."year_level" FROM "core_user" WHERE "core_user"."id" = %s LIMIT 21
```

5. **106.586 ms**

```sql
SELECT COUNT(*) AS "__count" FROM "faculty_facultyprofile" INNER JOIN "core_user" ON ("faculty_facultyprofile"."user_id" = "core_user"."id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "core_user"."account_status" = %s AND "core_user"."role" = %s)
```

Similar-query patterns:

Executed 4 times:
```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s)
```

Executed 3 times:
```sql
SELECT COUNT(*) AS "__count" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s AND "faculty_consultationrequest"."status" = %s)
```

Executed 3 times:
```sql
SELECT "faculty_statushistory"."history_id", "faculty_statushistory"."faculty_id", "faculty_statushistory"."status", "faculty_statushistory"."changed_at" FROM "faculty_statushistory" WHERE ("faculty_statushistory"."changed_at" < %s AND "faculty_statushistory"."faculty_id" = %s) ORDER BY "faculty_statushistory"."changed_at" DESC LIMIT 1
```

Executed 3 times:
```sql
SELECT "faculty_statushistory"."history_id", "faculty_statushistory"."faculty_id", "faculty_statushistory"."status", "faculty_statushistory"."changed_at" FROM "faculty_statushistory" WHERE ("faculty_statushistory"."changed_at" >= %s AND "faculty_statushistory"."changed_at" < %s AND "faculty_statushistory"."faculty_id" = %s) ORDER BY "faculty_statushistory"."changed_at" ASC
```

Executed 2 times:
```sql
SELECT "faculty_consultationrequest"."date" AS "date" FROM "faculty_consultationrequest" INNER JOIN "faculty_facultyprofile" ON ("faculty_consultationrequest"."faculty_id" = "faculty_facultyprofile"."faculty_id") WHERE (UPPER("faculty_facultyprofile"."college_id"::text) = UPPER(%s) AND "faculty_consultationrequest"."date" >= %s AND "faculty_consultationrequest"."date" <= %s) ORDER BY 1 DESC
```

## Development setup

- Install with `python -m pip install -r requirements-dev.txt`. Production continues to use requirements.txt.
- Development-only app, middleware and loopback INTERNAL_IPS. URLs require DEBUG and the installed toolbar app.
- `manage.py check`: passed. Production settings: toolbar app absent and toolbar URL namespace absent (checked).
- Reproduce: `python scripts/profile_college_head.py testdepthead` or `python scripts/profile_college_head.py code` using the project virtual environment.
- Setup reference: https://django-debug-toolbar.readthedocs.io/en/latest/installation.html
