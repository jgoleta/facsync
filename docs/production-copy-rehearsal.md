# Production-copy migration rehearsal

The production `public` schema backup was restored by the user into a fresh
Supabase project. Production and the existing shared staging project are not
targets for the rehearsal. The user reported empty production Storage buckets
and saved the code ZIP matching the deployed Vercel version. The rehearsal
Data API must remain disabled because this copy contains real records.

`.env.rehearsal` supplies the new project credentials and is ignored, along with
accidental similarly named copies. Only `.env.rehearsal.example` is trackable.
Never paste or commit database credentials or the production dump.

`config.settings.rehearsal` rejects a project matching the primary database,
primary Supabase Storage URL, or existing staging project. It fixes the schema
to `public`, requires SSL/session port 5432, and enforces read-only mode on each
established connection. Poolers may ignore startup options, so enforcement is
also explicit at the session level and verified. The preflight additionally
sets and checks transaction read-only mode before reading restored records.

This settings module is command-line only: its URL configuration has no routes,
email delivery is discarded, external service credentials are blanked, status
queueing is disabled, and the preflight blocks requests/httpx calls. No server,
OAuth login, calendar job or email job should be run against the production copy.

Run the read-only check with:

```powershell
.\venv\Scripts\python.exe scripts/preflight_rehearsal.py
```

The check lists pending migrations, record/role counts, unresolved college
references and faculty/user disagreements. It does not display names, emails,
tokens, passwords or insight contents. It never calls migrate or repairs data.
Do not run the ordinary test suite against this persistent copy.

## Observed preflight result

The restored copy contains 16 users, eight colleges, five faculty profiles and
26 consultations. Three users are active Super Admins. All examined User,
FacultyProfile, invitation, closure and announcement college references resolve;
there are no faculty/user college disagreements.

The initial preflight found one blocking legacy reference:

- Table: `depthead_collegeaiinsight`.
- Record ID: `3`.
- College code: `CCS2`.
- The college table has `CCS`, but no `CCS2`.

The ADNU data migration intentionally refuses unresolved references rather than
assigning or renaming them silently. The user confirmed that CCS2 was likely a
deleted college and explicitly authorized removal of this cache from the
rehearsal copy without an archive. Exactly record ID 3 with code CCS2 was removed
in a single transaction. All other table contents and the remaining AI caches
matched their pre-removal fingerprints before commit. No archive was created.
Production and staging were not changed; the original production backup remains
untouched. The same orphan may still require handling before production rollout.

The subsequent read-only preflight passes: no unresolved college references or
faculty/user disagreements remain, and all three active Super Admins remain.
There are now two AI cache records. At this preflight stage, no migrations had
been applied.

The reviewed plan contains five migrations:

1. `core.0020_school_foundation`
2. `depthead.0002_collegeaiinsight_school_and_more`
3. `core.0021_attach_existing_to_adnu`
4. `core.0022_alter_user_managers`
5. `core.0023_alter_user_role_superadmininvite`

No migrations ran during the preflight. Read-only settings deliberately prevent
accidental migration commands.

## Approved migration runner

`scripts/migrate_production_copy_rehearsal.py` uses the same fixed rehearsal
settings, project guards and offline controls. Its default is preview only:

```powershell
.\venv\Scripts\python.exe scripts/migrate_production_copy_rehearsal.py
```

The user's approval authorizes `--apply` on this restored copy. The runner rejects
plans other than the five listed migrations. It fingerprints existing records in
memory without exporting record contents, then tests forward and reverse inside
one transaction that is rolled back. Rollback must restore original table and
constraint definitions, all original records, and the applied migration set.

Only after those checks pass does another transaction apply the migrations and
normal Django content type/permission setup. All original fields and records
must still match; changes are limited to school ownership, the new School-related
tables, and the expected migration/content type/permission entries. No roles are
promoted and no domain is assigned. Relation IDs, ownership and grants in other
schemas must remain unchanged. Normal rehearsal sessions remain read-only;
write mode is enabled only for these bounded, approved transactions.

The result report is saved under the ignored
`.staging-backups/production-copy-rehearsal/migration-report.json`. It contains
counts and verification results, not record contents, credentials or tokens.
Once applied, the legacy preflight/runner will refuse another run against this
now-migrated copy; inspect the result rather than attempting to reapply it.

## Verified result

The authorized rehearsal passed. Forward migration and reverse migration were
both verified against the restored production data, and that test transaction
was rolled back. The five migrations were then committed to the rehearsal copy
with the expected Django content types and permissions. No pending migrations
remain on this copy.

- One active school: ADNU.
- All 16 existing users and eight colleges attached to ADNU.
- All 26 consultations preserved, along with the other existing records.
- Roles preserved: four faculty, six students, three College Heads and three
  Super Admins. All three active Super Admins remain active.
- Original fields/IDs preserved; new school ownership is the intended addition.
- Zero domains assigned and zero accounts promoted/created as System Admin.
- Other schemas' relation IDs, ownership and grants unchanged.
- No emails, Calendar sync or external HTTP actions occurred.

Production and the original staging project were not modified. The deleted CCS2
cache was removed only from the rehearsal copy; its production counterpart may
still need handling before a separately authorized production migration.

This verifies the data migration and rollback, not a complete production release.
The previously documented full-suite baseline still has 39 failures and nine
errors. Production rollout still needs review of those failures, a maintenance
window and fresh backup, the approved legacy-cache cleanup, explicit domain
assignment, and the guarded System Admin account conversion. None of those
production operations were performed by this rehearsal.
