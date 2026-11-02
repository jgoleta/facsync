# System Admin management UI

Manage Schools and Manage Super Admins now use directory tables, status pills,
and the existing admin spacing and typography. The duplicate tab strip is removed
from the shared layout; sidebar navigation and active states remain. System
Overview content is unchanged.

School counts include existing Super Admin accounts, including deactivated
accounts, and exclude invitations. Domain chips and counts are loaded without
per-row queries. Accounts and unused invitations have separate bordered cards,
each with its own empty/filter state. The school filter applies to both cards,
including deactivated invitations and suspended schools. Account
photos reuse `User.avatar_url`, `User.avatar_initials` and the shared avatar
component; schools and invitations use initials.

## Forms and feedback

Existing form links open native modal dialogs when supported. X, Cancel and
Escape close them; outside clicks close only untouched forms. Focus enters the
form, stays inside the open dialog, and returns to the trigger. Native dialogs
make the background inert. Existing full-page links and POST routes remain
available without JavaScript.

The JavaScript submits the existing Django form and reads its HTML response.
Invalid bound forms replace the modal form without discarding entered values.
The server remains authoritative for domain assignment, codes, school status,
roles and invitation validation. Live domain-format guidance accepts the same
whitespace/comma/semicolon separators as the existing form.

Disabled buttons, spinners and a processing guard prevent duplicate submissions
on the current page. The action payload is captured before disabling controls.
The form URL is read with `getAttribute('action')` because buttons named `action`
shadow `form.action`. Redirected Django messages preserve success/error/warning
severity in toasts, including saved actions whose email failed. Uncertain network
outcomes instruct the user to check the list before trying again; no automatic
retry is performed. Closing a submitted form does not cancel the saved action.

The Schools and Super Admins skeletons have separate templates matching their
own table columns; the Super Admin skeleton has two cards. System Overview has
its own skeleton matching the three summary cards. They appear during navigation
without delaying a ready page. The sidebar highlight and `aria-current` change
immediately on click and restore on cancelled navigation/timeouts. New styles are scoped to System Admin and
use existing theme variables; shared Super Admin/College Head styles are untouched.

No model, permission, validation, email, activation, suspension or URL-name rules
were changed. The only view changes add display counts, filter choices and page
descriptions. No migrations or production operations were performed.

## Verification

Seven new Django tests and nine real Chromium checks cover navigation, counts,
photos, invitations, empty states, validation, permissions, modal close behavior,
clean/dirty outside clicks, focus, duplicate submission, processing, both table
skeletons, all action types, and desktop/mobile layout. The existing seven System
Overview tests also pass. External resources were blocked in browser verification;
the logo therefore displays its initials fallback in local screenshots.

Browser tests are opt-in and require a local development dependency, not a
production requirement:

```powershell
.\venv\Scripts\python.exe -m pip install playwright==1.64.1
.\venv\Scripts\python.exe -m playwright install chromium
$env:SYSTEMADMIN_BROWSER_TESTS = "1"
.\venv\Scripts\python.exe manage.py test apps.systemadmin.tests --settings=config.settings.test
Remove-Item Env:SYSTEMADMIN_BROWSER_TESTS
```

Tests use synthetic accounts, SQLite and local-memory email. The verification
runner additionally disabled dotenv/credential loading and blocked external
network connections. No production settings or database were used.

The fresh full-suite comparison used the same local settings before and after:
313 tests before; 329 after (nine browser cases skipped in normal discovery).
Both runs have 204 failures and 104 errors. Exact failing test/subtest names and
outcomes match: no new or removed failing cases. This is the current checkout's
baseline, not the older school-aware baseline kept on a separate branch.

Raw logs, before/after failure identities, comparison JSON and screenshots are
local-only under `.staging-backups/systemadmin-ui/` and must not be pushed.
Tests and this document can be kept on the validation branch. Release files are
the changed `apps/systemadmin/views.py`, shared/page/form templates, both skeleton
partials, `static/systemadmin/css/systemadmin.css` and
`static/systemadmin/js/management.js` (paths relative to `apps/systemadmin/`).
