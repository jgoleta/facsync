# Department management — stage 2

This adds the Super Admin screens and assignment flows on top of the department
foundation. School registration and System Admin are unchanged. This is local
work, not a complete production release. Stage 3 now switches head dashboards
and analytics to explicit department permissions; see `department-reporting.md`.
Stage 4 now implements student educational levels/profile choices; see
`student-education.md`. The database rehearsal still remains before deployment.

## Available screens

- Manage Departments: create, rename, describe, choose an optional same-school
  college, deactivate/reactivate, and delete an empty department. Codes are
  locked after creation. Linked accounts, invitations and records prevent
  deletion. Active members, heads and pending invitations prevent deactivation.
- Manage Colleges: shows the departments grouped under each college. College
  labels do not grant permissions. A college with departments cannot be deleted.
- Manage Admins: assign one or more active same-school departments to a head,
  choose College Head or Department Head as a title, and deactivate/reactivate.
  Multiple heads can share a department. Titles reuse the existing `dean` and
  `chairperson` values; no new role is added. Pending head invitations have
  editable department assignments and are shown separately from accounts.
- Manage Faculty: invite to an active same-school department or existing office;
  show department and derived college labels; filter by college and unit; edit
  an account's assignment. Profile identifiers and calendar connections are
  preserved. Transfers are blocked when consultations, walk-ins, status history
  or calendar events exist; retaining the same assignment is allowed.

Forms use native modal dialogs with keyboard focus handling. Outside clicks
close untouched forms only. Server errors retain entered values. A shared
processing guard disables controls and shows progress until the save returns,
preventing repeated submissions in that page. Connection failures warn that the
change may already have saved and should be checked before retrying.

## Invitations and activation

Head invitations carry explicit department assignments. First Google login
rechecks the saved invitation, verified email, active school and departments,
copies assignments to the account, and then deletes the invitation. Faculty
activation also copies the latest saved department. Legacy college-based faculty
invitations are accepted only when exactly one active department matches;
existing office invitations remain supported. Ambiguous academic assignments
are refused rather than guessed.

Head and faculty invitation emails are attempted after saving. Email failures
are logged by category and reported as a warning without undoing the saved
invitation. Head deactivation email is sent only on an active-to-deactivated
transition. Existing Office Admin management remains a separate flow.

## Files and migration boundary

The new routes live under the existing `superadmin` URL namespace. Department
views are in `apps/superadmin/department_views.py`; assignment forms and locking
helpers are in `forms.py` and `assignment_services.py`. The new management pages
share `base_management.html`, sidebar navigation and theme-variable styles.

`core.0028_head_title_labels` records display-label changes only. No stored title
codes are rewritten. All migrations so far have run only against disposable
in-memory SQLite in tests. No Supabase database was migrated or edited; nothing
was pushed or deployed.

## Verification — 2026-11-06

- All 40 focused foundation, migration and management tests passed, including
  19 new endpoint/activation tests for role restrictions, guessed foreign-school
  IDs, multi-department assignments, invalid inputs, protected deletion,
  historical transfer blocking, invitation activation and email failure.
- Four separate Chromium browser tests passed: form focus/closing, dirty forms,
  server errors retaining values, duplicate-submit prevention, assignment saving,
  filters, navigation highlighting and mobile overflow.
- Full suite: before 337 tests / 205 failures / 105 errors; after 360 tests /
  205 failures / 105 errors / four opt-in browser tests skipped. Comparing exact
  failing test names, including subtests, found no new or resolved failures or
  errors. Existing failures are not being described as a passing suite.
- `makemigrations --check --dry-run` found no missing migrations.
- Tests used synthetic settings, in-memory SQLite and email mocks; external
  network access was blocked. Browser checks used a local test server only.
  Live Google activation, provider email delivery and PostgreSQL concurrency
  still require the later rehearsal against a disposable restored copy.

## Next stage

Stage 3 now switches head views/actions, analytics, chatbots and AI insight caches
to explicit department assignments, and captures department references on new
operational records. See `department-reporting.md`. Student educational levels,
profile choices and announcement audiences are now implemented in stage 4; see
`student-education.md`. A PostgreSQL rehearsal remains before rollout.
