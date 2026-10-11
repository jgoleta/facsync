# Best Shared Time Window

On College Head **Faculty Trends**, choose a labeled weekday in the current
Monday–Friday week and a duration, then select **Find best times**. The card
replaces College-wide availability by day. Most available faculty per day and
the status/consultation sections remain.

The planner checks 15-minute starts between 8 AM and 5 PM in the configured
calendar timezone (normally Asia/Manila). Past starts are excluded on weekdays.
On weekends the form can review Monday–Friday windows from the current week.
Durations are 30, 60, 120, 240, or 540
minutes. An unfiltered weekday page initially shows today's two-hour results.
On Saturday/Sunday the selector shows the latest Monday–Friday week, with
Friday selected initially and all five days available for review.

Each result leads with its time/start range and the number of faculty free
based on recorded schedules. The stacked bar shows free/conflict/unknown
proportions. Time-window buttons retain all grouped results and display one
window at a time, with the first selected initially. Faculty lists under Free, Conflict,
and Unknown are immediately visible in bordered columns. The short **How is this calculated?**
explanation is also visible without an expander. On wide screens the planner
appears on the left at 70% width, with status availability on the right at 30%.

The GET form remains usable without JavaScript. With JavaScript it requests
`/depthead/api/shared-windows/` and replaces only the card content. While loading,
the button is disabled, a spinner appears, and previous results stay dimmed.
Failures restore the form and retain previous results. The endpoint reuses the
same form validation, planner, and autoescaped Django partial as the full page.
It accepts the user's college only from their authenticated account.

Results count active faculty only in the authenticated head's college:

- **Conflict:** any recorded eligible schedule event or approved /
  cancellation-requested consultation overlaps the entire proposed window or
  any portion of it.
- **Free:** an eligible schedule occurrence exists for that date, with no
  overlapping commitment during the proposed window.
- **Unknown:** no qualifying schedule occurrence exists for that date and no
  commitment overlaps the window. Records on another weekday and live manual
  Available statuses do not establish day-specific knowledge. A consultation
  can establish a conflict without establishing availability outside its time.

All highest-headcount starts are retained in chronological order. Adjacent tied
starts are grouped only when the free, conflict, and unknown memberships are
identical. A grouped start range still uses the selected fixed duration.
No full-college window, zero known-free faculty, all-unknown schedules, empty
colleges, and insufficient remaining time have distinct messages.

## Shared logic and data limits

`apps/faculty/services/schedule_conflicts.py` supplies event eligibility,
recurrence/date rules, interval normalization, and overnight spillover to both
schedule analytics and status refresh. Status priority and manual override
precedence remain in status refresh. Planning is read-only: it never refreshes
statuses, synchronizes calendars, changes history, or sends notifications.

The planner uses local calendar copies, not live Google calls. It requires three
batched SELECTs for a populated roster regardless of faculty count. No new
database model, migration, cache, or scheduled job is required.

The retired daily percentage, two-hour threshold, chart CSS, browser questions
(including the dependent student best-day question), and AI recommendations
based on that percentage have been removed. AI context retains anonymous daily
ranking information and explicitly avoids inferring simultaneous availability.

Free means **no recorded conflict**, not confirmed attendance. The models do not
record whether a day's schedule is complete, so truly empty days remain unknown.
Live manual statuses are not projected into future planning. Lunch is not
automatically excluded. Virtual schedule events count as commitments.

Existing Google import limitations remain: local copies do not preserve event
transparency or a separate multi-day end date, and synchronization has a bounded
import horizon. Incomplete/outdated imports can affect results.

## Validation

- 54 focused Django tests and 3 JavaScript interaction tests pass: planner, remaining schedule rankings, AI insights,
  calendar import/edited occurrences/unified preview, and updated rendering.
- Tests cover simultaneous free time, partial/zero shared availability, unknown
  schedules, tied membership changes, fixed three-query behavior with 30
  faculty, boundaries, all-day/overnight/recurring events, consultations,
  manual override precedence, weekly validation, weekend behavior, and college
  isolation.
- Added presentation tests cover summary wording, stacked bars, weekday dropdown
  labels/disabled past options, show-more results, endpoint validation and
  isolation, loading, duplicate submissions, failure recovery, and form errors.
- Latest broader run: 109 tests, with the same 19 failures and 4 errors as the
  previous implementation. No new failures/errors; details are in local ignored
  `presentation-shared-windows.log`.
- Broader regression failures were compared against an isolated export of Git
  HEAD, using the same test settings and environment. See local ignored logs
  `baseline-shared-windows.log` and `final-shared-windows.log`.
- Browser visual verification was unavailable; Django response rendering and
  form/error behavior were verified. No production database was used for tests.

## Real-database endpoint profile

Measured a local Django request against the configured real PostgreSQL database
using a CCS College Head, five active faculty and 36 eligible schedule records.
Selected Friday, October 9, 2026, for a two-hour event during weekend review.
The script prevents non-read-only SQL and never persists login/session data.

| Run | Queries | SQL time | Endpoint time |
| --- | ---: | ---: | ---: |
| 1 (initialization) | 4 | 1,004 ms | 2,012 ms |
| 2 | 4 | 2,481 ms | 2,635 ms |
| 3 | 4 | 2,038 ms | 2,185 ms |
| 4 | 4 | 6,070 ms | 6,218 ms |
| 5 | 4 | 9,069 ms | 9,158 ms |

Warm median: **4,426 ms**; warm range: **2,185–9,158 ms**. Most elapsed time was
SQL/database I/O. These measurements include authentication and normal request
middleware, but exclude HTTP transit from a browser/deployed server. The session
is supplied in memory to avoid writes; the session lookup is therefore excluded.
The four measured queries are one authenticated-user lookup and three planner
queries. A normal database-backed session adds its own lookup.

Reproduce with `venv/Scripts/python.exe scripts/profile_shared_windows.py`.
The script selects the active College Head with the largest available roster.
The planning algorithm was not changed for this presentation update.
