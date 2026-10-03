# Conversational helper updates — October 3, 2026

Student, faculty and College Head preset helpers now use readable introductions,
dates, durations, counts, empty messages, and destination-specific links. Results
still come from the existing calculations; these helpers do not generate AI text
or refresh faculty status. Names and announcement messages render as text, never
HTML. Announcement messages keep their original content and line breaks, with
audience/posted/expiry details displayed separately.

- Student answers remain limited to the student's college. Available-now uses
  the latest saved Available status and respects the saved college closure flag.
- Faculty consultation results remain limited to the signed-in faculty member's
  own records. The source link now targets `/faculty/dashboard/#consultation-requests`.
- College Head answers remain college-scoped. Question groups retain their order:
  Schedules, Consultations, Faculty, Students, Department updates.
- Department announcements retain role/audience, college and expiry filters.
  Open colleges no longer show obsolete closure reasons/dates. Missing closure
  records are described as missing, not as verified opening hours.
- Reporting windows and aggregation rules are unchanged except the shared daily
  schedule-availability threshold described below. Peak-hour replies describe
  hourly buckets; submission-month answers still use submission timestamps, while
  topic/student-frequency answers use scheduled consultation dates.

## Two-hour schedule rule

`MIN_FREE_MINUTES` is now 120: a faculty member needs a single uninterrupted gap
of at least two hours within 8 AM–5 PM to count in daily schedule availability.
Two separate one-hour gaps do not qualify. Faculty without recorded schedules
still count as fully unscheduled, as approved. This is an estimate, not a live
Available status, and it does not specifically remove or detect lunch breaks.

This updates the Faculty Trends daily chart, College Head daily availability
answer, student best-day answer, calculated best-day recommendations, and the
anonymous schedule summary sent to Gemini. Total-open-time rankings, live status
badges, consultation metrics and Calendar synchronization are unchanged.

Existing saved Gemini prose follows its existing refresh schedule. New generations
receive both the revised aggregates and an explicit explanation of the two-hour
rule. No forced regeneration or database edits were performed.

## Deployment and validation

No new environment variables, dependencies or database migrations are required.
Deploy the code and refresh the dashboard; the helper assets have updated cache
versions. No live deployment or browser visual check was performed by the agent.

Focused Django tests cover readable replies, actual month/date scopes, missing
data versus zero, ties, role/college/faculty isolation, announcement audiences,
closure state and two-hour thresholds (including 119 minutes and fragmented gaps).
Node tests exercise paragraph/list/announcement rendering, text-only messages,
same-origin source links, the consultation anchor and error responses.

Final results: baseline 294 tests, 27 failures and 2 errors; after changes 310
tests, the same 27 failures and 2 errors (matched by test identity). No new
failing tests. All 42 focused backend tests and 6 frontend tests passed.
