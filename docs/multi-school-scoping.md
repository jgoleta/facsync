# School scoping and authorization

This phase adds school isolation to the existing application. The School/ADNU
foundation is described in [multi-school-foundation.md](multi-school-foundation.md).
System Admin screens, the bootstrap command and Super Admin invites were added
in the [next phase](system-admin.md). [Student domain registration](student-registration.md)
is now implemented using explicitly assigned domains. The public
dashboard remains in place with an interim login and school restriction.

## Request boundary and writes

`SchoolScopeMiddleware`, immediately after authentication, derives the school
from the authenticated user. Query parameters, submitted fields and cookies
cannot select another school. Inactive accounts, schoolless school-role accounts
and suspended schools receive HTTP 403, including existing sessions. A suspended
user sees: “Your school’s access to FacSync has been suspended. Please contact
your school’s Super Admin.” The OAuth adapter checks this before accepting login.
Login/logout routes remain available. Authenticated responses use private,
no-store caching.

Only an active schoolless `systemadmin` can enter the all-school context or Django
administration; Django's staff and model permission checks still apply there.
School Super Admins retain their own-school role. The reserved System Admin role
has not been exposed in existing role editors or promoted from an existing account.

Shared managers filter school-owned models using a request-local ContextVar.
Participant records (consultations, walk-ins, subscriptions and queued emails)
must match on both participants' schools. Model saves and bulk operations validate
ownership; existing persisted ownership is checked before a save to stop forged
IDs from reassigning another school's records. Direct ownership updates are
blocked inside a school request. Direct-school forms set ownership from the
server before validation and ignore submitted school values.

The school columns remain nullable for compatibility with the staged migration.
Missing-school accounts fail closed at HTTP access and signup persistence. This
is application isolation, not PostgreSQL row-level security: raw SQL, base
managers and trusted offline code must be reviewed explicitly.

## Covered paths

| Area | Isolation and authorization |
| --- | --- |
| Super Admin | Colleges, heads, faculty, students, statistics, invites and edit/deactivate/remove actions use the current school. Both student-management endpoints additionally require the Super Admin role. Role edits cannot grant privileged roles. |
| College Head | Dashboard, faculty monitoring, behavior, peak/trend analytics, closures, announcements, schedules and aliases filter by school as well as college. Guessed foreign IDs return 404. |
| Student | Directory, availability, schedules, booking, cancellation/deletion, walk-ins, subscriptions and profile college choices use the student's school. |
| Faculty | Schedule/event APIs, booking management, consultation chatbot, walk-ins, status/history, private photos and calendar connection records use the faculty's school. |
| Analytics/chatbots | Analytics, student availability and faculty consultation browser entry points require an active school context, or explicit `school=` outside a request. A school request cannot switch context. Calculations and existing response shapes are preserved. |
| AI insights | Read, stale fallback, refresh and upsert use school plus college. School code enters the sanitized generation context and hash. A missing local cache cannot fall back to another school's cache. |
| Notifications/email | Notifications, announcement recipients, status subscriptions, schedule-upload recipients and queued delivery eligibility validate school ownership. Transport, templates and batching remain unchanged. |
| Invites/OAuth | Faculty and College Head invites inherit the sender's school; login assigns that school, rechecks activation and consumes the invite only after successful account persistence in a transaction. |
| Public dashboard | Anonymous access redirects to login. Authenticated data is scoped to the user's school and responses cannot be shared-cached. Removal remains a separate task. |

Email invitation identity checks deliberately use the global base manager to
prevent duplicate identities across schools; the form reports only a generic
unavailable-email error. The global faculty identifier check likewise discloses
no owner or school. College codes can collide between schools.

## Background and maintenance boundary

Outside requests, managers permit trusted global maintenance. Analytics and
other college-based service entry points still require an explicit active school.
Profiling commands now select school along with college; demo seeding requires
an explicit school. Staging samples also inherit their explicitly selected school.

The bearer-authenticated status scheduler intentionally runs across active schools
even if its request carries a user session. Calendar sync eligibility requires an
active school; calendar synchronization itself is unchanged. Queued emails recheck
school equality and activation when claimed. Legacy corrupt deliveries are
cancelled through the base manager using state-only writes, so invalid ownership
does not prevent cancellation. New cross-school participant records are rejected.

## Verification and staging evidence

All 22 new tests in `apps/core/tests/test_school_isolation.py` pass. They create
ADNU and UNC with the same CCS code and cover each school role, guessed URLs/IDs,
management authorization, forged school fields, read/write isolation, all three
chatbots, AI cache/refresh behavior, recipients, invite activation/failure, profile
choices, suspension, private photos, administration and public-dashboard access.

The complete suite ran 347 tests with 39 failures and nine errors. All 48 failing
occurrences exactly match the preceding 325-test run by test name, subtest and
outcome. The suite is still failing overall. See
[scope-phase.md](test-baselines/scope-phase.md) and its JSON, and the linked
historical name-by-name comparison against the original 21-failure/3-error run.

Staging-only verification used `scripts/verify_school_scoping_staging.py` with
`config.settings.staging`. It verified the restricted role and schema, backed up
all staging model records and migration history into the ignored
`.staging-backups/before-scope-v1/`, then applied only
`core.0022_alter_user_managers` (Django manager metadata; no table/column changes).

A temporary UNC school, operator and four school roles exercised real PostgreSQL
HTTP access, guessed foreign IDs, same-college analytics/AI, and suspension. The
entire test transaction rolled back, including sessions and login timestamps.
The final state remains one school, 16 users, seven colleges, zero domains and a
valid 71-record sample manifest. Other schemas' relation IDs, owners and grants
matched the pre-run inventory. Production was not accessed.

## Rollback and remaining rollout

Stop staging writes before reverting this phase. The manager migration can be
reversed to `core.0021_attach_existing_to_adnu` using the explicit staging settings;
deploy the matching previous application revision as part of that rollback. No
business-data rewrite is required for this metadata migration. Preserve the new
backup; restore to a fresh isolated schema if a data restore becomes necessary.
The separate School foundation rollback guards still apply and must not be
bypassed after additional schools or domains have been onboarded.

System Admin screens/bootstrap and Super Admin invites are now implemented; see
[system-admin.md](system-admin.md). Student domain registration is also implemented;
see [student-registration.md](student-registration.md). New students require a
verified institutional identity on a domain explicitly assigned to an active
school. No domain is automatically assigned, and existing users retain their
school. Production rollout and the existing failing test baseline still need
separate review before onboarding real institutions.
