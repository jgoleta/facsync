# Account deactivation and consultation recovery

Faculty and student account actions now deactivate instead of deleting. The old
URL names remain available, but they update `account_status` and `is_active`.
Head account removal follows the same rule. Authorized administrators can
reactivate accounts within their existing school/department permissions.

The confirmation displays the account's consultation count. Deactivation preserves
consultations, schedules and history, removes login access, and removes faculty
from student booking choices. Direct booking and walk-in submissions also require
an active faculty account. Pending/approved consultations keep their status; the
warning calls this out so administrators can resolve outstanding appointments.

Faculty deactivation email uses the existing HTML layout and only sends on an
active-to-deactivated transition. Missing addresses are skipped. Delivery failure
does not undo the account change. Existing Google tokens are not exported by the
recovery tooling or restored into a missing account.

`faculty.0035_protect_consultation_history` changes the consultation's student and
faculty deletion behavior to `PROTECT`. Django refuses accidental hard deletion
of a referenced account/profile. This is not a complete database audit trail or
protection against someone deliberately deleting records through SQL.

## Verification

- 17 targeted tests passed for access changes, history protection, permissions,
  email failure/duplicate prevention, and recovery planning.
- A browser test passed for consultation-count warnings, cancellation, processing
  and duplicate-submit prevention on the Super Admin and Department Head pages.
- Django system checks and migration consistency checks passed.
- The existing 322-test suite retains the same 205 failing and 105 erroring test
  names as its baseline, with six skipped tests. The full suite is not green.
- The migration was applied only to the separate rehearsal database. All existing
  records in 30 application tables were unchanged.

## Selective recovery

Use `scripts/recover_consultation_history.py`. Its default is a read-only preview.
It reads `.env.rehearsal` as the source and `.env` as the production target, and
requires different identifiable Supabase projects. It verifies every consultation
field contained in the selected custom-format backup against rehearsal before
planning recovery. Historical department assignments added by the restructuring
are retained and validated against the target school and department.

Example preview/rehearsal (replace the backup path):

```powershell
.\venv\Scripts\python.exe scripts/recover_consultation_history.py --backup "C:\path\to\source.dump" --rehearse
```

Rehearsal copies production-shaped rows into temporary tables on the separate
rehearsal project, adds primary keys, identity uniqueness and relevant foreign
keys, and executes the recovery there. It rolls the transaction back and checks
that permanent rehearsal tables have not changed. Production connections are
read-only in preview and rehearsal modes.

The reviewed November 9 preview, using the November 6 backup, contains:

| Change | Count |
| --- | ---: |
| Existing production consultations preserved | 2 |
| Missing consultations restored | 17 |
| Missing students restored as deactivated | 1 |
| Old faculty profiles mapped to an existing replacement | 1 |
| Consultations retaining a null department | 6 |
| Total consultations after recovery | 19 |

The 17 missing requests comprise four completed, four pending, three approved,
three cancelled and three declined requests. Preserve those statuses. The six
requests with no department must not be assigned to Computer Science merely to
increase its analytics counts.

The missing student is restored with an unusable password, no staff/superuser
privileges, and deactivated access. No SocialAccount links, OAuth tokens or
sessions are restored. The six consultations for the deleted faculty account
are matched to its unique replacement by email, role, school and unit. Changed
or ambiguous identities stop recovery instead of being guessed.

## Production release and recovery approval

Production is unchanged by this work. Before production recovery:

1. Review the preview and approve the exact recovery.
2. Take a new production backup and temporarily avoid account deletion, account
   changes and consultation edits while performing recovery.
3. Coordinate deployment of the deactivation code and the new migration. Do not
   invoke the old permanent-removal actions during the transition.
4. Rerun rehearsal/preview to obtain its current `plan_sha256`.
5. Only after approval, run the recovery with `--apply`, `--expected-project`
   (the production project reference), `--approved-plan` (the reviewed hash),
   `--fresh-production-backup` (the new backup path), and `--backup` (source
   backup path).

The production command locks the affected tables, revalidates the plan and
inserts missing rows in a single transaction. It does not overwrite existing
consultations or reset the database. It runs no Django signals, email delivery
or Google Calendar operations. Normal application behavior resumes afterward;
restored pending/approved appointments retain their original meaning.

Recovery is not a full account restoration: the archived student's sign-in link
is intentionally absent. Reactivating that historical account alone does not
recreate a Google identity link; that would require a separately reviewed identity
recovery process.
