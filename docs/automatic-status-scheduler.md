# Automatic status scheduler

This feature checks saved schedules and approved consultations, expires temporary
manual statuses, and delivers automatic-status emails. It does not fetch Google
Calendar data, send announcements, or process other email types.

## Behavior

With `AUTOMATIC_STATUS_EMAIL_QUEUE_ENABLED=False` (the default), status emails
continue to be sent during the triggering request, after its database transaction
commits. Nothing is scheduled merely by deploying these files.

When enabled, ordinary status refreshes atomically save status/history, create
bell notifications, and add one pending email per subscriber. Opening a page does
not wait for these automatic emails. The manual Update status endpoint (including
the explicit switch to calendar mode) still sends immediately after commit.

The scheduler checks active faculty in automatic mode and expired temporary
manual overrides. It preserves unexpired manual overrides. No active event means
Not Set, not Available. Existing status calculation semantics remain unchanged.
Calendar synchronization's existing error fallback still assigns the manual
status without creating a notification; its database update now uses the current
stored manual value rather than a stale in-memory value.

All normal refresh paths lock and re-read the faculty row before recording a
transition. History, bell notifications, and pending deliveries are committed
together. A page can discover a change before the scheduler without losing the
email. This adds database transaction/locking work; it does not retain the earlier
eight-query dashboard measurement as an invariant.

## Delivery and limits

- A database lease excludes overlapping scheduled invocations for 120 seconds.
- Up to 10 eligible faculty are checked per invocation, using a rotating cursor.
- Checks stop starting after approximately 10 seconds. Email work starts only
  before 15 seconds, with up to 30 private single-recipient message versions in
  one Brevo HTTPS request (2-second connect / 5-second read timeout).
- Scheduled transactions use PostgreSQL lock and statement timeouts. These are
  defensive limits, not a hard end-to-end 30-second guarantee: database connection
  setup, network delays, and provider behavior can still cause a timeout.
- Unfinished pending work waits for later invocations. As faculty/subscriber
  counts grow, a full sweep or email backlog can take multiple intervals.
- Only rate limiting (HTTP 429) and connect timeouts are automatically retried,
  at most three attempts, with delayed retries.
- Read timeouts, ambiguous transport/server responses, malformed acceptance
  responses, and abandoned sending claims become **unknown** and are not retried
  automatically. This avoids blindly duplicating potentially accepted emails;
  exactly-once external delivery is not guaranteed.
- A 201 response with one message ID per recipient means **accepted by Brevo**,
  not confirmed inbox delivery. Definitive failures are recorded as failed.
- Unsubscribed, inactive, deleted, or changed-email recipients are not sent stale
  queued mail. Deleting the recipient or related history/faculty cascades to the
  corresponding delivery records.
- Delivery snapshots remain until their related records are removed. There is
  no automatic retention purge in this change.
- An outage does not reconstruct transitions that occurred entirely between
  checks. The scheduler evaluates the current time. Queued detected transitions
  are retained even if a newer status is recorded before delivery.

## Deployment steps

1. Back up the database using the project's normal procedure. Apply the additive
   migration against the intended database before serving the new code:

   ```powershell
   .\venv\Scripts\python.exe manage.py migrate
   ```

   Your local `.env` must point to the intended database. This command was **not**
   run against Supabase by the implementation agent.

2. In Vercel's **production** environment variables configure:

   ```ini
   AUTOMATIC_STATUS_EMAIL_QUEUE_ENABLED=True
   STATUS_SCHEDULER_SECRET=<a-new-random-secret>
   BREVO_API_KEY=<your-existing-server-side-Brevo-key>
   DEFAULT_FROM_EMAIL=<your-verified-sender>
   ```

   The scheduled sender uses Brevo HTTPS regardless of `EMAIL_BACKEND`; other
   email flows retain their configured backend. Never put the Brevo key in
   cron-job.org or send secrets in chat.

   Generate the separate scheduler secret locally:

   ```powershell
   .\venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

3. Prepare a disabled cron-job.org job, deploy the migrated application with the
   variables above, then test and enable the job promptly:

   - URL: `https://facsync.vercel.app/faculty/internal/automatic-status/`
   - Method: **POST** (not the default GET)
   - Header name: `Authorization`
   - Header value: `Bearer <the-same-STATUS_SCHEDULER_SECRET>`
   - Schedule: every five minutes, all days; do not restrict to office hours if
     you need manual expiry and evening events handled.
   - Enable failure notifications. Do not configure this in `vercel.json`; the
     external service supplies the schedule.

4. First test with controlled faculty/subscriber accounts. A manual job execution
   is real: it can change due statuses and send pending emails. Verify successful
   response counts and inspect Django admin > Faculty > Status email deliveries.
   Do not post response payloads containing personal data or authorization headers.

The endpoint returns 401 for incorrect/missing credentials, 405 for GET, 503 when
disabled/unconfigured or processing has failed, and 200 on a completed run or an
already-running skip. Known temporary email rejections can return 200 with pending
work for retry; monitor delivery states as well as HTTP status.

## Monitoring and rollback

Django admin exposes read-only delivery outcomes and scheduler lease/cursor state.
Investigate failed/unknown records using Brevo delivery logs before considering
any manual resend. There is deliberately no blind retry button for unknown mail.

To stop scheduled activity, disable the cron job and set the queue flag to False,
then redeploy. Pending emails remain stored and resume when re-enabled; disabling
does not drain them. Page-triggered status emails revert to immediate behavior.
Do not delete the additive tables while this code is deployed.

The external scheduler adds 8,640 requests per 30 days at five-minute intervals.
No paid worker or new dependency is required. Vercel compute, database, and Brevo
allowances still apply; account usage and deployed runtime have not been verified
by local tests. Existing Google profile/calendar integrations are unaffected.
