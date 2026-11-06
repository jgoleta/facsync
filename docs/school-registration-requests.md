# School registration requests

School representatives request registration at `/register/school/`, also linked from
the registration page. They verify a Google account with a verified `.edu.ph`
email, then provide their school's name, code, educational levels, representative
details and an official school contact email on the same domain. The domain comes
from Google verification and cannot be supplied by the form.

Pending requests create no school, User or SocialAccount, grant no school access,
and do not reserve the domain. Another representative can request the same domain.
Existing FacSync accounts cannot use this flow to change their role or school.
The applicant can verify the same Google account again to check their own status.
Verification lasts one hour; its Google-start intent expires after 15 minutes.

## Manual review

The existing administration account opens **FacSync Administration → School
Requests** (`/systemadmin/requests/`). Review opens in a modal, with a full-page
route available at `/systemadmin/requests/<request UUID>/`. Filters show pending,
approved, rejected or all requests. The visible administration name changed;
the existing internal `systemadmin` role, permissions and URL namespace remain.
No additional role or reviewer account is created.

The reviewer must independently find an official school contact, confirm the
representative's authority and record private verification notes before approval.
A school email or the applicant's suggested contact alone is not proof of authority.
The application cannot perform that human verification automatically.

Approval creates the school, its single domain and the first Super Admin invitation
in one transaction. It rechecks email, school code and domain availability. If
another request has already claimed them, approval fails without a partial school.
The representative then uses normal Google sign-in with the invited email; the
existing invite activation flow creates the Super Admin account for that school.
Repeated decisions do not create duplicate schools, invitations or emails.

Rejection requires a reason shared with the applicant. Private verification notes
stay in the administration review. A rejected applicant can submit a corrected
request; previous decisions remain recorded. Submission has a one-minute cooldown
and only one pending request per verified identity/email.

## Email and settings

Submission emails a receipt to the applicant and alerts active, schoolless
administration accounts with email addresses. Approval reuses the existing Super
Admin invitation email; rejection emails the shared reason. Templates extend the
existing email layout and escape submitted content. Links use `SITE_URL`.

Emails are sent synchronously after saving. Requests may wait for the existing
email backend, but a delivery failure never undoes submission or approval/rejection.
Failures are logged using the request reference and exception category. Applicants
can still check their status; an approved invitation can be resent from the existing
Super Admin management page. No worker, new Google scopes, callback URL or email
provider settings are introduced.

## Migration and deployment

`core.0032_school_registration_request` adds the request model, constraints and
index. It does not alter existing users, roles or school records. Production must
receive that migration during the coordinated rollout before the new pages are
used. The implementation has not been committed, pushed or deployed by this work.

The migration was applied only to the guarded, separate rehearsal database. All
records in 29 existing application tables were preserved. A synthetic submission,
approval and repeated approval passed inside a rollback-only transaction, leaving
no synthetic request or school. No rehearsal emails were sent.

## Verification

- 20 focused server tests passed: Google identity validation, privacy, role
  restrictions, atomic decisions, first-login invite activation, escaped content,
  duplicate protection and email-failure persistence.
- One migration test passed, preserving existing records from migration 0031.
- Three browser checks passed: public submission/status, review modal/approval,
  processing protection and mobile layout. Browser identities are test fixtures;
  there is no application verification bypass.
- Django checks, migration drift checks, JavaScript syntax checks and Git whitespace
  checks passed.
- Full suite: 344 tests, 205 failures, 105 errors and 7 skips. The fresh baseline had
  320 tests, 205 failures, 105 errors and 4 skips. Comparing exact failing/error test
  names found no additions or removals. The three new browser checks were skipped
  in the full suite and passed separately.

Local reports and screenshots are in ignored `.staging-backups/` files prefixed
`school-request`, including the rehearsal preservation report. The full suite is
not green; its existing failures remain. Live Google verification and real inbox
delivery still require a manual check with an eligible institutional account after
deployment.
