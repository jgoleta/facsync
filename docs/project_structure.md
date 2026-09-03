# Project structure

FacSync is organized as a set of role-focused Django applications. Code that is
used by more than one role belongs in `core`; role-specific behavior stays in
its corresponding application.

```text
facsync/
|-- facsync_project/       Django project configuration
|-- core/                  Shared accounts, notifications, and UI utilities
|-- faculty/               Faculty workflows and calendar integrations
|-- students/              Student browsing and consultation workflows
|-- depthead/              Department-head administration and analytics
|-- superadmin/            System-wide administration
|-- docs/                  Project documentation
|-- scripts/               Standalone development utilities
|-- manage.py
|-- requirements.txt
`-- README.md
```

## Application conventions

- Python modules and packages use `snake_case`.
- Templates and static assets remain namespaced by Django application.
- Shared calendar code lives under `core/static/core/js/calendar/`.
- Faculty editing code lives under `faculty/static/faculty/js/calendar/`.
- Student read-only calendar code lives under
  `students/static/students/js/calendar/`.
- Faculty domain integrations live under `faculty/services/`.
- Existing migrations are historical records and should not be renamed or
  reorganized.

## Verification

Run checks and the local, isolated test suite with:

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py test --settings=facsync_project.test_settings
```
