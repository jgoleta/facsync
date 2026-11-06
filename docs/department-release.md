# Department restructuring release checklist

Prepared on November 6, 2026. Current branch: main, with uncommitted changes.
No commit, push, merge, production migration or deployment was performed by this review.

## Release contents

Select all changed application files under apps/, except the nine new test files
listed below. Include the three changed templates/emails/ files. There are 68
release files in this checkout, including all seven migrations. Do not exclude
migrations: they are required for the application models.

No dependency, production-settings, Vercel configuration or new production
service credential change is required by this release. The existing build checks
Django and collects static assets; it does not apply database migrations.

Exact release file list:

```text
apps/core/adapters.py
apps/core/decorators.py
apps/core/department_access.py
apps/core/department_models.py
apps/core/department_updates.py
apps/core/education.py
apps/core/forms.py
apps/core/migrations/0026_department_foundation.py
apps/core/migrations/0027_attach_adnu_departments.py
apps/core/migrations/0028_head_title_labels.py
apps/core/migrations/0029_department_closure_scope.py
apps/core/migrations/0030_educational_levels.py
apps/core/migrations/0031_classify_existing_students.py
apps/core/models.py
apps/core/school_models.py
apps/core/school_scope.py
apps/core/services.py
apps/core/static/core/css/studentProfileSetup.css
apps/core/static/core/js/studentProfileSetup.js
apps/core/student_announcements.py
apps/core/templates/core/studentProfileSetup.html
apps/core/views.py
apps/depthead/forms.py
apps/depthead/models.py
apps/depthead/scope.py
apps/depthead/services/ai_insights.py
apps/depthead/services/analytics.py
apps/depthead/services/analytics_browser.py
apps/depthead/templates/depthead/adminDashboard.html
apps/depthead/templates/depthead/adminFaculty.html
apps/depthead/templates/depthead/collegeSettings.html
apps/depthead/templates/depthead/departmentSettings.html
apps/depthead/templates/depthead/facultyMonitoring.html
apps/depthead/templates/depthead/facultyTrends.html
apps/depthead/templates/depthead/peakAnalytics.html
apps/depthead/templates/depthead/studentBehavior.html
apps/depthead/views.py
apps/faculty/migrations/0034_department_foundation.py
apps/faculty/models.py
apps/faculty/services/consultation_browser.py
apps/faculty/views.py
apps/students/availability_browser.py
apps/students/static/students/js/dashboardStudent.js
apps/students/templates/students/dashboardStudent.html
apps/students/templates/students/homeStudent.html
apps/students/templates/students/partials/availability_browser.html
apps/students/templates/students/profile.html
apps/students/views.py
apps/superadmin/assignment_services.py
apps/superadmin/department_views.py
apps/superadmin/forms.py
apps/superadmin/static/superadmin/css/departmentManagement.css
apps/superadmin/static/superadmin/js/departmentManagement.js
apps/superadmin/templates/superadmin/base_management.html
apps/superadmin/templates/superadmin/manageAdmins.html
apps/superadmin/templates/superadmin/manageColleges.html
apps/superadmin/templates/superadmin/manageDepartments.html
apps/superadmin/templates/superadmin/manageFaculty.html
apps/superadmin/templates/superadmin/manageOffices.html
apps/superadmin/templates/superadmin/manageStudents.html
apps/superadmin/templates/superadmin/partials/sidebar_nav.html
apps/superadmin/templates/superadmin/schoolSettings.html
apps/superadmin/templates/superadmin/superadminDashboard.html
apps/superadmin/urls.py
apps/superadmin/views.py
templates/emails/college_announcement.html
templates/emails/college_closure.html
templates/emails/depthead_invite.html
```

## Keep on the validation branch

Uncheck these files when making the release commit:

```text
.env.rehearsal.example
apps/core/tests/test_department_foundation.py
apps/core/tests/test_department_migrations.py
apps/core/tests/test_education.py
apps/core/tests/test_education_browser.py
apps/core/tests/test_education_migrations.py
apps/depthead/tests/test_department_scope.py
apps/depthead/tests/test_department_scope_browser.py
apps/superadmin/tests/test_department_management.py
apps/superadmin/tests/test_department_management_browser.py
docs/department-foundation.md
docs/department-management.md
docs/department-rehearsal.md
docs/department-release.md
docs/department-reporting.md
docs/student-education.md
scripts/check_department_rehearsal.py
scripts/migrate_department_rehearsal.py
scripts/restore_department_rehearsal.py
```

The real .env, .env.rehearsal, .env.staging and .staging-backups/ are private and
ignored. They are not tracked. Never force-add them. The empty
.env.rehearsal.example is safe configuration documentation and belongs on the
validation branch if keeping docs/tools separate. Do not remove any of these
files from your laptop merely to exclude them from a commit.

## GitHub Desktop sequence

1. Create feature/department-restructure-release from the current main branch.
   Keep/bring all local changes onto that new branch if Desktop asks.
2. In Changes, select the 68 release files and uncheck the validation list above.
   Inspect the selected-file list before committing. A suggested summary is:
   Add departments, assigned head reporting and student educational levels.
3. Commit those selected files to the release branch, then Publish branch.
   Main stays unchanged. Do not merge yet.
4. Create feature/department-restructure-validation FROM THE RELEASE BRANCH.
   Keep/bring the remaining changes. Commit the remaining test/doc/tool files
   there. Publishing this branch is optional; it is not the production release.
5. Switch back to feature/department-restructure-release. Both branches now retain
   the application code, but only validation has the extra tests/docs/tools.
   Do not merge the validation branch into main if the goal is to keep them out.

Because the release branch excludes this document, it disappears from that branch
once the validation files are committed. Keep the checklist open or read it from
the validation branch as needed. Do not cherry-pick validation commits into the
release branch without reviewing their contents.

## Production sequence (not executed)

After the release branch is published, review its diff against main and its build.
A preview build passing is not a test of migration/data behavior. Until the
production schema is migrated, a preview connected to production may not render
the new pages. The successful feature checks used the separate rehearsal copy.

Before running any production command:

- Confirm the production project identity and current migration plan read-only.
  The rehearsal scripts deliberately refuse production; do not bypass that guard.
- Pause the cron job and ask testers not to book, approve or change records.
  Merely having an idle browser tab open is not the same as making changes.
- Keep the fresh production backup. Refresh it if there have been important writes
  since the November 6, 7:19 PM backup. Exporting a backup does not change records.
- Ensure the matching release code is ready to deploy promptly. Avoid a long gap
  between applying migrations and switching the production code.

Then apply the seven reviewed production migrations using the matching local
release checkout, merge the release PR into main, and verify Vercel's production
deployment has the matching code. Do not run makemigrations on production: the
seven prepared migration files are the source of truth.

Use a quiet rollout window and keep the cron paused until live checks pass:
Super Admin department/college management, head assignments and combined views,
existing student profiles, offered educational levels, a new student profile,
same-school cross-department booking and normal approval/completion, plus live
Google sign-in and email checks. Resume the cron afterward.

A Vercel code rollback does not undo database migrations or new department data.
After new department assignments, basic-education profiles or educational-level
audit records exist, reverse migrations may intentionally refuse. Review any
failure before deciding between a forward repair and restoring a backup; do not
force --fake or blindly roll back only the code.

## Evidence and limits

The new PostgreSQL rehearsal project received the November 6 production backup.
All seven restructuring migrations passed. Original field values/counts matched
across 26 application tables; seven ADNU departments and three head assignments
were populated; seven students were classified as College. Twenty-two page and
role checks passed using copied accounts. No live Google, email, queue or Gemini
provider call was tested in those checks.

The last full local suite comparison remains 400 tests, 205 failures, 105 errors
and nine skipped browser checks, with the same failing/error names as the prior
baseline. It is not an all-green suite. The browser checks passed separately.
The file review reran offline Django checks and makemigrations --check --dry-run:
both passed, with no missing migrations. All release Python files parse.
See department-rehearsal.md and student-education.md for details.
