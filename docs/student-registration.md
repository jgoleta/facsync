# Student registration by school domain

Students choose Register as Student and continue with Google. New registration
requires a verified Google identity. The adapter normalizes its email domain to
lowercase and matches it exactly against System Admin-managed school domains.
The school is assigned by the server, not selected by the student.

| Condition | Result |
| --- | --- |
| Email does not end in an institutional `.edu.ph` domain | `FacSync supports .edu.ph institutional accounts only` |
| Institutional domain is not assigned to a school | `Your institution is not yet registered with FacSync` |
| Assigned school is suspended | School-suspension message; no account created |
| Google email is missing or unverified, or provider is not Google | Verified-Google-account message; no account created |
| Assigned school is active | Active student account linked to that school; continue to profile setup |

There is no suffix-based institution lookup. `student@adnu.edu.ph` matches an
explicit `adnu.edu.ph` assignment; `student@gbox.adnu.edu.ph` requires a separate
`gbox.adnu.edu.ph` assignment. Other domains ending in `.edu.ph` do not inherit
access from a similar institution name or parent domain. Each school can have
multiple explicitly assigned domains.

The profile displays the assigned school and offers only its colleges. A forged
school/role submission cannot change ownership; a college found only in another
school is rejected with a visible form error. Shared college codes, such as CCS,
resolve inside the student's school. The existing profile fields and active
student status are preserved; no new approval step is introduced.

## Save-time checks and existing accounts

The adapter checks the domain at the Google callback and rechecks before account
persistence. Saving locks the school, serializing against its domain edits and
suspension. A removed domain or suspended school blocks signup. If a domain is
reassigned to another school during a delayed signup, the student must restart
rather than silently changing schools. Allauth's serialized signup retains the
initial school assignment, and the server validates it against the current domain.

Student creation, Google association and verified-email records are transactional.
A persistence failure rolls back the new records. An existing account with the
same email is not recreated or reassigned. Signup cannot grant staff, superuser
or administrator roles. The saved identity must match the verified Google email.

Existing students keep their stored school when signing in after a domain edit;
the domain rule applies to new registrations. Existing school/account suspension
checks still apply. Faculty, College Head and Super Admin invitations are handled
before student registration checks, including invitations to Gmail addresses.
No Google Calendar, email transport or analytics calculation changes were made.

## Try it in staging

Use the staging server and keep using the same host throughout:

```powershell
.\venv\Scripts\python.exe manage.py runserver --insecure --settings=config.settings.staging
```

1. In the System Admin area, verify that ADNU has the explicitly assigned
   `adnu.edu.ph` domain. Registration does not seed or edit it.
2. In a separate browser profile, open `http://127.0.0.1:8000/register/`, choose
   Student, and sign in with a **new** Google account using that exact domain.
3. Confirm the profile displays ADNU and only ADNU colleges. Complete the profile
   and verify the student dashboard opens.
4. With a new, uninvited Gmail identity, try student registration and confirm the
   institutional-only message. An existing Gmail-based administrator logs in
   through its normal account/invitation flow instead.
5. With a new Google identity on an unassigned `.edu.ph` domain, confirm the
   institution-not-registered message. Do not remove a real assigned domain just
   to manufacture this check; automated tests cover it with disposable fixtures.
6. For suspension testing, use a disposable test school and its own domain; verify
   both registration and existing school-user access are blocked while suspended.

Real Google accounts are required for browser OAuth testing. The synthetic seed
accounts cannot authenticate. Invitations and existing accounts take precedence,
so use fresh, uninvited identities when testing student-registration rejection.

## Verification and rollout

No model changes or migrations are needed: registration uses the existing User
school link and audited SchoolDomain assignments. The two preexisting photo and
registration test fixtures now use verified, assigned institutional identities;
their original photo/status assertions remain intact.

The new `test_student_domains.py` tests cover exact messages, uppercase/multiple
domains, subdomain and lookalike rejection, schoolless/missing-domain registration,
verified identity, suspension/removal/reassignment during signup, delayed signup,
identity substitution, transaction rollback, duplicate accounts, existing login,
profile isolation and all three invitation roles. Full-suite failure identities
are compared against the preceding phase and the original historical baseline
in [student-registration-phase.md](test-baselines/student-registration-phase.md).

`scripts/verify_student_registration_staging.py` uses only the separate staging
settings, restricted role and schema. It requires the assigned active ADNU domain
and no pending migrations. All temporary students, Google associations, sessions,
school/domain/college fixtures and profile updates occur inside one rolled-back
transaction. HTTP integration calls are forbidden and emails stay in memory. It
compares all staging model records by hash and unrelated schema metadata before
and after; it never runs migrations or assigns ADNU a domain.

The PostgreSQL rehearsal passed using the active `adnu.edu.ph` assignment already
made through the System Admin area. Existing staging model records matched their
pre-run hash after rollback; unrelated relation IDs, owners and grants also
matched. No production connection was used. All 22 new tests passed, and the
391-test full local suite retained the exact same 39 failures and nine errors as
the preceding 369-test baseline, including subtest parameters and outcomes.

For a rollback, deploy the matching previous application code; there is no schema
migration to reverse. Existing student records should retain their assigned
schools. The previous version blocks new uninvited student signup, so account for
that behavior before rolling back. Production deployment and migration rehearsal
remain separate work requiring review and a production backup.
