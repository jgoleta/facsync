# School foundation and ADNU backfill

This is the first compatibility phase, implemented and applied only to the
isolated `facsync_staging` schema. It does not enable multi-school onboarding.
Production has not been migrated.

## Changes

- `School`: name, immutable normalized code, active flag and timestamps. Schools
  cannot be deleted through the model or queryset; use audited suspension.
- `SchoolDomain`: normalized lowercase `.edu.ph` hostnames, globally unique
  without regard to case. Domains reject email addresses, URLs and wildcards.
- `SchoolChangeLog`: actor, preserved username, timestamp and old/new values for
  name, domain and active-state changes. Application edits require a schoolless,
  active `systemadmin` actor. History cannot be edited/deleted through the model.
- School ownership on colleges, users, faculty/College Head invites,
  announcements, closures and AI insights. Faculty profiles and consultation,
  schedule, walk-in, subscription and notification ownership derive through their
  existing user/faculty/college foreign keys; their identifiers are unchanged.
- College code and name uniqueness is scoped to school, case-insensitively.
  Code generation checks only that school. Closure and AI-insight uniqueness is
  also scoped to school and college code.

At the foundation phase, the model permission check reserved `systemadmin` for
later bootstrap and authentication work. The [System Admin phase](system-admin.md)
now exposes that role and its dedicated area; school Super Admin editors still
cannot grant it.

ADNU is created as `Ateneo de Naga University`, code `ADNU`, active, with **no
domain** and no fabricated operator/history. A System Admin will explicitly
assign `adnu.edu.ph` later. No `gbox.adnu.edu.ph` domain is seeded.

## Compatibility boundary

School links are temporarily nullable, without an automatic ADNU default. Every
existing school-owned record is backfilled, including blank-college accounts.
Existing roles, account statuses, college-code casing and related records are
preserved. This phase does not silently repair unresolved colleges or disagreeing
faculty/user college codes: the backfill refuses those cases for review.

This describes the foundation phase. Request scoping, authorization and suspension
enforcement have since been implemented; see
[multi-school-scoping.md](multi-school-scoping.md) for their coverage and remaining
rollout limits. [System Admin screens and invites](system-admin.md) and
[student domain registration](student-registration.md) are now implemented.
School-required database constraints remain a rollout compatibility concern.
Google Calendar behavior, email transport and analytics calculations are unchanged.

## Migration order

1. `core.0020_school_foundation`: add models/ownership fields and replace global
   uniqueness with school-scoped constraints.
2. `depthead.0002_collegeaiinsight_school_and_more`: add AI-insight ownership and
   school-scoped uniqueness.
3. `core.0021_attach_existing_to_adnu`: validate legacy data; create ADNU without
   domains; backfill ownership using the migration connection alias.

The final migration uses historical models, preserves Super Admin roles and
updates sample-manifest fingerprints only for records whose original hashes
still match. Previously edited sample records are never re-signed as unchanged.
Reverse migration restores matching original fingerprints.

## Backup and rehearsal evidence

Before migrating, the staging-only data and original migration history were
saved in the ignored `.staging-backups/before-school-v1/` directory:

- `data.json`: Django natural-key fixture.
- `data-physical.json`: 235 fixture objects with original IDs.
- `manifest.json`: checksums and the 87 previously applied migrations.

Restore and forward/reverse rehearsal used an in-memory local SQLite database:

```powershell
.\venv\Scripts\python.exe scripts/rehearse_school_migration.py
```

All 235 objects and their IDs restored exactly. Forward migration attached all
sample records and preserved ownership-manifest checks. Reversal reproduced the
original backup exactly. The script fixes its settings to local in-memory SQLite;
it never migrates staging or production.

On staging PostgreSQL, all three migrations were also applied and reversed inside
one transaction, which was then rolled back. Only after successful rehearsal were
the migrations applied normally. The final verification found 37 staging tables,
all 16 users and seven colleges attached to ADNU, both Super Admin roles intact,
zero assigned domains and a valid unchanged 71-record sample manifest. A sample
undo preview succeeded without deleting data. Relation IDs, ownership and grants
in other schemas matched the pre-migration inventory.

The full isolated local suite ran 325 tests: 39 failures and nine errors. All
13 new tests passed. Every failing test/subtest and outcome exactly matches the
captured 312-test baseline; see `test-baselines/school-phase.md` and its JSON.

## Rollback limits

The reverse data migration refuses rollback once an additional school, assigned
domain, audit history or System Admin account exists. This prevents silently
discarding tenant identity, edited domains or administrator history. The old
global college constraints must not be restored over multiple schools.

Before an authorized rollback, stop staging writes/jobs, take a fresh backup and
review the migration plan for the explicit staging settings. Returning core to
`0019_demodatabatch` also unapplies the dependent depthead ownership migration.
The rollback was rehearsed; it was not left applied to staging.

If the guard refuses, use a reviewed forward repair or restore a verified backup
to a fresh isolated schema with the matching pre-school code/migrations. Never
drop the shared project's schemas or use a blanket database reset. Restoring the
old backup loses subsequent writes, so reconcile them before choosing restore.
