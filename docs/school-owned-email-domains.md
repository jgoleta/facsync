# School-owned email domains

Student and school-request registration accepts a valid school-owned email domain
instead of requiring `.edu.ph`. Google Sign-In remains required, including the
existing verified-Google-email checks. No additional email link, code, mailbox
verification page or Google Workspace-only restriction was added.

New school requests still require manual verification of the school and the
representative's authority. Domain validation does not prove school ownership.
Approval automatically creates the school, its exact domain and first Super Admin
invitation through the existing flow.

## Domain rules

- One exact domain per school, and one school per domain.
- Exact matching only: registering `school.org` does not register
  `students.school.org` or the reverse.
- Known personal/shared email providers and their subdomains cannot be assigned
  to schools. The explicit list is maintained in `apps/core/school_domains.py`.
  It is a supporting control, not an exhaustive list or proof of school ownership.
- URLs, wildcards, IP addresses, malformed names, unknown suffixes and bare public
  suffixes such as `co.uk` are rejected.
- The pinned `tldextract` dependency uses its bundled public-suffix snapshot with
  networking and disk caching disabled. Updating the dependency updates that
  snapshot; registration does not make DNS or HTTP checks.

The same server policy covers registration, approval, school settings and FacSync
Administration. Frontend validation checks basic syntax and the single-domain
requirement; the server performs the provider and suffix checks.

## Domain replacements

The school's active Super Admin can replace its domain automatically, with a
confirmation explaining the consequences. The existing domain row is updated
in place and the existing audit log records the actor, old domain and new domain.
FacSync Administration also supports an in-place replacement.

New students using the old domain can no longer register under that school.
Existing accounts keep their school and normal sign-in access, subject to account
and school status. Names can be edited without a domain-change confirmation.
Domain assignment, school suspension and student signup retain the existing
locking and recheck behavior. Invitation eligibility and notification delivery
are unchanged.

## Migration and rollout

`core.0033_school_owned_domains` removes the `.edu.ph` database constraint and adds
the one-domain-per-school constraint. Lowercase enforcement and case-insensitive
global domain uniqueness remain. The migration first refuses to run if a school
has multiple domains; it never chooses or deletes domains automatically.

The migration passed locally and on the separately guarded rehearsal database.
All records in 30 existing application tables were preserved. A domain replacement
and school lookup passed in a rollback-only transaction; no temporary changes or
emails remained. Production has not been migrated by this work.

Before production rollout, take a fresh backup and coordinate applying migration
0033 with deploying the code and updated dependency files. Pause domain edits
during that short rollout: the old administration form adds a new row before
removing the old row, which is incompatible with the new uniqueness constraint.
Do not simply reverse the migration after custom domains are registered: the old
suffix constraint cannot accept those domains. Use the backup/coordinated recovery
plan rather than deleting school/domain records to force a reversal.

Verification reports are in ignored `.staging-backups/` files prefixed
`school-domain`. The 15 focused checks cover validation, registration/approval,
domain replacement, audit history, existing-user preservation, permissions and
migration preservation/preflight.
Two additional browser checks passed for administration creation, domain-change
confirmation/cancellation, provider rejection and mobile layout.
The existing 320-test suite still has 205
failures and 105 errors; comparing the exact failure/error names before and after
found no additions or removals. This does not mean the full suite is green.

Live Google sign-in with the intended custom-domain account still needs a manual
check after rollout. Existing Google verification alone is deliberately retained;
no claim of current mailbox ownership beyond that existing mechanism is made.
