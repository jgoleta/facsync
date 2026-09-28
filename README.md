# FacSync

FacSync is a real-time faculty availability and consultation scheduling system
Pilot-tested at Ateneo de Naga University. It provides public faculty availability,
consultation booking, walk-in queues, notifications, schedule management, and
Google Calendar integration.

## Applications

- `apps/core` - shared accounts, notifications, announcements, email, and UI code
- `apps/faculty` - faculty dashboards, schedules, consultations, and calendar sync
- `apps/students` - faculty discovery, read-only calendars, booking, and queues
- `apps/depthead` - college administration, monitoring, and analytics
- `apps/superadmin` - system-wide administration

See [docs/project_structure.md](docs/project_structure.md) for detailed file
placement and naming conventions.

## Setup
python -m venv venv
.\venv\Scripts\Activate
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py runserver


Copy the required values into `.env` before starting the application. Never
commit `.env` or production credentials.

## Verification

Online consultations use the faculty member's connected Google Calendar to
create an event with a Google Meet conference. Enable the Calendar API and
configure `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and the OAuth redirect URI
for `/faculty/calendar/connect/`. The default `calendar.events` scope permits
event creation; a separate Meet API or Meet Spaces permission is not required.
The connected calendar must support Google Meet. An `Invalid conference type
value` response means Google rejected the requested conference type; verify that
the faculty can add Meet from Google Calendar and check Workspace settings.

Approval saves the Google event ID immediately. If conference generation is
pending, request pages poll for the URL and then show **Join Google Meet** to both
participants. Rescheduling patches the same event. Completion removes the event
and the link from FacSync; this does not guarantee revocation of a copied Meet URL.
Consultation events have no attendees and use `sendUpdates=none`. Students and
faculty access the Meet link in FacSync without Google Calendar invitations.

python manage.py check
python manage.py test --settings=config.settings.test


The test settings use an isolated in-memory SQLite database and never connect
to the configured PostgreSQL database.

Entry points default to `config.settings.development`. Select another settings
module with `DJANGO_SETTINGS_MODULE` or Django's `--settings` option.
The server entry points are `config.wsgi:application` and
`config.asgi:application`. The production settings module currently preserves
the same values as development; this reorganization adds no deployment overrides.

Run the standalone email utility from the repository root with
`python -m scripts.test_email` so the project packages are importable.

## GEMINI_MODEL=gemini
