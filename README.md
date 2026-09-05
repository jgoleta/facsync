# FacSync

FacSync is a real-time faculty availability and consultation scheduling system
for Ateneo de Naga University. It provides public faculty availability,
consultation booking, walk-in queues, notifications, schedule management, and
Google Calendar integration.

## Applications

- `core` - shared accounts, notifications, announcements, email, and UI code
- `faculty` - faculty dashboards, schedules, consultations, and calendar sync
- `students` - faculty discovery, read-only calendars, booking, and queues
- `depthead` - college administration, monitoring, and analytics
- `superadmin` - system-wide administration

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
python manage.py test --settings=facsync_project.test_settings


The test settings use an isolated in-memory SQLite database and never connect
to the configured PostgreSQL database.

## GEMINI_MODEL=gemini
