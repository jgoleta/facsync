# Calendar status mapping correction

Only the event-to-faculty-status mapping and its overlap priority changed.
Unavailable events now produce `unavailable`, Busy produces `busy`, and On Leave
produces `on_leave`. Existing legacy Virtual mapping remains supported internally;
the event dropdown is unchanged. Overlap priority is On Leave, Unavailable,
Virtual Only, Busy. Manual override still wins.

No scheduler, polling, Google API, settings, email delivery infrastructure, data
model or migration changes were made. This correction does not add live dashboard
refresh. Until that separate work is approved, refresh the dashboard to see the
newly calculated status after an event boundary.

## Git investigation

Local history was traced across the old and current service paths:

- `685828f` (`fixed and cleaned`, August 12, 2026, Asia/Manila) introduced
  `_update_status_from_calendar`; its ordinary Google event fallback was already
  Busy. There was no Unavailable mapping in that version.
- `e68bb31` (`booking update`, August 15, 2026) added local-event evaluation and
  overlap priorities, still mapping events other than On Leave/Virtual to Busy.
- `a6509c0` (`added Best Shared Time Window for college head meeting planning`,
  October 11, 2026) extracted the current `event_status()` helper while preserving
  that fallback. Its parent commit already had the incorrect mapping.

Thus `git blame` points at the October refactor for the current lines, but that
commit did not introduce the fallback. Available local history does not establish
a commit that removed a previously working Unavailable mapping. Other branches or
an older deployment may require their exact commit to compare.

Useful read-only commands:

```powershell
git blame -L 840,863 -- apps/faculty/services/google_calendar.py
git log --follow --oneline -S active_status -- apps/faculty/services/google_calendar.py
git show 685828f:faculty/facultyServices/googleCalendarService.py
git show a6509c0^:apps/faculty/services/google_calendar.py
```

## Verification

Eight new tests reproduced the mapping defect before the fix (15 failing subtest
cases), then all passed after it. Coverage includes the reported 09:00–09:30
Unavailable / 09:30–10:00 Busy / 10:00–10:30 Unavailable sequence on November 2,
2026 in Asia/Manila, exact boundaries, synced Google copies, recurring events,
overlap order/ties, manual overrides, existing mappings, school isolation and
duplicate transition prevention.

Fresh full-suite comparison: 313 tests before, 321 after. Both runs have 204
failures and 104 errors, with exactly matching failing test/subtest identities
and outcomes. No new failing names or removed failing names were found. These
are this checkout's existing failures, not a passing full suite.

Tests used in-memory SQLite, local-memory email, synthetic settings, disabled
credential-file loading and blocked external network connections. No production
database was accessed and no live emails were sent.

Raw baseline, focused results and exact full-suite failure-name comparisons are
local-only in `.staging-backups/calendar-status-mapping/` and must not be pushed.
The runtime release file is `apps/faculty/services/google_calendar.py`. The new
`apps/faculty/tests/test_calendar_status_mapping.py` and this document can stay on
the validation branch.
