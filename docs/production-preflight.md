# Production preflight: read only

Run from the repository folder on `feature/multi-school-validation`. Nothing
needs to be pushed to use this helper. Do not run the rehearsal migration script
against production.

First preview the connection identity, without connecting to any database:

```powershell
.\venv\Scripts\python.exe scripts/preflight_production.py
```

The script reads the main `.env` DB_* values explicitly. It prints only the
project reference, never passwords or connection strings. Compare that reference
with the Project ID/reference in the real Supabase project's settings. It must
not be the staging or rehearsal project. Missing or unrecognized configuration
stops the script.

After confirming the reference, replace `YOUR_PRODUCTION_PROJECT_REF` below
with that exact reference. Use the exact existing Super Admin email intended
for later conversion:

```powershell
.\venv\Scripts\python.exe scripts/preflight_production.py --project-ref "YOUR_PRODUCTION_PROJECT_REF" --system-admin-email "facsync@gmail.com"
```

This command connects to the production database, reads metadata and counts in
one read-only, repeatable-read transaction, then rolls it back and closes the
connection. It does not run migrations, repair records, convert accounts, send
emails, or call Google/AI/Storage APIs. No database dump or personal records are
written to disk. The report includes only migration names, counts and blockers.

It checks:

- The main .env project matches the explicit reference and differs from staging
  and rehearsal; SSL and the port-5432 direct/session connection are required.
- The server actually enforces a read-only transaction.
- Required legacy FacSync tables exist in public and School tables do not yet exist.
- The pending migration set is exactly the five rehearsed migrations, with
  consistent history. Django supplies only the local graph; it is configured
  with SQLite, not connected to the production database through its ORM.
- College codes/names, unresolved references and faculty/user college disagreements.
- The number of `CCS2` AI-insight rows, without deleting them. An unresolved
  reference anywhere blocks readiness, including this cache if still orphaned.
- The intended conversion email matches one active Super Admin and at least
  one other active Super Admin will remain for ADNU. No email is printed.

An exit code of 2 means the report contains data blockers. A stopped preflight
or `ready_for_migration_review: false` is a reason to review the findings, not
to run `migrate` anyway. A true result still requires a fresh backup and the
coordinated maintenance/migration/deployment procedure; it is not permission
to deploy automatically.

The helper has eleven offline tests:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s scripts/tests -p test_production_preflight.py -v
```

Those tests passed during preparation. Configuration reads and production
connections were mocked; the real local migration graph also loaded with both
PostgreSQL and SQLite connection creation blocked. No production connection was
made while preparing or testing this helper.

## Authorized production cache cleanup result

After the user confirmed a fresh public-schema backup and explicitly approved
the production cleanup, exactly one orphaned `depthead_collegeaiinsight` row
was deleted: ID 3, college code `CCS2`. There was no matching College, incoming
foreign key, or custom trigger on the cache table. The backup file was verified
present and nonempty before the operation.

The first deletion attempt refused before any DELETE because scheduler
bookkeeping changed between preview and execution. A read-only comparison
identified only `faculty_statusschedulerstate`; the target row and backup were
unchanged. The retry allowed only that table to advance between checks. Inside
the cleanup transaction, fingerprints across 21 tables verified preservation
of all captured records except the specified cache row, including migration
history. No user, role, college, consultation, or calendar record was changed
by the cleanup.

The subsequent read-only production preflight passed:

- `issues`: empty.
- `ccs2_insight_rows`: 0; cached insights decreased from 3 to 2.
- All college references resolve; zero faculty/user college disagreements.
- 16 users, 8 colleges and 26 consultations remain.
- The intended conversion account is an active Super Admin, with two other
  active Super Admins remaining.
- Exactly the five rehearsed migrations are still pending.
- `ready_for_migration_review`: true.

The single-use cleanup helper, hashes and post-cleanup preflight report are
local-only under the ignored `.staging-backups/production-ccs2-cleanup/` folder.
No production migration, account conversion, push, or deployment was performed.
Migration readiness is not deployment authorization.
