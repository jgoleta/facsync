# Reversible defense demo data

`seed_demo_data` adds data to **one existing college**, with no announcements,
Google accounts/connections, invitations, subscriptions, email sends, or Gemini
calls. It never updates existing accounts or analytics caches. Use real accounts
to present the analytics; demo accounts have unusable passwords and `.invalid`
addresses, not working Google login identities.

## Preview first (no migration needed)

```powershell
.\venv\Scripts\python.exe manage.py seed_demo_data --college "College of Computer Studies" --batch defense-demo --dry-run
```

The command resolves the exact college name/code from the College table. On
PostgreSQL, dry-run executes inside a database-enforced read-only transaction.
It reports the database host/name, a project-specific target fingerprint, counts,
and distributions. The fingerprint is an acknowledgement aid, not a secret or
an access-control mechanism.

## Only after separate approval to write

The new `core.0019_demodatabatch` migration adds an ownership manifest table.
Review unapplied migrations before applying this migration to the approved
database; do not run a general migration command blindly against live data.

```powershell
.\venv\Scripts\python.exe manage.py migrate core 0019 --plan
.\venv\Scripts\python.exe manage.py migrate core 0019
.\venv\Scripts\python.exe manage.py seed_demo_data --college "College of Computer Studies" --batch defense-demo --confirm-target <FINGERPRINT_FROM_DRY_RUN>
```

Neither migration nor seed write was authorized merely by approving the dry run.
Do not paste the angle brackets; replace the placeholder with the printed value.
Re-run the preview if the environment/database or calendar day has changed.

The batch has 6 faculty, 18 students, 54 consultations, fourteen days of varied
status histories plus a carry-in state, two weeks of weekday teaching blocks,
and 10 walk-ins. Names/identifiers/messages carry demo labels. Manual overrides
keep the visible faculty status mix stable; automatic Calendar sync is disabled.
History and request timestamps are synthetic and are not real research evidence.

The seed uses one transaction and refuses existing batch names or identifier
collisions; it never updates a matching account. The only historical timestamp
updates affect consultation records created in that same transaction. Records
are fingerprinted after saving so later modifications can be detected.

Live seeding makes the records visible to real users and changes aggregate totals
in that college and Super Admin Overview. Stored Gemini insights are not refreshed
or removed. No existing record is changed to force agreement with the demo data.

## Undo

```powershell
.\venv\Scripts\python.exe manage.py seed_demo_data --batch defense-demo --undo --dry-run
.\venv\Scripts\python.exe manage.py seed_demo_data --batch defense-demo --undo --confirm-target <FINGERPRINT_FROM_DRY_RUN>
```

Undo checks exact manifest IDs and fingerprints, not names alone. It examines
deletion cascades and SET_NULL dependencies before deleting anything. A changed
demo account, real consultation attached to a demo faculty member, subscription,
or another outside dependency blocks the entire undo for review. There is no
force-delete option. Do not delete the manifest manually or run broad username
prefix deletes. If blocked, retain the data until dependencies are reviewed.

Undo removes the owned data and its manifest but leaves the additive table and
existing college in place. Any external account/data created manually while
presenting is outside this seed's ownership and must not be silently deleted.
