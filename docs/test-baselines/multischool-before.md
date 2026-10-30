# Baseline before multi-school implementation

Captured for client date 2026-10-29, after staging isolation/sample tooling and before multi-school implementation.

This is a baseline of the current working tree, not a clean historical checkout. No application fixes were made during capture.

```powershell
.\venv\Scripts\python.exe manage.py test --settings=config.settings.test --verbosity=2 --noinput
```

Result: **312 tests; 39 failures; 9 errors**, in 15.766 seconds. Exit code 1 is expected for this failing baseline.

The test database was local in-memory SQLite. Staging and production were not accessed. All six staging-seed tests passed.

Python 3.13.15; Django 6.1.1; HEAD `94d5a35083d3f2f88a0c104d20bb95c5484a5cd9`.

Full tracebacks are in the ignored root log `multischool-before-tests.log`. The adjacent JSON preserves exact failing names, subtest parameters, outcome categories, log hashes and historical comparisons.

Runner totals count failed subtest occurrences; they are not necessarily counts of distinct test methods.

## Historical comparisons

| Saved run | Tests | Failures | Errors | Same failing name/outcome | Outcome transitions | Previously failing, now passed | Previously failing, not observed passing | Current failing names absent from old failure list |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline-tests.log | 166 | 21 | 3 | 18 | 0 | 6 | 0 | 27 |
| final-tests.log | 173 | 21 | 3 | 18 | 0 | 6 | 0 | 27 |
| scheduler-after.log | 312 | 32 | 2 | 28 | 1 | 1 | 2 | 16 |

Names absent from an old failure list can include tests added since that run. They must not automatically be labelled regressions. Names not observed passing may have been renamed or removed; they are not automatically fixes.

## Comparison by test name

### baseline-tests.log

**Same failing name and outcome**

- `apps.faculty.tests.test_views.FacultyViewTests.test_approving_consultation_creates_google_event`
- `apps.faculty.tests.test_views.FacultyViewTests.test_booking_page_renders`
- `apps.faculty.tests.test_views.FacultyViewTests.test_calendar_sync_preference_requires_connection_and_can_be_disabled`
- `apps.faculty.tests.test_views.FacultyViewTests.test_csv_none_day_creates_time_only_month_range`
- `apps.faculty.tests.test_views.FacultyViewTests.test_dashboard_page_renders`
- `apps.faculty.tests.test_views.FacultyViewTests.test_expired_manual_status_defaults_to_available`
- `apps.faculty.tests.test_views.FacultyViewTests.test_faculty_can_toggle_walk_in_availability`
- `apps.faculty.tests.test_views.FacultyViewTests.test_manual_status_can_be_cleared_back_to_calendar_status`
- `apps.faculty.tests.test_views.FacultyViewTests.test_profile_page_renders`
- `apps.faculty.tests.test_views.FacultyViewTests.test_profile_updates_editable_fields`
- `apps.faculty.tests.test_views.FacultyViewTests.test_recurring_event_stays_local_when_google_is_connected`
- `apps.faculty.tests.test_views.FacultyViewTests.test_recurring_google_payload_counts_every_matching_weekday`
- `apps.faculty.tests.test_views.FacultyViewTests.test_reschedule_and_cancel_update_and_delete_google_event`
- `apps.faculty.tests.test_views.FacultyViewTests.test_schedule_page_renders`
- `apps.faculty.tests.test_views.FacultyViewTests.test_schedule_template_download_has_canonical_csv_headers`
- `apps.faculty.tests.test_views.FacultyViewTests.test_status_is_derived_from_an_active_system_calendar_event`
- `apps.faculty.tests.test_views.FacultyViewTests.test_status_update_persists_status_note_and_history`
- `apps.students.tests.test_views.StudentScheduleTests.test_student_schedule_api_returns_faculty_events`

**Outcome transitions**

None.

**Previously failing, now passed**

- `apps.depthead.tests.test_views.DeptheadViewTests.test_depthead_can_upload_schedule_for_same_college_faculty`
- `apps.faculty.tests.test_unified_preview.UnifiedPreviewTests.test_mixed_uploads_append_preview_and_delete_only_displayed_rows`
- `apps.faculty.tests.test_views.FacultyViewTests.test_clear_schedule_deletes_only_uploaded_preview_events`
- `apps.faculty.tests.test_views.FacultyViewTests.test_csv_schedule_upload_appends_schedule_and_returns_preview`
- `apps.faculty.tests.test_views.FacultyViewTests.test_faculty_can_notify_and_complete_walk_in_student`
- `apps.faculty.tests.test_views.FacultyViewTests.test_invalid_csv_does_not_delete_existing_schedule`

**Previously failing, not observed passing**

None.

**Current failing names absent from the saved failure list**

- `apps.depthead.tests.test_analytics.CollegeAnalyticsTests.test_consultation_summary_status_distribution`
- `apps.depthead.tests.test_analytics_browser.AnalyticsBrowserTests.test_capacity_honestly_unavailable`
- `apps.depthead.tests.test_analytics_browser.AnalyticsBrowserTests.test_repeated_fetch_reuses_schedule_service_each_time`
- `apps.depthead.tests.test_analytics_browser.AnalyticsBrowserTests.test_scope_ignores_client_college`
- `apps.depthead.tests.test_analytics_browser.AnalyticsBrowserTests.test_widget_only_on_overview`
- `apps.depthead.tests.test_college_analytics_batching.CollegeAnalyticsBatchingTests.test_all_browser_answers_match_frozen_public_helpers`
- `apps.depthead.tests.test_college_analytics_batching.CollegeAnalyticsBatchingTests.test_fixed_query_budget_and_complete_page_parity_at_three_and_fifteen`
- `apps.depthead.tests.test_consultation_topics.ConsultationTopicsTests.test_all_statuses_college_scope_and_scheduled_boundaries`
- `apps.depthead.tests.test_faculty_trends_batching.FacultyTrendsBatchingTests.test_output_parity_and_fixed_page_queries_at_three_and_fifteen`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_charts_distinguish_tiny_zero_and_missing_rates`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_fragmented_free_time_does_not_meet_threshold`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_no_records_excluded_from_ranking_but_included_in_percentage`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_only_unscheduled_faculty_and_empty_college`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_overlaps_clipping_and_exact_threshold`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_recurring_and_dated_events_bucket_by_actual_occurrence`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_schedule_chart_renders_zero_as_zero_height`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_stale_external_events_do_not_occupy_time_or_qualify_for_ranking`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_view_renders_tables_and_caveat`
- `apps.depthead.tests.test_views.DeptheadViewTests.test_ai_endpoint_adds_local_daily_faculty_recommendation`
- `apps.faculty.tests.test_views.FacultyViewTests.test_bulk_delete_removes_google_events_when_sync_is_disabled`
- `apps.students.tests.test_availability_browser.AvailabilityBrowserTests.test_every_answer_scoped_and_read_only`
- `apps.students.tests.test_availability_browser.AvailabilityBrowserTests.test_ties_and_repeated_requests`
- `apps.students.tests.test_cancellation.CancellationTests.test_student_cancellation_removes_faculty_card_immediately`
- `apps.students.tests.test_consultation_deletion.ConsultationDeletionTests.test_calendar_failure_preserves_request`
- `apps.students.tests.test_consultation_deletion.ConsultationDeletionTests.test_linked_calendar_event_removed`
- `apps.students.tests.test_consultation_deletion.ConsultationDeletionTests.test_owner_can_delete_deletable_statuses_and_request_disappears`
- `apps.students.tests.test_views.StudentScheduleTests.test_student_consultation_list_includes_completed_and_excludes_declined_requests`

### final-tests.log

**Same failing name and outcome**

- `apps.faculty.tests.test_views.FacultyViewTests.test_approving_consultation_creates_google_event`
- `apps.faculty.tests.test_views.FacultyViewTests.test_booking_page_renders`
- `apps.faculty.tests.test_views.FacultyViewTests.test_calendar_sync_preference_requires_connection_and_can_be_disabled`
- `apps.faculty.tests.test_views.FacultyViewTests.test_csv_none_day_creates_time_only_month_range`
- `apps.faculty.tests.test_views.FacultyViewTests.test_dashboard_page_renders`
- `apps.faculty.tests.test_views.FacultyViewTests.test_expired_manual_status_defaults_to_available`
- `apps.faculty.tests.test_views.FacultyViewTests.test_faculty_can_toggle_walk_in_availability`
- `apps.faculty.tests.test_views.FacultyViewTests.test_manual_status_can_be_cleared_back_to_calendar_status`
- `apps.faculty.tests.test_views.FacultyViewTests.test_profile_page_renders`
- `apps.faculty.tests.test_views.FacultyViewTests.test_profile_updates_editable_fields`
- `apps.faculty.tests.test_views.FacultyViewTests.test_recurring_event_stays_local_when_google_is_connected`
- `apps.faculty.tests.test_views.FacultyViewTests.test_recurring_google_payload_counts_every_matching_weekday`
- `apps.faculty.tests.test_views.FacultyViewTests.test_reschedule_and_cancel_update_and_delete_google_event`
- `apps.faculty.tests.test_views.FacultyViewTests.test_schedule_page_renders`
- `apps.faculty.tests.test_views.FacultyViewTests.test_schedule_template_download_has_canonical_csv_headers`
- `apps.faculty.tests.test_views.FacultyViewTests.test_status_is_derived_from_an_active_system_calendar_event`
- `apps.faculty.tests.test_views.FacultyViewTests.test_status_update_persists_status_note_and_history`
- `apps.students.tests.test_views.StudentScheduleTests.test_student_schedule_api_returns_faculty_events`

**Outcome transitions**

None.

**Previously failing, now passed**

- `apps.depthead.tests.test_views.DeptheadViewTests.test_depthead_can_upload_schedule_for_same_college_faculty`
- `apps.faculty.tests.test_unified_preview.UnifiedPreviewTests.test_mixed_uploads_append_preview_and_delete_only_displayed_rows`
- `apps.faculty.tests.test_views.FacultyViewTests.test_clear_schedule_deletes_only_uploaded_preview_events`
- `apps.faculty.tests.test_views.FacultyViewTests.test_csv_schedule_upload_appends_schedule_and_returns_preview`
- `apps.faculty.tests.test_views.FacultyViewTests.test_faculty_can_notify_and_complete_walk_in_student`
- `apps.faculty.tests.test_views.FacultyViewTests.test_invalid_csv_does_not_delete_existing_schedule`

**Previously failing, not observed passing**

None.

**Current failing names absent from the saved failure list**

- `apps.depthead.tests.test_analytics.CollegeAnalyticsTests.test_consultation_summary_status_distribution`
- `apps.depthead.tests.test_analytics_browser.AnalyticsBrowserTests.test_capacity_honestly_unavailable`
- `apps.depthead.tests.test_analytics_browser.AnalyticsBrowserTests.test_repeated_fetch_reuses_schedule_service_each_time`
- `apps.depthead.tests.test_analytics_browser.AnalyticsBrowserTests.test_scope_ignores_client_college`
- `apps.depthead.tests.test_analytics_browser.AnalyticsBrowserTests.test_widget_only_on_overview`
- `apps.depthead.tests.test_college_analytics_batching.CollegeAnalyticsBatchingTests.test_all_browser_answers_match_frozen_public_helpers`
- `apps.depthead.tests.test_college_analytics_batching.CollegeAnalyticsBatchingTests.test_fixed_query_budget_and_complete_page_parity_at_three_and_fifteen`
- `apps.depthead.tests.test_consultation_topics.ConsultationTopicsTests.test_all_statuses_college_scope_and_scheduled_boundaries`
- `apps.depthead.tests.test_faculty_trends_batching.FacultyTrendsBatchingTests.test_output_parity_and_fixed_page_queries_at_three_and_fifteen`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_charts_distinguish_tiny_zero_and_missing_rates`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_fragmented_free_time_does_not_meet_threshold`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_no_records_excluded_from_ranking_but_included_in_percentage`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_only_unscheduled_faculty_and_empty_college`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_overlaps_clipping_and_exact_threshold`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_recurring_and_dated_events_bucket_by_actual_occurrence`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_schedule_chart_renders_zero_as_zero_height`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_stale_external_events_do_not_occupy_time_or_qualify_for_ranking`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_view_renders_tables_and_caveat`
- `apps.depthead.tests.test_views.DeptheadViewTests.test_ai_endpoint_adds_local_daily_faculty_recommendation`
- `apps.faculty.tests.test_views.FacultyViewTests.test_bulk_delete_removes_google_events_when_sync_is_disabled`
- `apps.students.tests.test_availability_browser.AvailabilityBrowserTests.test_every_answer_scoped_and_read_only`
- `apps.students.tests.test_availability_browser.AvailabilityBrowserTests.test_ties_and_repeated_requests`
- `apps.students.tests.test_cancellation.CancellationTests.test_student_cancellation_removes_faculty_card_immediately`
- `apps.students.tests.test_consultation_deletion.ConsultationDeletionTests.test_calendar_failure_preserves_request`
- `apps.students.tests.test_consultation_deletion.ConsultationDeletionTests.test_linked_calendar_event_removed`
- `apps.students.tests.test_consultation_deletion.ConsultationDeletionTests.test_owner_can_delete_deletable_statuses_and_request_disappears`
- `apps.students.tests.test_views.StudentScheduleTests.test_student_consultation_list_includes_completed_and_excludes_declined_requests`

### scheduler-after.log

**Same failing name and outcome**

- `apps.depthead.tests.test_analytics.CollegeAnalyticsTests.test_consultation_summary_status_distribution`
- `apps.depthead.tests.test_analytics_browser.AnalyticsBrowserTests.test_capacity_honestly_unavailable`
- `apps.depthead.tests.test_analytics_browser.AnalyticsBrowserTests.test_scope_ignores_client_college`
- `apps.depthead.tests.test_consultation_topics.ConsultationTopicsTests.test_all_statuses_college_scope_and_scheduled_boundaries`
- `apps.depthead.tests.test_views.DeptheadViewTests.test_ai_endpoint_adds_local_daily_faculty_recommendation`
- `apps.faculty.tests.test_views.FacultyViewTests.test_approving_consultation_creates_google_event`
- `apps.faculty.tests.test_views.FacultyViewTests.test_booking_page_renders`
- `apps.faculty.tests.test_views.FacultyViewTests.test_bulk_delete_removes_google_events_when_sync_is_disabled`
- `apps.faculty.tests.test_views.FacultyViewTests.test_calendar_sync_preference_requires_connection_and_can_be_disabled`
- `apps.faculty.tests.test_views.FacultyViewTests.test_csv_none_day_creates_time_only_month_range`
- `apps.faculty.tests.test_views.FacultyViewTests.test_dashboard_page_renders`
- `apps.faculty.tests.test_views.FacultyViewTests.test_expired_manual_status_defaults_to_available`
- `apps.faculty.tests.test_views.FacultyViewTests.test_faculty_can_toggle_walk_in_availability`
- `apps.faculty.tests.test_views.FacultyViewTests.test_manual_status_can_be_cleared_back_to_calendar_status`
- `apps.faculty.tests.test_views.FacultyViewTests.test_profile_page_renders`
- `apps.faculty.tests.test_views.FacultyViewTests.test_profile_updates_editable_fields`
- `apps.faculty.tests.test_views.FacultyViewTests.test_recurring_event_stays_local_when_google_is_connected`
- `apps.faculty.tests.test_views.FacultyViewTests.test_recurring_google_payload_counts_every_matching_weekday`
- `apps.faculty.tests.test_views.FacultyViewTests.test_reschedule_and_cancel_update_and_delete_google_event`
- `apps.faculty.tests.test_views.FacultyViewTests.test_schedule_page_renders`
- `apps.faculty.tests.test_views.FacultyViewTests.test_schedule_template_download_has_canonical_csv_headers`
- `apps.faculty.tests.test_views.FacultyViewTests.test_status_is_derived_from_an_active_system_calendar_event`
- `apps.faculty.tests.test_views.FacultyViewTests.test_status_update_persists_status_note_and_history`
- `apps.students.tests.test_availability_browser.AvailabilityBrowserTests.test_every_answer_scoped_and_read_only`
- `apps.students.tests.test_consultation_deletion.ConsultationDeletionTests.test_calendar_failure_preserves_request`
- `apps.students.tests.test_consultation_deletion.ConsultationDeletionTests.test_linked_calendar_event_removed`
- `apps.students.tests.test_views.StudentScheduleTests.test_student_consultation_list_includes_completed_and_excludes_declined_requests`
- `apps.students.tests.test_views.StudentScheduleTests.test_student_schedule_api_returns_faculty_events`

**Outcome transitions**

- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_overlaps_clipping_and_exact_threshold`: FAIL ? ERROR

**Previously failing, now passed**

- `apps.faculty.tests.test_views.FacultyViewTests.test_faculty_can_notify_and_complete_walk_in_student`

**Previously failing, not observed passing**

- `apps.students.tests.test_cancellation.CancellationTests.test_faculty_sees_cancellation_decisions_and_consultation_type`
- `apps.students.tests.test_consultation_deletion.ConsultationDeletionTests.test_owner_can_delete_each_status_and_request_disappears`

**Current failing names absent from the saved failure list**

- `apps.depthead.tests.test_analytics_browser.AnalyticsBrowserTests.test_repeated_fetch_reuses_schedule_service_each_time`
- `apps.depthead.tests.test_analytics_browser.AnalyticsBrowserTests.test_widget_only_on_overview`
- `apps.depthead.tests.test_college_analytics_batching.CollegeAnalyticsBatchingTests.test_all_browser_answers_match_frozen_public_helpers`
- `apps.depthead.tests.test_college_analytics_batching.CollegeAnalyticsBatchingTests.test_fixed_query_budget_and_complete_page_parity_at_three_and_fifteen`
- `apps.depthead.tests.test_faculty_trends_batching.FacultyTrendsBatchingTests.test_output_parity_and_fixed_page_queries_at_three_and_fifteen`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_charts_distinguish_tiny_zero_and_missing_rates`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_fragmented_free_time_does_not_meet_threshold`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_no_records_excluded_from_ranking_but_included_in_percentage`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_only_unscheduled_faculty_and_empty_college`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_recurring_and_dated_events_bucket_by_actual_occurrence`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_schedule_chart_renders_zero_as_zero_height`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_stale_external_events_do_not_occupy_time_or_qualify_for_ranking`
- `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_view_renders_tables_and_caveat`
- `apps.students.tests.test_availability_browser.AvailabilityBrowserTests.test_ties_and_repeated_requests`
- `apps.students.tests.test_cancellation.CancellationTests.test_student_cancellation_removes_faculty_card_immediately`
- `apps.students.tests.test_consultation_deletion.ConsultationDeletionTests.test_owner_can_delete_deletable_statuses_and_request_disappears`

## Current failing occurrences

| Outcome | Fully qualified test | Subtest |
| --- | --- | --- |
| ERROR | `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_fragmented_free_time_does_not_meet_threshold` | ? |
| ERROR | `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_no_records_excluded_from_ranking_but_included_in_percentage` | ? |
| ERROR | `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_only_unscheduled_faculty_and_empty_college` | ? |
| ERROR | `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_overlaps_clipping_and_exact_threshold` | ? |
| ERROR | `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_recurring_and_dated_events_bucket_by_actual_occurrence` | ? |
| ERROR | `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_stale_external_events_do_not_occupy_time_or_qualify_for_ranking` | ? |
| ERROR | `apps.faculty.tests.test_views.FacultyViewTests.test_recurring_event_stays_local_when_google_is_connected` | ? |
| ERROR | `apps.faculty.tests.test_views.FacultyViewTests.test_recurring_google_payload_counts_every_matching_weekday` | ? |
| ERROR | `apps.students.tests.test_availability_browser.AvailabilityBrowserTests.test_ties_and_repeated_requests` | ? |
| FAIL | `apps.depthead.tests.test_analytics.CollegeAnalyticsTests.test_consultation_summary_status_distribution` | ? |
| FAIL | `apps.depthead.tests.test_analytics_browser.AnalyticsBrowserTests.test_capacity_honestly_unavailable` | ? |
| FAIL | `apps.depthead.tests.test_analytics_browser.AnalyticsBrowserTests.test_repeated_fetch_reuses_schedule_service_each_time` | ? |
| FAIL | `apps.depthead.tests.test_analytics_browser.AnalyticsBrowserTests.test_scope_ignores_client_college` | ? |
| FAIL | `apps.depthead.tests.test_analytics_browser.AnalyticsBrowserTests.test_widget_only_on_overview` | ? |
| FAIL | `apps.depthead.tests.test_college_analytics_batching.CollegeAnalyticsBatchingTests.test_all_browser_answers_match_frozen_public_helpers` | `(metric='approval_times')` |
| FAIL | `apps.depthead.tests.test_college_analytics_batching.CollegeAnalyticsBatchingTests.test_fixed_query_budget_and_complete_page_parity_at_three_and_fifteen` | `(page='peak_analytics', faculty_count=3)` |
| FAIL | `apps.depthead.tests.test_college_analytics_batching.CollegeAnalyticsBatchingTests.test_fixed_query_budget_and_complete_page_parity_at_three_and_fifteen` | `(page='peak_analytics', faculty_count=15)` |
| FAIL | `apps.depthead.tests.test_consultation_topics.ConsultationTopicsTests.test_all_statuses_college_scope_and_scheduled_boundaries` | ? |
| FAIL | `apps.depthead.tests.test_faculty_trends_batching.FacultyTrendsBatchingTests.test_output_parity_and_fixed_page_queries_at_three_and_fifteen` | `(faculty_count=3)` |
| FAIL | `apps.depthead.tests.test_faculty_trends_batching.FacultyTrendsBatchingTests.test_output_parity_and_fixed_page_queries_at_three_and_fifteen` | `(faculty_count=15)` |
| FAIL | `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_charts_distinguish_tiny_zero_and_missing_rates` | ? |
| FAIL | `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_schedule_chart_renders_zero_as_zero_height` | ? |
| FAIL | `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_view_renders_tables_and_caveat` | ? |
| FAIL | `apps.depthead.tests.test_views.DeptheadViewTests.test_ai_endpoint_adds_local_daily_faculty_recommendation` | ? |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_approving_consultation_creates_google_event` | ? |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_booking_page_renders` | ? |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_bulk_delete_removes_google_events_when_sync_is_disabled` | ? |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_calendar_sync_preference_requires_connection_and_can_be_disabled` | ? |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_csv_none_day_creates_time_only_month_range` | ? |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_dashboard_page_renders` | ? |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_expired_manual_status_defaults_to_available` | ? |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_faculty_can_toggle_walk_in_availability` | ? |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_manual_status_can_be_cleared_back_to_calendar_status` | ? |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_profile_page_renders` | ? |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_profile_updates_editable_fields` | ? |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_reschedule_and_cancel_update_and_delete_google_event` | ? |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_schedule_page_renders` | ? |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_schedule_template_download_has_canonical_csv_headers` | ? |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_status_is_derived_from_an_active_system_calendar_event` | ? |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_status_update_persists_status_note_and_history` | ? |
| FAIL | `apps.students.tests.test_availability_browser.AvailabilityBrowserTests.test_every_answer_scoped_and_read_only` | ? |
| FAIL | `apps.students.tests.test_cancellation.CancellationTests.test_student_cancellation_removes_faculty_card_immediately` | ? |
| FAIL | `apps.students.tests.test_consultation_deletion.ConsultationDeletionTests.test_calendar_failure_preserves_request` | ? |
| FAIL | `apps.students.tests.test_consultation_deletion.ConsultationDeletionTests.test_linked_calendar_event_removed` | ? |
| FAIL | `apps.students.tests.test_consultation_deletion.ConsultationDeletionTests.test_owner_can_delete_deletable_statuses_and_request_disappears` | `(status='approved')` |
| FAIL | `apps.students.tests.test_consultation_deletion.ConsultationDeletionTests.test_owner_can_delete_deletable_statuses_and_request_disappears` | `(status='cancellation_requested')` |
| FAIL | `apps.students.tests.test_views.StudentScheduleTests.test_student_consultation_list_includes_completed_and_excludes_declined_requests` | ? |
| FAIL | `apps.students.tests.test_views.StudentScheduleTests.test_student_schedule_api_returns_faculty_events` | ? |

## Observed error signatures

- Six schedule-availability errors access the missing `availability_percent` key.
- One student availability-browser error accesses the missing `lines` key.
- The recurring-event Google test attempts to insert a mocked expression into `google_event_id`.
- The recurring Google payload test passes a string where `datetime.combine` expects a time.

These describe the captured tracebacks, not completed root-cause diagnoses. Failure groups also include faculty HTTP authorization expectations, consultation deletion/cancellation behavior, response/display expectations and analytics query budgets. No fixes or assertion changes were attempted.

For the implementation comparison, preserve test names and subtest parameters; report unchanged outcomes, new failing cases, transitions and observed passes separately. Use both this captured baseline and the requested historical 21-failure/3-error reference.
