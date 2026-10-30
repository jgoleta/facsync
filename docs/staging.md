# Local staging with Supabase

Use a Supabase project different from production. An existing project's tables
must stay separate from FacSync. Copy `.env.staging.example` to `.env.staging`
and initially enter that project's admin database credentials locally. The
latter file is ignored by Git. Use the direct or session connection on port 5432.

The provisioning script defaults to a read-only preflight. Its explicit `--apply`
mode creates only a new `facsync_staging` schema and `facsync_staging_login` role,
checks that existing application tables are inaccessible and other schemas are
not writable, then replaces the user/password in `.env.staging` with randomly
generated restricted credentials. It does not run migrations. It refuses to
reuse existing schema/role names or change grants on existing schemas/tables.

```powershell
.\venv\Scripts\python.exe scripts/setup_staging_schema.py
# Only after authorization to create the new schema/login:
.\venv\Scripts\python.exe scripts/setup_staging_schema.py --apply
```

If PUBLIC grants would expose existing tables or permit creation outside staging,
provisioning rolls back. Use a dedicated project instead of changing another
application's grants. If credential-file saving or the post-creation connection
check fails, inspect the provisioning state before retrying; it deliberately
refuses to overwrite existing objects. The project admin remains available
through Supabase independently of the new restricted credentials.

Always select `--settings=config.settings.staging` explicitly. The default
development and production configurations are unchanged. Staging reads database
credentials only from `.env.staging`; it refuses missing values, unsupported
connection hosts, and a project matching the main database or Storage URL.
It requires the restricted login and the explicit `STAGING_DB_SCHEMA` value.
The connection search path contains only `facsync_staging`, so it cannot fall
back to another application's tables or Django migration history. The login
can create tables in that schema; the provisioning administrator owns the schema.

Run local configuration checks without applying migrations:

```powershell
.\venv\Scripts\python.exe manage.py check --settings=config.settings.staging
```

After separately authorizing and applying migrations to the testing database,
start the local staging server (including development static-file serving):

```powershell
.\venv\Scripts\python.exe manage.py runserver --insecure --settings=config.settings.staging
```

This configuration is local-only, with debug disabled and separate session/CSRF
cookie names. It uses console email and disables Gemini, scheduled status emails,
and photo storage. Google login credentials are inherited from the main local
configuration and are wired into allauth without copying production SocialApp
records. Configure the authorized callback
`http://127.0.0.1:8000/accounts/google/login/callback/` before testing login.
Google Calendar remains a real external integration if explicitly connected:
use dedicated test Google accounts/calendars, never production faculty accounts.

Do not run the automatic test suite against this persistent staging database.
Use `--settings=config.settings.test` for the isolated SQLite suite; use a
separate disposable local PostgreSQL database for PostgreSQL migration rehearsals.
Staging starts without FacSync tables until migrations are explicitly applied.

## Synthetic migration sample

Once existing migrations are applied, preview the fixed `staging-adnu-v1` batch:

```powershell
.\venv\Scripts\python.exe manage.py seed_staging_data --settings=config.settings.staging
# Create only after authorization:
.\venv\Scripts\python.exe manage.py seed_staging_data --apply --settings=config.settings.staging
```

The sample includes two Super Admins, two College Heads, four faculty and eight
students, with mixed account statuses, legacy college-code casing and an
unfinished student profile. It includes consultations in every status, schedules,
status histories, walk-ins, pending/used invitations, audience-specific/expired
announcements, open/closed colleges, subscriptions, notifications and a synthetic
stale AI-insight record. It preserves the seven existing seeded colleges.

Accounts use `demo-staging-adnu-v1-` usernames and `example.invalid` email
addresses, unusable passwords and no social/calendar connections. They cannot
log in. Interactive testing will require a separately configured test identity;
these records are for migration rehearsal and data-scope verification.

Creation is atomic and refuses duplicates or conflicting existing records. The
ownership manifest records exact IDs and fingerprints. Preview removal with:

```powershell
.\venv\Scripts\python.exe manage.py seed_staging_data --undo --settings=config.settings.staging
# Remove only after authorization:
.\venv\Scripts\python.exe manage.py seed_staging_data --undo --apply --settings=config.settings.staging
```

Undo refuses changed records and dependencies outside the batch. After model
changes or a school backfill, fingerprints may differ; review the manifest and
migration state instead of forcing deletion. Neither command runs migrations or
sends notifications/emails through integrations.

The approved School foundation is now applied to this staging schema; see
`multi-school-foundation.md` for the migration, backup and rollback evidence.
Its data migration preserves valid sample fingerprints across the backfill.

The System Admin area and its staging setup instructions are documented in
[system-admin.md](system-admin.md). Its bootstrap command creates a separate
interactive operator; synthetic seed accounts remain unchanged.

[Student registration](student-registration.md) now resolves verified Google
identities against the domains assigned through that area. It needs no new
database migration. Use a fresh institutional Google identity for browser testing.
