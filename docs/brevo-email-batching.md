# Brevo HTTPS email on Vercel

Email remains synchronous. There are no threads, queues, workers, migrations,
or new paid services. Existing Brevo sending allowances still apply.

## Configuration

Set these in the intended Vercel environment, then redeploy:

```text
EMAIL_BACKEND=apps.core.email_backends.BrevoEmailBackend
BREVO_API_KEY=<Brevo API key, not the SMTP password>
BREVO_BATCH_SIZE=100
```

Keep `DEFAULT_FROM_EMAIL` set to a sender authorized in Brevo and `SITE_URL`
set to the public deployment URL. Never commit the API key or include it in
screenshots. No `RENDER` switch is used. SMTP remains the default when
`EMAIL_BACKEND` is not changed. To roll back, restore
`django.core.mail.backends.smtp.EmailBackend` and redeploy with the existing
SMTP credentials.

## Behavior

Single-message calls keep Django's `send_messages()` contract. Announcements
and closure notices use an explicit `send_personalized_batch()` method only
when the selected backend provides it. Other backends keep the existing
individual-send behavior, including recipient-level exception handling.

Every batch version has exactly one recipient and separately rendered HTML
and text. There is no shared To/CC/BCC list. Requests use up to 100 versions by
default (configurable from 1 to 1000), sharing an HTTPS session across chunks.
The existing audience/college/active-account filters are preserved. Student-only
announcements send no emails; closure notices send on the open-to-closed transition.

The batch result counts accepted, rejected, and unknown submissions. Complete
201 responses with one message ID per version count as provider acceptance,
not inbox delivery. Explicit 4xx responses except 408 are rejected. Timeouts,
5xx responses, redirects, and malformed acceptance responses are unknown.
There are no retries or fallback resends after provider calls; this avoids
duplicating emails when acceptance is uncertain. A failed chunk does not stop
later chunks. Input validation happens before any batch is submitted, so invalid
input aborts that batch invocation. HTTP timeouts are 5 seconds to connect and
20 seconds to read, per call, not an overall request deadline.

Unsupported attachments, custom headers, alternative MIME types and multiple
reply-to addresses fail explicitly. Announcement creation still succeeds when
email fails, as before. Logs contain counts/statuses and elapsed time, not email
bodies, recipient addresses, API keys or raw provider responses. Successful
batch summaries use INFO logging; production log configuration may need to
enable `apps.core.services` INFO to display those summaries.

Provider limits: 1000 versions/request, 2000 recipients/request, 99 recipients
per version. This implementation uses only one recipient per version. Brevo's
batch guide lists 100 requests/minute and 6000/hour; account quota and applicable
rate limits still apply. No automatic delays or retries on HTTP 429.

References:
- https://developers.brevo.com/docs/batch-send-transactional-emails
- https://developers.brevo.com/reference/send-transac-email

## Vercel before measurement (user-collected, September 28, 2026)

Endpoint: `/depthead/announcements/create/`. Two active faculty recipients,
faculty audience; user confirmed email receipt. Measurements include the entire
HTTP request, not just email submission, and do not establish cold-start status.

| Attempt | Total seconds | Waiting/TTFB seconds | Note |
| --- | ---: | ---: | --- |
| 1 | 3.90 | 3.90 | HTTP 200, success response provided |
| 2 | 3.84 | 3.84 | |
| 3 | 3.78 | 3.77 | |
| 4 | 3.72 | 3.72 | |
| 5 | 3.58 | 3.58 | Announcement content accidentally changed |

All five: median 3.78 s, mean 3.764 s. Excluding changed-content run:
median 3.81 s, mean 3.81 s. Retain both comparisons rather than silently
discarding the shortest run.

## After measurement (pending deployment)

Repeat five browser Network/Timing measurements on Vercel with the same two
controlled recipients, same announcement content and audience, browser and
network conditions, and no throttling. Wait for each request before sending
the next. Record deployment revision, total duration, TTFB, HTTP/JSON success,
and receipt in both inboxes. Never include cookies, CSRF headers or an unredacted
HAR. Do not send benchmark announcements to ordinary faculty accounts.

For these two recipients, the expected change is two SMTP connections to one
HTTPS batch request, still delivering two separate emails. Do not infer a speedup
from mocked tests. Compare median/mean before and after only after collecting
the deployed timings. Provider receipt should be checked separately from action
success, because action success does not guarantee email acceptance.

## Local validation results

- Fresh before suite: 191 tests, 21 failures / 3 errors.
- After suite: 216 tests, 21 failures / 3 errors.
- All 24 failing test identities and FAIL/ERROR classifications match both the fresh baseline and historical `baseline-tests.log`. No new or resolved failures.
- Focused backend/batch/existing announcement suite: 28 tests passed.
- Both Node browser suites: 10 tests passed.
- Local logs: `email-batch-before.log`, `email-batch-after.log`, `email-batch-focused.log`, `email-batch-browser.log` (ignored by Git).
- Python tests use isolated SQLite test settings and mocked email transport; no live email was sent by these tests.

Unchanged failure identities:

```text
ERROR: apps.faculty.tests.test_views.FacultyViewTests.test_clear_schedule_deletes_only_uploaded_preview_events
ERROR: apps.faculty.tests.test_views.FacultyViewTests.test_recurring_event_stays_local_when_google_is_connected
ERROR: apps.faculty.tests.test_views.FacultyViewTests.test_recurring_google_payload_counts_every_matching_weekday
FAIL: apps.depthead.tests.test_views.DeptheadViewTests.test_depthead_can_upload_schedule_for_same_college_faculty
FAIL: apps.faculty.tests.test_unified_preview.UnifiedPreviewTests.test_mixed_uploads_append_preview_and_delete_only_displayed_rows
FAIL: apps.faculty.tests.test_views.FacultyViewTests.test_approving_consultation_creates_google_event
FAIL: apps.faculty.tests.test_views.FacultyViewTests.test_booking_page_renders
FAIL: apps.faculty.tests.test_views.FacultyViewTests.test_calendar_sync_preference_requires_connection_and_can_be_disabled
FAIL: apps.faculty.tests.test_views.FacultyViewTests.test_csv_none_day_creates_time_only_month_range
FAIL: apps.faculty.tests.test_views.FacultyViewTests.test_csv_schedule_upload_appends_schedule_and_returns_preview
FAIL: apps.faculty.tests.test_views.FacultyViewTests.test_dashboard_page_renders
FAIL: apps.faculty.tests.test_views.FacultyViewTests.test_expired_manual_status_defaults_to_available
FAIL: apps.faculty.tests.test_views.FacultyViewTests.test_faculty_can_notify_and_complete_walk_in_student
FAIL: apps.faculty.tests.test_views.FacultyViewTests.test_faculty_can_toggle_walk_in_availability
FAIL: apps.faculty.tests.test_views.FacultyViewTests.test_invalid_csv_does_not_delete_existing_schedule
FAIL: apps.faculty.tests.test_views.FacultyViewTests.test_manual_status_can_be_cleared_back_to_calendar_status
FAIL: apps.faculty.tests.test_views.FacultyViewTests.test_profile_page_renders
FAIL: apps.faculty.tests.test_views.FacultyViewTests.test_profile_updates_editable_fields
FAIL: apps.faculty.tests.test_views.FacultyViewTests.test_reschedule_and_cancel_update_and_delete_google_event
FAIL: apps.faculty.tests.test_views.FacultyViewTests.test_schedule_page_renders
FAIL: apps.faculty.tests.test_views.FacultyViewTests.test_schedule_template_download_has_canonical_csv_headers
FAIL: apps.faculty.tests.test_views.FacultyViewTests.test_status_is_derived_from_an_active_system_calendar_event
FAIL: apps.faculty.tests.test_views.FacultyViewTests.test_status_update_persists_status_note_and_history
FAIL: apps.students.tests.test_views.StudentScheduleTests.test_student_schedule_api_returns_faculty_events
```
