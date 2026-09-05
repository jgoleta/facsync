# Project structure

FacSync is organized as a set of role-focused Django applications. Code that is
used by more than one role belongs in `core`; role-specific behavior stays in
its corresponding application.

```text
facsync/
|-- config/
|   |-- settings/          base.py, development.py, production.py, test.py
|   |-- urls.py
|   |-- asgi.py
|   `-- wsgi.py
|-- apps/
|   |-- core/              Shared accounts, notifications, and UI utilities
|   |-- faculty/           Faculty workflows and calendar integrations
|   |-- students/          Student browsing and consultation workflows
|   |-- depthead/          Department-head administration and analytics
|   `-- superadmin/        System-wide administration
|-- templates/             Shared components and emails; reserved base.html
|-- static/                Shared css/, js/, and images/
|-- tests/                 Reserved for cross-application tests
|-- docs/                  Project documentation
|-- scripts/               Standalone development utilities
|-- manage.py
|-- requirements.txt
`-- README.md
```

## Application conventions

- Python modules and packages use `snake_case`.
- App-specific templates and static assets remain namespaced by Django application.
- Shared calendar code lives under `static/js/calendar/`.
- Faculty editing code lives under `apps/faculty/static/faculty/js/calendar/`.
- Student read-only calendar code lives under
  `apps/students/static/students/js/calendar/`.
- Faculty domain integrations live under `apps/faculty/services/`.
- Shared notifications live in `templates/components/`; emails retain their
  `emails/` template names. Root `templates/base.html` is an unused placeholder.
- Import application Python code through `apps.<app>`. Django app labels,
  migration dependencies, model references such as `core.User`, and URL
  namespaces such as `faculty:dashboard` retain their original names.
- Existing migrations move with their application; their names and operations
  remain unchanged. Keep app-specific tests inside each app's `tests/` package.

## Settings

`config.settings.base` preserves the original settings values. Development and
production import those values unchanged. Default command and server entry
points select development unless `DJANGO_SETTINGS_MODULE` is already set.
`config.settings.test` retains the isolated SQLite database, local email backend,
fast test password hasher, and disabled Gemini API key.

## Verification

Run checks and the local, isolated test suite with:

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py test --settings=config.settings.test
```

The refactor baseline and post-move suite both discover 101 tests and report
12 failures and 1 error in existing faculty tests. Test fixtures and assertions
were preserved. Django checks pass, no migration changes are detected, and
routes, application labels, model fields/table names, and migration graphs
match the baseline.
