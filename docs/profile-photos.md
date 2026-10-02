# Hybrid profile pictures

## Setup before enabling uploads

Use the existing Supabase project. No extra worker or hosting service is needed. Storage and bandwidth count toward that project's plan limits; this change does not purchase a plan or enable paid features.

1. In Supabase, open **Storage** and create `faculty-photos` with **Public bucket ON**.
2. Create `student-photos` with **Public bucket OFF**. Keep it private.
3. For both buckets, set the maximum file size to 2 MB and the allowed MIME type to `image/webp`. The app accepts JPEG/PNG/WebP, validates the actual file, strips metadata, and uploads only a resized WebP.
4. Do not create anonymous upload/read/list policies for student objects. Django handles access; FacSync does not use Supabase Auth accounts. The server key bypasses RLS, so it must never appear in templates, browser JavaScript, Git, or chat.
5. Copy the project API URL from the project's Connect/API settings (usually `https://PROJECT_REF.supabase.co`). This is not the database host or pooler URL.
6. Get a backend **secret** API key from project API Keys (`sb_secret_...`). A legacy `service_role` key is also supported. An anon/publishable key or database password is not the right credential.
7. Set these in Vercel's Production environment and locally in `.env` if testing locally:

   ```dotenv
   SUPABASE_URL=https://PROJECT_REF.supabase.co
   SUPABASE_SECRET_KEY=YOUR_SERVER_ONLY_SECRET
   SUPABASE_FACULTY_PHOTO_BUCKET=faculty-photos
   SUPABASE_STUDENT_PHOTO_BUCKET=student-photos
   ```

8. Install the updated requirements. Apply the migration **against the intended deployment database** before serving the new code:

   ```powershell
   .\venv\Scripts\python.exe -m pip install -r requirements.txt
   .\venv\Scripts\python.exe manage.py migrate
   ```

   Check that your local environment points to the intended database before running `migrate`. The agent's tests use isolated SQLite and do not apply this migration to Supabase. The current Vercel build command runs deployment checks, not migrations, so pushing this code alone does not add the new database columns.
9. Deploy/redeploy the app so it receives the environment variables and new code. No additional Google OAuth scopes are needed.

Google photos and initials work without Storage configuration. Upload attempts display an explanatory error until it is configured. Existing users get their Google photo on their next Google sign-in.

## Behavior and privacy

- `User.google_photo_url` and `User.uploaded_photo_url` are separate URL fields. Uploaded photo takes precedence, then Google photo, then the existing placeholder. Failed image loads reveal the placeholder.
- Existing `FacultyProfile.photo_url` values are copied by migration 0018. The legacy field is retained for compatibility but is no longer used for display or new uploads. External legacy images are not deleted from their original hosts.
- Faculty upload URLs are public and appear in the public directory, student directory/consultation list, College Head monitoring/manage faculty, Super Admin manage faculty, and the faculty's own profile/navigation.
- Student uploads appear only in their own profile/navigation. HTML contains an owner-protected FacSync image URL, not a permanent public Storage URL. That endpoint checks user ID, student role and active account status before requesting a 60-second signed URL. Responses are `no-store`. Signed URLs are temporary bearer links, so do not share them.
- The student profile is `/student/profile/`; faculty controls are on `/faculty/profile/`.
- Google photos remain hosted by Google. Private Storage settings apply to manual student uploads, not the original Google image URL.
- The server verifies bucket visibility before uploading/signing. Do not later change `student-photos` to public: Supabase itself would expose the objects regardless of application checks.
- Server validates extension, MIME, decoded format, size (2 MiB), pixel count (16 million), and rejects animation. Images are resized within 512 × 512 and re-encoded without original metadata.
- Uploads use unique object names. Replacement/removal/account deletion schedules cleanup after database commit. Failed cleanup logs `profile_photo_cleanup outcome=failed`; there is no background retry worker. An administrator may need to remove orphaned objects in Storage. Keep originals when investigating and only remove objects unreferenced by account records.
- No image bytes are saved in Postgres. Private image signing and uploads use server-only HTTPS requests with bounded timeouts; credentials and response bodies are not logged.

## Deployment smoke checks (use accounts you control)

1. Sign in as a student and faculty member through Google. Confirm photo or initials. Test both invited roles when convenient.
2. Upload a JPEG/PNG/WebP under 2 MB; confirm it overrides Google and persists after navigation. Remove it and check the fallback.
3. Check faculty pictures in monitoring, both Manage Faculty tables, and both directories. Confirm polling keeps the picture.
4. View a faculty upload's direct URL in a private browser window: it should load.
5. Copy the student's `/account/photo/USER_ID/` URL to a signed-out browser or another user's session: it must fail. A direct permanent private Storage URL must also fail without credentials.
6. Verify invalid and oversized files are rejected, and private/student objects never appear in public directory responses.

## References

- https://supabase.com/docs/guides/storage/buckets/fundamentals
- https://supabase.com/docs/guides/getting-started/api-keys
- https://supabase.com/docs/reference/python/storage-from-createsignedurl
