# System Admin area

The new `/systemadmin/` area has two tabs and reuses the Super Admin layout.
New CSS uses existing theme variables only. It is restricted to active,
schoolless users whose FacSync role is `systemadmin`. Post-login redirects send
them here without student or faculty profile setup. School Super Admins cannot
enter this area or promote themselves through their existing role editor.

## Manage Schools

- Add a name, unique school code and one or more institutional email domains.
- Domains normalize to lowercase, must end in `.edu.ph`, and are unique across
  schools. Enter one per line; commas and semicolons are accepted too.
- The school code is locked after creation, including against forged form data.
- Edit names and domain assignments; the edit screen shows recent audit history
  with actor, timestamp, field and previous/new values. Replacing the last domain
  is atomic and never leaves the school without its required domain.
- Suspend or reactivate. Suspension preserves records and blocks existing
  sessions as well as new logins for school users. Reactivation restores access
  for accounts that are individually active.

The existing ADNU bootstrap remains domain-free until a System Admin assigns
its domains. No domain is seeded or inferred. When configuring ADNU, use
`adnu.edu.ph` as instructed, not `gbox.adnu.edu.ph`. School creation no longer
requires database administration; it requires this System Admin role.

## Manage Super Admins

Invite an unused Google sign-in email to an active school. The institutional
domain rule does **not** apply to Super Admin invitations. The normal FacSync
email transport sends a school-specific activation email linking to login.
If delivery fails, the invitation stays saved with a retry message and a Resend
email action. Staging uses console email; no external invitation is delivered.

Pending invitations can be edited, deactivated, reactivated or resent. Their
school/email may be corrected before activation. First login requires a verified
Google email matching the live invitation. Signup persistence locks and rechecks
school activation and the invitation; account creation, Google association and
invite consumption are atomic. Cancelled, used or suspended-school invitations
cannot activate, including after a delayed allauth signup/session round trip.
The activated account has role `superadmin`, the invited school, no college
assignment and a completed profile. Student domain checks do not apply to these
invitations; the separate [student registration flow](student-registration.md)
now handles institutional self-registration.

Activated accounts can have their names edited and access deactivated/reactivated.
Email and school remain fixed to preserve Google identity and ownership of
existing records. Use a new invitation for a different school. The last active
Super Admin in a school cannot be deactivated; activate a replacement first.
An active school is required before reactivating its accounts or invitations.

## First System Admin and account conversion

No migration promotes a user, and no production account was changed. The
management command is preview-first and requires an exact email. It never grants
Django staff/superuser permissions. Existing Google associations and passwords
are preserved on conversion. New accounts have unusable passwords and connect
only on their first verified Google login using the exact bootstrap email.

For interactive **staging** checks, create a separate operator with the Google
email you control. These commands explicitly target the isolated staging project:

```powershell
# Preview only; replace the example address with your Google sign-in email.
.\venv\Scripts\python.exe manage.py create_systemadmin --email "your-google-email@gmail.com" --settings=config.settings.staging
# Save that reviewed staging account.
.\venv\Scripts\python.exe manage.py create_systemadmin --email "your-google-email@gmail.com" --apply --settings=config.settings.staging
.\venv\Scripts\python.exe manage.py runserver --insecure --settings=config.settings.staging
```

Sign in normally with Google, then visit `/systemadmin/`. The existing staging
seed accounts use `example.invalid` and cannot sign in. A real Google OAuth
application must allow the local callback, as with the existing staging login.
No production email, password or storage credentials are needed for these pages.

Use `http://127.0.0.1:8000/login/` consistently. In the Google OAuth client's
authorized redirect URIs, include
`http://127.0.0.1:8000/accounts/google/login/callback/`. Staging configures allauth
from the existing local `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`; it does
not require copying a production SocialApp record. If you choose `localhost`
instead, that hostname needs its own matching Google redirect URI.

The `--insecure` flag serves local CSS/JS with staging's `DEBUG=False`. It does
not change the database or enable debug. Stop the previous server with Ctrl+C,
restart using the command above, and hard-refresh the browser if styles are
missing. It is a local development-server flag, not a production deployment
setting. Running the bootstrap command again is unnecessary once it reports
that the account already exists as a schoolless System Admin. These accounts
sign in with Google, not a Django-admin username/password.

For the later **production** conversion, review the deployment and backup first.
Use the same command with `--convert-existing`, the exact existing account email,
and explicitly reviewed production settings; preview before `--apply`. Do not
copy a staging command and remove its settings flag casually. The command refuses
ambiguous emails, inactive/non-Super-Admin accounts, or a conversion that would
leave ADNU without another active Super Admin. It clears school, college and
title on the converted user, preserving the replacement's school/role.

Django admin is restricted to System Admins in this version, so it cannot bootstrap
the first one through a school Super Admin login. After bootstrap, an operator
who already has Django user-management permissions can edit role choices there;
the change form clears school/college for System Admins and guards removal of a
school's last active Super Admin. The dedicated management area does not depend
on Django superuser privileges.

## Migration, verification and rollback

`core.0023_alter_user_role_superadmininvite` adds the role choice and a
`SuperAdminInvite` table with school/sender links, case-insensitive unique email,
active and used states. It does not alter existing account roles or assign domains.

The local suite covers both tabs, school creation/edit/domain validation/audits,
CSRF and role checks on every endpoint, account edits and access changes, last
Super Admin preservation, invitation email/retry/collision handling, real allauth
activation, signup serialization, suspension/revocation rechecks, and bootstrap
creation/conversion. See [systemadmin-phase.md](test-baselines/systemadmin-phase.md)
for the full-suite comparison by failing test and subtest name.

`scripts/verify_systemadmin_staging.py` is fixed to the separate staging settings,
role and schema. It backs up the staging model data and migration history to the
ignored `.staging-backups/before-systemadmin-v1/`, permits only migration 0023,
and uses a rollback-contained temporary operator, school and invite for real
PostgreSQL page, email, activation and authorization checks. HTTP integrations
are blocked and emails stay in memory during the rehearsal. No durable operator
is provisioned by this script.

The rehearsal passed on staging PostgreSQL and migration 0023 is applied there.
All temporary records rolled back: staging retains one ADNU school, 16 synthetic
users, seven colleges, no domains, no System Admin account and no Super Admin
invitations. All 71 sample fingerprints and the unrelated schemas' relation IDs,
owners and grants matched the pre-run inventory. Production was not accessed.
The full local suite ran 369 tests with the same 39 failures and nine errors as
the previous phase; all 22 new System Admin tests passed.

Before reverting this phase, stop writes and back up invitation data. Returning
core to `0022_alter_user_managers` removes the invitation table and its contents;
deploy matching earlier code only after reviewing how to handle any already
activated System Admin accounts. Account conversion is not automatically reversed
by schema rollback. Restore backups to a fresh isolated schema if needed; never
reset the shared Supabase database or its other schemas.
