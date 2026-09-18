# Analytics browser validation

- Baseline: 166 Django tests; 21 failures, 3 errors.
- Final: 173 Django tests; identical 21 failures and 3 errors (exact test identifiers compared).
- All 7 new endpoint/isolation/rendering tests pass.
- All 3 new JavaScript interaction tests pass.
- All 7 existing college settings JavaScript tests pass.
- Overview renders 12 buttons; Peak Analytics, Faculty Trends and Student Behavior render neither widget nor its script.
- No browser visual verification was available.

## Existing baseline failures/errors

- ERROR: test_clear_schedule_deletes_only_uploaded_preview_events 
- ERROR: test_recurring_event_stays_local_when_google_is_connected 
- ERROR: test_recurring_google_payload_counts_every_matching_weekday 
- FAIL: test_approving_consultation_creates_google_event 
- FAIL: test_booking_page_renders (apps.faculty.tests.test_views.FacultyViewTests.test_booking_page_renders)
- FAIL: test_calendar_sync_preference_requires_connection_and_can_be_disabled 
- FAIL: test_csv_none_day_creates_time_only_month_range 
- FAIL: test_csv_schedule_upload_appends_schedule_and_returns_preview 
- FAIL: test_dashboard_page_renders (apps.faculty.tests.test_views.FacultyViewTests.test_dashboard_page_renders)
- FAIL: test_depthead_can_upload_schedule_for_same_college_faculty 
- FAIL: test_expired_manual_status_defaults_to_available 
- FAIL: test_faculty_can_notify_and_complete_walk_in_student 
- FAIL: test_faculty_can_toggle_walk_in_availability 
- FAIL: test_invalid_csv_does_not_delete_existing_schedule 
- FAIL: test_manual_status_can_be_cleared_back_to_calendar_status 
- FAIL: test_mixed_uploads_append_preview_and_delete_only_displayed_rows (apps.faculty.tests.test_unified_preview.Unified
- FAIL: test_profile_page_renders (apps.faculty.tests.test_views.FacultyViewTests.test_profile_page_renders)
- FAIL: test_profile_updates_editable_fields 
- FAIL: test_reschedule_and_cancel_update_and_delete_google_event 
- FAIL: test_schedule_page_renders (apps.faculty.tests.test_views.FacultyViewTests.test_schedule_page_renders)
- FAIL: test_schedule_template_download_has_canonical_csv_headers 
- FAIL: test_status_is_derived_from_an_active_system_calendar_event 
- FAIL: test_status_update_persists_status_note_and_history 
- FAIL: test_student_schedule_api_returns_faculty_events 
