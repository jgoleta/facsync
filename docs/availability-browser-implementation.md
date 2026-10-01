# Availability browser implementation and validation

College Head Overview: 400px full-height right drawer, desktop content reflow, edge tab, 16px messages and 15px questions. Below 1280px the drawer overlays an inert background with focus containment; at 600px and below it fills the screen. Existing colors and College Head backend remain unchanged.

Student dashboard: same drawer, four fixed availability questions. Separate GET endpoint uses authenticated student college only, never the client college filter. Answers use recorded current status and existing schedule calculations. No status refresh, performance dispatcher, AI calls, or persistence. Schedule caveats and closure warnings remain visible.

## Results

- Fresh baseline: 236 Django tests; 26 failures, 2 errors.
- Final: 242 Django tests; identical 26 failures and 2 errors, compared by complete test identifier and failure/error classification.
- New/resolved baseline failures: none.
- Focused student and College Head browser tests: 13 passed.
- JavaScript baseline: 10 passed. Final: 13 passed.
- Cross-college scope, guessed admin metrics, roles, GET-only, missing college, no database writes, closure, ties, deactivated faculty, widget placement, repeated questions, mobile focus and reset covered.
- git diff --check passed.
- No deployed or visual browser verification; no browser automation is installed in this environment.

## Changed implementation/test files

- `apps/depthead/static/depthead/css/analytics_browser.css`
- `apps/depthead/static/depthead/js/analytics_browser.js`
- `apps/depthead/templates/depthead/adminDashboard.html`
- `apps/depthead/templates/depthead/partials/analytics_browser.html`
- `apps/students/templates/students/dashboardStudent.html`
- `apps/students/urls.py`
- `apps/students/views.py`
- `tests/analytics_browser.test.js`
- `apps/students/availability_browser.py`
- `apps/students/templates/students/partials/availability_browser.html`
- `apps/students/tests/test_availability_browser.py`

## Unchanged baseline failures/errors

- ERROR: `test_recurring_event_stays_local_when_google_is_connected (apps.faculty.tests.test_views.FacultyViewTests.test_recurring_event_stays_local_when_google_is_connected)`
- ERROR: `test_recurring_google_payload_counts_every_matching_weekday (apps.faculty.tests.test_views.FacultyViewTests.test_recurring_google_payload_counts_every_matching_weekday)`
- FAIL: `test_all_statuses_college_scope_and_scheduled_boundaries (apps.depthead.tests.test_consultation_topics.Consultati onTopicsTests.test_all_statuses_college_scope_and_scheduled_boundaries)`
- FAIL: `test_approving_consultation_creates_google_event (apps.faculty.tests.test_views.FacultyViewTests.test_approving_consultation_creates_google_event)`
- FAIL: `test_booking_page_renders (apps.faculty.tests.test_views.FacultyViewTests.test_booking_page_renders)`
- FAIL: `test_calendar_failure_preserves_request (apps.students.tests.test_consultation_deletion.ConsultationDeletionTests.test_calendar_failure_preserves_request)`
- FAIL: `test_calendar_sync_preference_requires_connection_and_can_be_disabled (apps.faculty.tests.test_views.FacultyViewTests.test_calendar_sync_preference_requires_connection_and_can_be_disabled)`
- FAIL: `test_consultation_summary_status_distribution (apps.depthead.tests.test_analytics.CollegeAnalyticsTests.test_consultation_summary_status_distribution)`
- FAIL: `test_csv_none_day_creates_time_only_month_range (apps.faculty.tests.test_views.FacultyViewTests.test_csv_none_day_creates_time_only_month_range)`
- FAIL: `test_dashboard_page_renders (apps.faculty.tests.test_views.FacultyViewTests.test_dashboard_page_renders)`
- FAIL: `test_expired_manual_status_defaults_to_available (apps.faculty.tests.test_views.FacultyViewTests.test_expired_manual_status_defaults_to_available)`
- FAIL: `test_faculty_can_notify_and_complete_walk_in_student (apps.faculty.tests.test_views.FacultyViewTests.test_faculty_can_notify_and_complete_walk_in_student)`
- FAIL: `test_faculty_can_toggle_walk_in_availability (apps.faculty.tests.test_views.FacultyViewTests.test_faculty_can_toggle_walk_in_availability)`
- FAIL: `test_faculty_sees_cancellation_decisions_and_consultation_type (apps.students.tests.test_cancellation.Cancellatio nTests.test_faculty_sees_cancellation_decisions_and_consultation_type) (consultation_type='face_to_face')`
- FAIL: `test_faculty_sees_cancellation_decisions_and_consultation_type (apps.students.tests.test_cancellation.Cancellatio nTests.test_faculty_sees_cancellation_decisions_and_consultation_type) (consultation_type='online')`
- FAIL: `test_linked_calendar_event_removed (apps.students.tests.test_consultation_deletion.ConsultationDeletionTests.test_linked_calendar_event_removed)`
- FAIL: `test_manual_status_can_be_cleared_back_to_calendar_status (apps.faculty.tests.test_views.FacultyViewTests.test_manual_status_can_be_cleared_back_to_calendar_status)`
- FAIL: `test_owner_can_delete_each_status_and_request_disappears (apps.students.tests.test_consultation_deletion.Consulta tionDeletionTests.test_owner_can_delete_each_status_and_request_disappears) (status='approved')`
- FAIL: `test_owner_can_delete_each_status_and_request_disappears (apps.students.tests.test_consultation_deletion.Consulta tionDeletionTests.test_owner_can_delete_each_status_and_request_disappears) (status='cancellation_requested')`
- FAIL: `test_profile_page_renders (apps.faculty.tests.test_views.FacultyViewTests.test_profile_page_renders)`
- FAIL: `test_profile_updates_editable_fields (apps.faculty.tests.test_views.FacultyViewTests.test_profile_updates_editable_fields)`
- FAIL: `test_reschedule_and_cancel_update_and_delete_google_event (apps.faculty.tests.test_views.FacultyViewTests.test_reschedule_and_cancel_update_and_delete_google_event)`
- FAIL: `test_schedule_page_renders (apps.faculty.tests.test_views.FacultyViewTests.test_schedule_page_renders)`
- FAIL: `test_schedule_template_download_has_canonical_csv_headers (apps.faculty.tests.test_views.FacultyViewTests.test_schedule_template_download_has_canonical_csv_headers)`
- FAIL: `test_status_is_derived_from_an_active_system_calendar_event (apps.faculty.tests.test_views.FacultyViewTests.test_status_is_derived_from_an_active_system_calendar_event)`
- FAIL: `test_status_update_persists_status_note_and_history (apps.faculty.tests.test_views.FacultyViewTests.test_status_update_persists_status_note_and_history)`
- FAIL: `test_student_consultation_list_includes_completed_and_excludes_declined_requests (apps.students.tests.test_views. StudentScheduleTests.test_student_consultation_list_includes_completed_and_excludes_declined_requests)`
- FAIL: `test_student_schedule_api_returns_faculty_events (apps.students.tests.test_views.StudentScheduleTests.test_student_schedule_api_returns_faculty_events)`
