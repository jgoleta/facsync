# Student profiles and educational levels — stage 4

## Super Admin configuration

School Settings in the Super Admin sidebar now offers Elementary, Junior High
School, Senior High School and College checkboxes. Multiple levels are allowed;
at least one must remain. Existing schools, and new schools created through the
current System Admin flow, default to College. Public school registration remains
on hold; a later registration form can collect the same choices.

Only the active Super Admin of that school can use this settings page. It cannot
edit another school or change names/domains through submitted extra fields.
Changes record the actor, timestamp and old/new choices in SchoolChangeLog.
Removing a level used by any student, including an inactive student, is blocked.
The existing System Admin school-save path observes the same removal guard.

## Student flow

1. Existing verified Google/.edu.ph/domain matching chooses the active school.
2. A new student starts with an incomplete profile and no selected level or
   department. Signup cannot pre-complete these fields.
3. Profile setup asks for Student ID, educational level and grade/year. It shows
   only the school's offered levels; a single offered level is automatic.
4. College students must choose an active department in their own school. Its
   college label is derived, including support for departments with no college.
   Elementary/JHS/SHS students do not choose a department or college.
5. Saving opens the student home page. My Profile shows the level, grade/year,
   Student ID and academic labels, with a link to update student details.

| Level | Choices |
| --- | --- |
| Elementary | Grades 1–6 |
| Junior High School | Grades 7–10 |
| Senior High School | Grades 11–12 |
| College | Years 1–6 |

These are the application's supported choices; no kindergarten or postgraduate
category is added. Changing level resets the visible grade/year choice. Server
validation checks the same ranges, offered levels, Student ID length/required
value, department school and active status. Submitted role/school/college values
cannot override the server's assignments. Moving to basic education clears old
college/department values. Student home changes do not move consultations:
historical department references continue to follow the faculty member.

The form retains errors and entered values, uses escaped text/JSON for labels,
and disables repeated submissions with a saving indicator. The student directory
now displays departments as primary labels and colleges as secondary labels.
Existing internal JSON/DOM field names such as `college` remain for compatibility.
Students continue to browse and book faculty across departments within their
school. Educational level does not impose a new booking restriction.

## Student announcements

Department Settings adds explicit offered-level checkboxes for announcements
whose audience includes students. Faculty-only posts need no student levels.

- Faculty recipients remain limited to the selected department.
- College-student recipients must match both the selected level and department.
- Elementary/JHS/SHS recipients match the selected level within the same school;
  they do not need a home department.

Notifications, student home/directory feeds, the announcement API and the
student chatbot use that same recipient policy. Expiry/audience checks remain.
Faculty email delivery/layout and the existing Office Admin management flow
remain on their existing paths. No student announcement email is added.

Basic-education availability answers can include the school's departments and
offices. Closing one department does not suppress available faculty elsewhere;
closed departments/offices are excluded from the current-availability answer.
Head reporting continues to use only its explicitly assigned departments and
has no department filter.

## Migration and rollback

- `core.0030_educational_levels` adds school offered levels, student level,
  announcement target levels, a two-character grade/year field, and the audit
  field choice. Existing announcement targets default to College.
- `core.0031_classify_existing_students` classifies all legacy student accounts
  as College, preserving their IDs, roles, Student IDs, years, completion flags
  and department links from the earlier ADNU backfill. Staff roles are unchanged.
- Completed profiles missing a department or valid college year stop migration
  before classification. Invalid years on incomplete profiles also stop it.
  Already changed level configuration stops classification rather than overwriting
  newly entered basic-education data. Resolve such cases on the disposable copy
  before planning any production repair.
- Unmodified demo-owned User fingerprints follow the schema change; edited
  records are not re-signed.
- Reverse migration checks that school choices, student profiles and audit
  history fit the previous schema. Basic-education records, later college years,
  or educational-level audit entries can block reversal. Do not force rollback
  with `--fake`; use a reviewed forward repair or a verified backup.

All migration checks used disposable in-memory SQLite. No Supabase database,
credentials file, deployment, remote branch or production account was changed.
PostgreSQL behavior, actual existing data and live OAuth/email remain for the
production-copy rehearsal. Do not deploy before that rehearsal and rollout review.

## Local verification — 2026-11-06

- Fifteen new profile/configuration/recipient tests pass, including mocked Google
  signup for a JHS-only school, invalid inputs, guessed foreign/inactive IDs,
  role restrictions, audit/removal safeguards, escaped display, notifications,
  feeds/chatbot matching and availability across departments/offices.
- Four migration tests pass: classification/preservation, refusal for invalid
  completed profiles, guarded reversal and demo fingerprint preservation.
- Three new Chromium checks pass: changing levels/grade options and completing
  a JHS profile, automatic single-level selection/mobile layout, and saving
  Super Admin level settings. The two earlier head-page browser checks also pass.
- The existing 56-test department regression group passed. A later focused run
  covering education, migration and head access passed all 34 tests; the extra
  Google signup scenario passed in the final 15-test education run.
- Full-suite baseline: 378 tests, 205 failures, 105 errors, six browser skips.
  Final run: 400 tests, 205 failures, 105 errors, nine browser skips. Exact failing
  and error names, including subtests, are unchanged. Browser checks were enabled
  and passed separately. The full suite still has existing failures and is not
  being described as green.
- `makemigrations --check --dry-run`, Django checks and `git diff --check` pass.
  Tests use synthetic settings, in-memory email/mocks and blocked external
  networking. Browser sessions use a local disposable test server.

Detailed local reports are in ignored `.staging-backups/education-*.json` and
matching logs. The next step is to back up and rehearse the complete restructuring
against a disposable restored production copy, then review assignments, counts,
profiles and isolation before an approved production rollout.
