# FacSync

FacSync is a real-time faculty availability and consultation scheduling system
for Ateneo de Naga University. It provides public faculty availability,
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
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver


Copy the required values into `.env` before starting the application. Never
commit `.env` or production credentials.

## Verification
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
