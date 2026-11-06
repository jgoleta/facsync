# Department foundation — stage 1

This stage adds data structures and an explicit ADNU backfill. It does not switch
HTTP permissions, page labels, invitation activation, analytics, or student
profiles to departments. School registration and System Admin remain unchanged.
Do not treat this stage alone as a production-ready restructuring release.

## Data structures

- Department belongs to one school and optionally a college in that school.
  Code and name are unique per school without case sensitivity. Its school/code
  cannot be changed after creation. Names and same-school college grouping can
  change while retaining identity.
- User.department is an optional academic-home link. FacultyProfile retains its
  existing identifier and college text. Heads use managed_departments through
  DepartmentHeadAssignment, supporting multiple departments and multiple heads.
- Head invitations have department assignments; faculty invitations,
  announcements and closures have optional department links.
- Consultations and walk-ins have nullable historical department references.
  Backfill follows the faculty's department, not the student's academic home.
  Office records keep a null academic department.
- Runtime model writes and bulk inserts validate related schools; assignments
  require the existing depthead role. Direct queryset department updates are
  refused in favor of validated saves. These links do not yet grant HTTP access.

## Migrations

1. core.0026_department_foundation adds the core schema.
2. faculty.0034_department_foundation adds consultation/walk-in references.
3. core.0027_attach_adnu_departments validates legacy data, then fills links.

Only the explicit ADNU mappings below are authorized. They are initial migration
labels, not assertions about the actual membership of every academic program.

| Existing code | Department code | Department name |
| --- | --- | --- |
| CBA | DA | Department of Accountancy |
| CCS | DCS | Department of Computer Science |
| CED | DEE | Department of Elementary Education |
| CHSS | DMS | Department of Media Studies |
| CON | DN | Department of Nursing |
| CSEA | DCE | Department of Civil Engineering |
| COL | DL | Department of Law |

The migration preserves legacy text, account roles/titles, stable identifiers,
calendar connections/events/Meet links, saved AI content, and consultation status.
Department descriptions and CSV templates start with the existing college values.
Unchanged demo-owned records receive updated fingerprints; modified records are
not re-signed. Old AI caches are preserved for the later reporting transition.

All references are checked before writing. Unknown/ambiguous unit codes,
User/FacultyProfile disagreements, cross-school consultation participants, or
academic records requiring an unapproved school mapping stop the backfill.
Blank incomplete student profiles remain unassigned. No college is invented for
a department, and no office is converted into a department.

## Database and rollback boundary

Development verification uses config.settings.test with in-memory SQLite,
synthetic configuration, email in memory, and external network access blocked.
No staging, rehearsal, or production connection is needed for these checks.

The backfill can reverse only while its mapping remains representable by the
preserved old fields. Extra departments, changed definitions, different member
or historical links, and multi-department head assignments refuse reversal
before writes. Never force such a rollback with --fake. Use a reviewed forward
repair or a verified backup instead.

Before a later production rollout, take a fresh backup, rehearse against a
disposable restored copy, check counts/assignments and the full suite by failing
test names, and deploy the complete permission/UI transition together. Stage 2
now reports protected college deletion as an error rather than removing a college
that still groups departments.

## Next stages

Stage 2 adds Super Admin management and invitation activation. Stage 3 adds
department access, combined reporting/AI cache scopes and new-record historical
references; see `department-reporting.md`. Stage 4 implements educational levels,
student profiles and announcement audiences; see `student-education.md`.
The PostgreSQL rehearsal remains before rollout. Historical transfers stay
blocked until their separate rules are implemented; school registration is on hold.

## Local verification (2026-11-06)

- All 21 new model/migration tests passed in the full run.
- Baseline: 316 tests, 205 failures, 105 errors.
- With the foundation: 337 tests, 205 failures, 105 errors. Comparing failure
  and error names (including subtests) found no added or resolved failures/errors.
- `makemigrations --check --dry-run` found no missing model changes.
- Verification used disposable in-memory SQLite only. No external database,
  provider email, Google Calendar, or Gemini call was made. PostgreSQL rehearsal
  against a restored copy remains a later release check.
