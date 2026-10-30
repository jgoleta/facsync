# Local test failure diagnosis

Investigated on 2026-10-30. This is a diagnosis, not a production-readiness approval.

## What was run

The unchanged application ran **391 tests in 64.712 seconds: 39 failures and
9 errors**, across 45 distinct failing test methods. Multiple failed subtests
explain why the number of failure/error occurrences exceeds the number of methods.
The failing names, subtest parameters, and outcomes exactly match
`docs/test-baselines/student-registration-phase.json`. That report in turn records
the same failures as the 312-test baseline taken before multi-school work.

All runs explicitly used `config.settings.test`: an in-memory SQLite database
and local-memory email. No commands connected to production, staging, or the
production-copy rehearsal database. No application files, test source files, or
migrations were changed during this investigation.

Reproduce the unchanged suite from the repository folder:

```powershell
.\venv\Scripts\python.exe manage.py test --settings=config.settings.test --noinput --verbosity=2
```

The full local output is `test-diagnosis-baseline.log`. Temporary diagnostic
experiments and logs are under the ignored `.staging-backups/test-diagnosis/`
folder. Those experiments patch fixtures/assertions only within their own Python
process, block HTTP requests through `requests`, and use separate SQLite test
databases. Their passing results are evidence about causes, not a replacement
for fixing and rerunning the real tests.

## Findings in plain English

The 48 failing occurrences do not represent 48 broken features. Many tests
describe an earlier version of the application, or log in as the wrong role.
However, dismissing all of them as outdated would also be wrong: there are
misleading messages, a CSV compatibility question, and incomplete comparisons
that need attention before a production rollout.

| Group | Failures | Errors | Finding |
| --- | ---: | ---: | --- |
| Faculty role fixtures | 10 | 0 | Tests omit the Faculty role; assigning it in memory lets these ten tests pass. |
| Faculty schedule page | 1 | 0 | Same role mistake; after fixing it, the page returns 200 but lacks an expected booking-page link. |
| Cancellation faculty card | 1 | 0 | Test is still logged in as the student when requesting the faculty dashboard. |
| Bulk-delete mock comparison | 1 | 0 | Google deletion is called; deleting the loaded model clears its primary key and breaks the mock's object equality assertion. |
| Recurrence payload time fixture | 0 | 1 | Test passes strings where the payload builder expects `datetime.time`. |
| Old local-only recurrence expectation | 0 | 1 | Test assumes recurring events cannot sync; its unconfigured Google mock also produces an invalid database value. |
| Removed availability percentage/chart | 3 | 6 | Tests request a field and chart that the current service and templates no longer provide. |
| College Head chatbot contract | 4 | 0 | Old wording, removed question ID, and a hard-coded question count. |
| Student chatbot contract | 1 | 1 | Old JSON schema and removed `best_day` question. |
| Consultation status expectations | 2 | 0 | Fixtures create all six current statuses; assertions still expect five. |
| Approval-time comparison | 1 | 0 | Current calculation uses approval dates; frozen helper uses appointment dates. Chatbot text incorrectly describes the old basis. |
| Page query budgets | 4 | 0 | Added page sections issue extra fixed queries; a frozen helper also has an incompatible signature. |
| AI recommendation expectation | 1 | 0 | Test expects the previous event-planning recommendation instead of the current daily faculty ranking. |
| Default faculty status | 2 | 0 | Current implementation explicitly falls back to Not Set; tests expect Available. |
| CSV template header | 1 | 0 | Test expects the old nine-column template; download now provides thirteen columns. |
| Legacy CSV blank recurrence | 1 | 0 | Supported older CSV parser rejects a time-only row accepted by the test. Needs a compatibility decision. |
| Consultation deletion | 4 | 0 | Tests attempt to delete active requests that the endpoint intentionally protects. Two calendar tests never reach their mocked operation. |
| Student consultation history | 1 | 0 | Test expects declined requests hidden; current page explicitly offers a Declined filter. |
| Student calendar JSON | 1 | 0 | Response adds seven fields; existing expected fields still match. |
| **Total** | **39** | **9** | |

## Confirmed fixture and assertion problems

### Faculty role and login

`User.role` defaults to `student`. Several fixtures in
`apps/faculty/tests/test_views.py` create users named `faculty-...` without setting
`role='faculty'`. A name or FacultyProfile does not grant a role. The 403 responses
are correct; loosening the endpoint checks would introduce an authorization bug.

A process-only correction at the user factory made ten affected methods pass.
An eleventh, `test_schedule_page_renders`, then reached a second assertion: it
expects a link to `/faculty/booking-management/` which the current schedule
template does not contain. Correct the role first, then decide whether that
navigation link is still a product requirement.

The cancellation-card test has a different login mistake: its cancellation
helper logs in as the student, then the test immediately opens the faculty
dashboard. Signing in as `self.teacher` before that request makes the complete
test pass, including disappearance of the cancelled faculty card.

### Calendar mocks and model values

The bulk-delete endpoint really calls `delete_google_event` once. The instance
passed to the mock is subsequently deleted, clearing its primary key; the
test's separately created instance retains its key. The mock retains a reference
to the mutated instance. The experiment observed `actual PK=None`, `expected
PK=1`, matching Google event IDs, and absence of the database row. Compare the
arguments at call time, as the consultation-deletion tests already do.

The recurrence payload error disappears when the newly created ScheduleEvent
is refreshed from the database before building its payload. Django does not
automatically replace string time attributes on an instance immediately after
creation. The normal event API parses time strings into time objects before
calling Google; a neighboring passing recurrence test already refreshes its
fixture.

The local-only recurrence test is a separate problem. Supplying a realistic
mock result, `{'id': 'diagnostic-google-event'}`, removes the database error and
reveals the underlying obsolete expectation: the event now has a Google ID.
The existing `test_recurring_event_syncs_when_user_chooses_google` passes.
Preserve current sync behavior and make the local-only case explicitly opt out
of sync, with a separate explicit opt-in assertion.

### Response fields

The student chatbot now returns `source_label` and `presentation` in addition to
the fields the older test expects. When only that strict schema assertion was
adjusted in memory, all five current questions completed the original privacy,
read-only SQL, cache-header, and unchanged-status checks successfully. This is
same-college fixture coverage; the separate school-isolation tests cover schools.

The student calendar response adds `offering_id`, `subject_code`, `section`,
`units`, `lecture`, `lab`, and `recurrence_excluded_dates`. Comparing the existing
expected fields passes. Update the schema test to assert the complete intended
response, including the new fields; do not simply drop the assertion.

## Older behavior versus current behavior

The availability service returns daily winners and total open minutes. It does
not calculate `availability_percent`, and the faculty-trends template no longer
renders that chart. This explains six KeyErrors and three chart failures.
Replacement tests should cover ranking, ties, excluded unscheduled faculty,
overlapping intervals, recurrence, and boundary clipping using the current
contract. Do not restore a removed metric merely to satisfy these assertions.

The College Head chatbot has fourteen current questions. `daily_availability`
is absent; `daily_faculty` is supported. Two other failures are wording-only:
`CCS — 1 request` replaces `CCS: 1 requests`, and the supply-gap explanation
changed. The student chatbot uses `week_daily` instead of `best_day`.
The AI recommendation helper likewise produces the daily faculty ranking.
These changes are consistent across current services and UI, although the
original reason for each historical product change cannot be established from
the failing logs alone.

Two status-aggregate tests loop over current `STATUS_CHOICES`, including
`cancellation_requested`, but hard-code the old five-status result. The topics
fixture now has six rows, making its split 50/50 rather than 60/40. Assertions
should explicitly specify their input populations and expected counts.

The faculty status service explicitly documents Not Set after a manual deadline
expires, and Not Set when auto mode has no active event. Tests expect Available.
Retain the current policy unless a separate behavior change is requested.

The CSV download has thirteen course-related columns; the old test expects nine.
Current regression tests successfully upload both downloaded faculty/head
templates. Separately, the legacy nine-column parser rejects blank recurring
day and month fields, while the failed test expects a time-only entry. This
is a compatibility gap, not proof that the whole upload feature is broken.
Before changing it, settle whether old time-only CSVs must remain supported.

Declined consultations are intentionally rendered by the current history page,
which has a Declined filter. The old test expects them omitted. Preserve the
history and test the filter/status representation unless requirements say otherwise.

## Items requiring particular care

### Approval-time meaning and misleading chatbot text

The current `get_faculty_trends` selects requests whose **approval timestamp** is
in the reporting period, independently of appointment dates. The frozen helper
selects requests whose **appointment date** is in the period. The fixture exposes
1.0 versus 1.2 hours; this is a different population, not a rounding error.

The current faculty-trends page explains the new calculation accurately:
"approval time uses requests approved this week." But
`apps/depthead/services/analytics_browser.py:133` still describes requests
"scheduled for" the period. This is a confirmed user-facing inconsistency.
Keep the current calculation, correct the chatbot description, and replace the
frozen comparison with explicit boundary cases where approval and appointment
dates fall in different periods. Changing the calculation back silently would
change analytics behavior beyond school scoping.

### Query budgets and a masked comparison error

Capturing queries at both three and fifteen faculty gives:

| Path | Expected | Actual at 3 | Actual at 15 |
| --- | ---: | ---: | ---: |
| College analytics service | 7 | 7 | 7 |
| College dashboard | 10 | 10 | 10 |
| Student behavior page | 10 | 10 | 10 |
| Peak analytics page | 10 | 12 | 12 |
| Faculty trends service | 4 | 4 | 4 |
| Faculty trends page | 9 | 12 | 12 |

The peak page now adds an hourly availability snapshot, with three queries after
the analytics/presentation work. Its complete HTML comparison with the old
analytics service passes when the count assertion is bypassed for diagnosis.
The faculty-trends page includes name presentation, the shared-window planner
and schedule availability. Both consume additional fixed queries. These fixtures
show no query-count growth with faculty count; this is not a newly demonstrated
per-faculty query problem. They do not prove the queries are all optimal.

Once the old count assertion is bypassed, the faculty-trends comparison hits a
previously masked error: the frozen helper does not accept `status_period=True`,
which the real view now supplies. Updating only the expected query count would
therefore leave this test broken. Update its comparison design and verify the
current weekly status/approval semantics before setting a justified page budget.

### Deletion coverage and misleading cancellation instructions

The delete endpoint protects Pending, Approved, and Cancellation Requested
requests. The current page shows cancellation controls for active requests and
deletion controls for terminal requests. The failing loop incorrectly assumes
every status except Pending can be deleted.

The two failed Google-cleanup tests set the request to Approved, so the 409
status guard prevents their Google mocks from running. Using a Completed
fixture in memory makes both tests pass. The missing-connection and
wrong-calendar tests also pass with Completed fixtures, meaning the guards
work when actually reached. Their original Approved fixtures were false
positives: a different earlier guard returned the same 409.

There is a confirmed misleading error string at `apps/students/views.py:216`:
it says cancellation needs faculty approval. The student cancellation endpoint
and existing passing cancellation tests implement immediate cancellation.
Update that message to direct users to cancel first. Preserve the protected
delete behavior and current cancellation workflow.

## Recommended fix order

1. Correct roles/logins and the time/mock fixtures. Keep authorization checks
   intact. Address the schedule navigation assertion separately from its role.
2. Update response schemas, status fixtures, chatbot IDs/text assertions, chart
   and recommendation tests to the current documented features. Preserve their
   privacy, read-only, and isolation assertions.
3. Correct the two misleading user-facing descriptions: approval-date reporting
   and immediate cancellation. Add focused assertions that prevent those
   descriptions contradicting the implemented behavior.
4. Resolve the legacy time-only CSV compatibility question, then test the agreed
   behavior for both faculty and College Head uploads.
5. Repair frozen-helper comparisons and justify page query budgets using the
   captured query breakdown. Keep the existing service budgets and compare
   small/large rosters so a growing-query regression still fails.
6. Rerun affected tests, all school-isolation/registration/invitation tests, and
   the complete local suite. Compare **test names and subtests**, not totals
   alone. Only then reassess the production rollout.

The passing multi-school tests and unchanged failure baseline are useful
evidence, but they do not make an already-red full suite green. No production
rollout was performed or authorized by this diagnosis.

## Complete failing-case index

The companion `test-baselines/diagnosis-2026-10-30.json` maps every failing name
and subtest to the finding above. The table below is generated from the saved
baseline and checked against the fresh run.

| Outcome | Test method and subtest | Diagnosis |
| --- | --- | --- |
| ERROR | `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_fragmented_free_time_does_not_meet_threshold` | Removed availability percentage/chart |
| ERROR | `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_no_records_excluded_from_ranking_but_included_in_percentage` | Removed availability percentage/chart |
| ERROR | `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_only_unscheduled_faculty_and_empty_college` | Removed availability percentage/chart |
| ERROR | `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_overlaps_clipping_and_exact_threshold` | Removed availability percentage/chart |
| ERROR | `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_recurring_and_dated_events_bucket_by_actual_occurrence` | Removed availability percentage/chart |
| ERROR | `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_stale_external_events_do_not_occupy_time_or_qualify_for_ranking` | Removed availability percentage/chart |
| ERROR | `apps.faculty.tests.test_views.FacultyViewTests.test_recurring_event_stays_local_when_google_is_connected` | Old recurrence policy and unconfigured mock |
| ERROR | `apps.faculty.tests.test_views.FacultyViewTests.test_recurring_google_payload_counts_every_matching_weekday` | String time fixture |
| ERROR | `apps.students.tests.test_availability_browser.AvailabilityBrowserTests.test_ties_and_repeated_requests` | Removed student chatbot metric |
| FAIL | `apps.depthead.tests.test_analytics.CollegeAnalyticsTests.test_consultation_summary_status_distribution` | Six-status fixture versus five-status assertion |
| FAIL | `apps.depthead.tests.test_analytics_browser.AnalyticsBrowserTests.test_capacity_honestly_unavailable` | Old College Head chatbot contract |
| FAIL | `apps.depthead.tests.test_analytics_browser.AnalyticsBrowserTests.test_repeated_fetch_reuses_schedule_service_each_time` | Old College Head chatbot contract |
| FAIL | `apps.depthead.tests.test_analytics_browser.AnalyticsBrowserTests.test_scope_ignores_client_college` | Old College Head chatbot contract |
| FAIL | `apps.depthead.tests.test_analytics_browser.AnalyticsBrowserTests.test_widget_only_on_overview` | Old College Head chatbot contract |
| FAIL | `apps.depthead.tests.test_college_analytics_batching.CollegeAnalyticsBatchingTests.test_all_browser_answers_match_frozen_public_helpers (metric='approval_times')` | Approval-date population versus appointment-date population |
| FAIL | `apps.depthead.tests.test_college_analytics_batching.CollegeAnalyticsBatchingTests.test_fixed_query_budget_and_complete_page_parity_at_three_and_fifteen (page='peak_analytics', faculty_count=3)` | Fixed page queries: hourly snapshot |
| FAIL | `apps.depthead.tests.test_college_analytics_batching.CollegeAnalyticsBatchingTests.test_fixed_query_budget_and_complete_page_parity_at_three_and_fifteen (page='peak_analytics', faculty_count=15)` | Fixed page queries: hourly snapshot |
| FAIL | `apps.depthead.tests.test_consultation_topics.ConsultationTopicsTests.test_all_statuses_college_scope_and_scheduled_boundaries` | Six-status fixture versus five-status assertion |
| FAIL | `apps.depthead.tests.test_faculty_trends_batching.FacultyTrendsBatchingTests.test_output_parity_and_fixed_page_queries_at_three_and_fifteen (faculty_count=3)` | Fixed page queries plus incompatible frozen helper |
| FAIL | `apps.depthead.tests.test_faculty_trends_batching.FacultyTrendsBatchingTests.test_output_parity_and_fixed_page_queries_at_three_and_fifteen (faculty_count=15)` | Fixed page queries plus incompatible frozen helper |
| FAIL | `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_charts_distinguish_tiny_zero_and_missing_rates` | Removed availability percentage/chart |
| FAIL | `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_schedule_chart_renders_zero_as_zero_height` | Removed availability percentage/chart |
| FAIL | `apps.depthead.tests.test_schedule_availability.ScheduleAvailabilityTests.test_view_renders_tables_and_caveat` | Removed availability percentage/chart |
| FAIL | `apps.depthead.tests.test_views.DeptheadViewTests.test_ai_endpoint_adds_local_daily_faculty_recommendation` | Old AI recommendation expectation |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_approving_consultation_creates_google_event` | Missing Faculty role in fixture |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_booking_page_renders` | Missing Faculty role in fixture |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_bulk_delete_removes_google_events_when_sync_is_disabled` | Deleted model mutates mock argument |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_calendar_sync_preference_requires_connection_and_can_be_disabled` | Missing Faculty role in fixture |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_csv_none_day_creates_time_only_month_range` | Legacy time-only CSV compatibility gap |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_dashboard_page_renders` | Missing Faculty role in fixture |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_expired_manual_status_defaults_to_available` | Explicit Not Set fallback policy |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_faculty_can_toggle_walk_in_availability` | Missing Faculty role in fixture |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_manual_status_can_be_cleared_back_to_calendar_status` | Missing Faculty role in fixture |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_profile_page_renders` | Missing Faculty role in fixture |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_profile_updates_editable_fields` | Missing Faculty role in fixture |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_reschedule_and_cancel_update_and_delete_google_event` | Missing Faculty role in fixture |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_schedule_page_renders` | Faculty role plus navigation assertion |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_schedule_template_download_has_canonical_csv_headers` | Old CSV template header |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_status_is_derived_from_an_active_system_calendar_event` | Explicit Not Set fallback policy |
| FAIL | `apps.faculty.tests.test_views.FacultyViewTests.test_status_update_persists_status_note_and_history` | Missing Faculty role in fixture |
| FAIL | `apps.students.tests.test_availability_browser.AvailabilityBrowserTests.test_every_answer_scoped_and_read_only` | Expanded student chatbot schema |
| FAIL | `apps.students.tests.test_cancellation.CancellationTests.test_student_cancellation_removes_faculty_card_immediately` | Wrong login for faculty-card check |
| FAIL | `apps.students.tests.test_consultation_deletion.ConsultationDeletionTests.test_calendar_failure_preserves_request` | Approved fixture never reaches calendar operation |
| FAIL | `apps.students.tests.test_consultation_deletion.ConsultationDeletionTests.test_linked_calendar_event_removed` | Approved fixture never reaches calendar operation |
| FAIL | `apps.students.tests.test_consultation_deletion.ConsultationDeletionTests.test_owner_can_delete_deletable_statuses_and_request_disappears (status='approved')` | Active requests deliberately protected from deletion |
| FAIL | `apps.students.tests.test_consultation_deletion.ConsultationDeletionTests.test_owner_can_delete_deletable_statuses_and_request_disappears (status='cancellation_requested')` | Active requests deliberately protected from deletion |
| FAIL | `apps.students.tests.test_views.StudentScheduleTests.test_student_consultation_list_includes_completed_and_excludes_declined_requests` | Declined history now displayed |
| FAIL | `apps.students.tests.test_views.StudentScheduleTests.test_student_schedule_api_returns_faculty_events` | Expanded calendar response schema |
