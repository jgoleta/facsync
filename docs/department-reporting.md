# Department access and combined reporting — stage 3

Head dashboards and management actions now use active, explicitly assigned
departments within the head's school. College Head and Department Head are
display titles for the same existing role: neither grants access beyond those
assignments. Multiple heads may share the same departments. Removing an
assignment takes effect on the next request, without another login.

## Combined reports

Overview, peak analytics, student behavior, faculty trends, hourly availability,
monitoring, shared schedule windows and every preset chatbot question use the
combined department scope. There is no department filter on the reports.
Guessed faculty/user IDs are checked against that scope before viewing,
uploading or deleting schedules or removing a faculty account. An unassigned
head gets empty reports or an assignment error; there is no college fallback.
The existing authenticated directory also restricts head accounts to their
departments.

Consultations and walk-ins capture the faculty member's department on creation,
including bulk inserts. A submitted snapshot for a different department is
rejected. Consultation/walk-in reports use the saved reference, not a student's
home department or a changeable college label. Existing ADNU records receive
these links in the earlier foundation backfill. Faculty activity transfers
remain blocked in Super Admin management until historical transfer rules exist.

## AI insights

The existing analytics calculations, Gemini model, response validation,
privacy sanitization, weekly cache policy, failure fallback and visual layout
remain. The input is now one set of combined department statistics, producing
one interpretation. Old written insights are not merged.

The existing CollegeAIInsight table is reused. Its college_code field stores a
reserved `DEPARTMENTS:` key followed by a hash of the school ID and sorted,
distinct department IDs. Its existing school constraint keeps schools separate.
Old college-code entries remain untouched and are not served for department
scopes. Identical assignments can share an insight; a changed combination uses
a different entry and cannot fall back to the previous combination's insight.
An empty assignment has no AI insight.

Expiry keeps the existing behavior: after seven days, the next insight API
request attempts regeneration. This does not add a timer, cron job or background
worker. The first request for a previously unseen combination can generate an
insight immediately. Generation failures can use only that same combination's
stored result. Live provider behavior has not been tested in this local work.

## Department actions and recipients

Faculty invitations explicitly choose one assigned department, and first-login
activation uses the saved assignment. The form cannot invite to an unassigned,
inactive or foreign-school department.

Settings show a separate action card for each assigned department. Description
edits and closure changes have an explicit department target, as do announcement
posts. This is action targeting, not a report filter. Faculty/student notices
and notifications reach the selected department; faculty announcement/closure
emails use the same existing layouts and department-specific recipients.
Stage 4 now adds educational-level student audiences; see `student-education.md`.

A department closure blocks new consultations and walk-ins only with that
department's faculty. Other departments in the same college remain bookable.
Students still browse and book across departments within their school. Existing
appointments are not cancelled by closing a department. Existing Office Admin
management stays on its office path.

Schedule uploads use the selected faculty member's department CSV template.
Per-department download links are available. Saving a common template from the
combined Manage Faculty page applies it to all assigned departments; the form
states that scope. Existing schedule rows and Google Calendar logic are unchanged.

## Migration and deployment boundary

`core.0029_department_closure_scope` replaces the old college-code closure
uniqueness constraint with a conditional constraint for rows without a
department. The existing one-to-one department link enforces one closure per
department, allowing two departments in the same college to close independently.
It performs no data rewrite. No AI table or role migration is needed here.

This migration has run only in disposable local SQLite test databases. No
Supabase database, secrets file, production deployment or remote branch was
changed. A PostgreSQL rehearsal and backup remain required before rollout.
Reversing this closure constraint after multiple departments share a college
can fail uniqueness; do not force reversal or use `--fake`. Use the planned
backup or a reviewed forward repair if new data cannot fit the old schema.

Stage 4 now adds student educational levels, department-based profile choices
and announcement audience targeting; see `student-education.md`. The complete
restructuring still needs the PostgreSQL rehearsal before deployment. School
registration remains on hold.

## Verification — 2026-11-06

- Sixteen new endpoint/service tests pass: combined totals, same-college and
  cross-school isolation, guessed IDs, all chatbot questions, assignment
  revocation, inactive departments, invitations, notifications/email recipients,
  closure independence, snapshot capture, optional-college faculty reporting,
  cross-department student booking and the existing Office Admin path.
- The AI test mocks the provider, checks combined input totals, ignores a legacy
  college-wide insight, checks assignment-based cache separation, and verifies
  regeneration after expiry. No live Gemini request is made.
- Two Chromium checks pass: combined overview and invitation target selection;
  multiple department settings cards and saving only the selected description.
- The earlier 54-test foundation/management/reporting regression run passed;
  the two later booking/office scenarios also passed in the final 16-test run.
- Full suite: before 360 tests / 205 failures / 105 errors / four browser skips;
  after 378 tests / 205 failures / 105 errors / six browser skips. Comparison by
  exact failing test name, including subtests, found no added or resolved failures
  or errors. Browser tests were enabled and passed in a separate run.
- Django checks and `makemigrations --check --dry-run` pass. Verification uses
  synthetic settings, in-memory SQLite and blocked external network access.
  Local reports are in the ignored `.staging-backups/department-scope-*.json`
  and matching logs; database and provider credentials are not needed.
