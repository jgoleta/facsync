# Department restructuring: rehearsal preparation

Do not deploy the restructuring or migrate production until a separate restored
copy has passed the rehearsal. The previous rehearsal setup is absent from this
checkout. School registration remains on hold.

1. Copy `.env.rehearsal.example` to `.env.rehearsal` locally. Fill the five DB
   values using the **disposable copy's** database connection, never production.
   Use the direct connection or session pooler, not the transaction pooler.
   This file is ignored by Git. Do not publish it or share its password.
2. Confirm the copy's project reference and when it was last restored from
   production. An old copy cannot establish readiness for today's production data.
3. From the repository folder in PowerShell, inspect it without making changes:

   ```powershell
   .\venv\Scripts\python.exe scripts/check_department_rehearsal.py --project-ref "YOUR_COPY_PROJECT_REF"
   ```

The checker reads DB values only from `.env.rehearsal`. It privately reads `.env`
to identify and reject the production project; it does not display credentials.
It also rejects an unidentified target, mismatched reference or missing values.
Database connections default to read-only, and inspection runs in an explicit
read-only transaction. Outbound email, queue and provider credentials are not
loaded. The checker prints pending migrations, table counts, role totals and a
preliminary count of incomplete legacy data in completed student profiles.

This is an initial inspection, **not** a successful migration rehearsal. It does
not validate all department mappings or apply migrations. After inspection,
review the copy's freshness, rehearse the entire migration chain there, compare
preserved records and assignments, and check permissions and profiles. Review any
data that stops migration before deciding a repair; do not silently guess values.

Only after that succeeds should the production backup, maintenance window,
migration and deployment be scheduled together. A code deployment rollback does
not undo a database migration. No production changes are performed by this setup.

Local verification: eight synthetic target-guard checks passed (separate project,
production rejection, reference mismatch, unidentified production, missing field,
session-pooler identity, transaction-pooler rejection and storage-project match).
These checks made no database connections.

## Connection inspection — 2026-11-06

The read-only checker connected to the separately identified rehearsal project.
No FacSync tables were visible through its configured schema/search path, and
the migration executor reported all application migrations as pending. This is
not a restored production copy ready for rehearsal. Other Supabase schemas or
unrelated data were not audited and must not be assumed empty or disposable.

Next: identify a recent production dump, inspect its contents and the destination
before restoring it, then repeat the read-only inspection. No migrations or
record changes were performed during this connection check. The checker also
now preserves Windows runtime environment paths while excluding ambient
database and application/provider configuration.

## Fresh backup and destination conflict — 2026-11-06

Inspected `facsync-production-20261106-191853.dump` from the user's private
backup folder. PostgreSQL lists the archive successfully (361 entries), including
School, User, consultations and Django migration data. Listing does not prove a
successful restore or full data integrity.

A further read-only destination check found existing unrelated `members_*`
tables and shared Django/allauth tables (`auth_*`, `account_*`, `django_*`,
`socialaccount_*`) in public. These overlap the production archive. No restore
was attempted; do not use `--clean` or overwrite those objects. An empty,
separate destination is needed before continuing this rehearsal.

## New project rehearsal result — 2026-11-06

The user created a new project and replaced `.env.rehearsal` with its connection.
The target guard verified separation from production. A read-only catalog check
found no public tables, views or sequences. The existing, unrelated project was
left untouched.

Restored `facsync-production-20261106-191853.dump` into the new project using
`scripts/restore_department_rehearsal.py`: single transaction, no drop/clean,
no owner/ACL restore, and no recreation of Supabase's existing public schema.
Restore completed successfully. The restored copy contained 18 accounts, seven
students, three heads, five faculty profiles (one retained by a now-Super-Admin
account), 19 consultations, 18 schedule events and four Calendar connections.

`scripts/migrate_department_rehearsal.py` applied all seven pending migrations:
core.0026–0031 and faculty.0034. Final result:

- Seven agreed ADNU departments created, including Computer Science and Civil
  Engineering; three head assignments populated.
- All seven existing students classified as College.
- Zero pending migrations.
- Counts and hashes of all original fields across 26 application tables match
  before/after, including account roles, consultation statuses/IDs, Calendar
  connections/events, notifications and saved AI insights. New department and
  educational-level fields are intentionally additional. Demo manifest hashes
  are excluded from preservation comparison because migrations intentionally
  refresh unchanged ownership fingerprints; this copy contained no demo batches.
- User/head department school checks and historical consultation mapping passed.

The first attempt's final checker incorrectly compared historical consultation
departments with the current faculty owner's home department. One retained
profile is owned by a now-Super-Admin account with no home department. That
attempt rolled back all seven migrations; a read-only check confirmed core.0026
was not retained. The checker was corrected to compare the preserved historical
profile college/school mapping. The second complete attempt passed and committed
on the separate copy. The application's migration code was not changed.

Twenty-two read-only PostgreSQL checks then passed: six Super Admin pages,
seven head pages, four student pages plus profile setup, and four denied-role
checks. These use RequestFactory and the actual copied accounts, not a live
Google sign-in. Google status refresh and inactivity maintenance were mocked;
no live Calendar, email, queue or Gemini calls were tested. They complement the
earlier local isolation/browser suites and do not replace a full user walkthrough
or live-provider checks. The full local suite was not rerun for these script-only
changes; its last recorded baseline comparison remains in student-education.md.

Private reports are in ignored `.staging-backups/department-rehearsal/`:
`restore.log`, `before.json`, `migration-result.json` and `page-checks.json`.
The record-comparison reports store counts/hashes rather than raw account data.

Production has not been migrated, deployed, or written to by this rehearsal.
Before rollout, review the release file set and production migration/deployment
sequence, arrange a quiet window, and retain the fresh backup. Rehearsal scripts
reject the production project and must not be repurposed to bypass that guard.
