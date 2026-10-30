# School scoping verification

The local suite uses isolated in-memory SQLite and never connects to staging or production.

| Run | Tests | Failures | Errors |
| --- | ---: | ---: | ---: |
| Before scoping (School foundation) | 325 | 39 | 9 |
| After scoping | 347 | 39 | 9 |

All 48 failing occurrences match exactly by fully qualified test name, subtest parameters and failure/error outcome. There are no new failures or transitions. The adjacent JSON records the complete identities and log checksum. Existing single-school test fixtures explicitly select ADNU; the new isolation tests deliberately use two schools sharing the CCS college code.

The original 21-failure/3-error historical baseline predates the current 312-test baseline. Its name-by-name comparison remains in [multischool-before.md](multischool-before.md) and its JSON; the additional failures were present before this implementation. This suite remains failing overall and is not a clean test run.

All 22 new isolation tests passed:

- `apps.core.tests.test_school_isolation.SchoolIsolationTests.test_ai_cache_fresh_and_stale_fallback_cannot_cross_schools`
- `apps.core.tests.test_school_isolation.SchoolIsolationTests.test_ai_refresh_writes_only_selected_school_and_missing_cache_does_not_fallback`
- `apps.core.tests.test_school_isolation.SchoolIsolationTests.test_all_three_chatbots_stay_in_the_callers_school`
- `apps.core.tests.test_school_isolation.SchoolIsolationTests.test_analytics_services_require_explicit_school_and_reject_context_switch`
- `apps.core.tests.test_school_isolation.SchoolIsolationTests.test_announcements_and_status_notifications_select_only_same_school_recipients`
- `apps.core.tests.test_school_isolation.SchoolIsolationTests.test_college_head_pages_apis_and_guessed_schedule_ids`
- `apps.core.tests.test_school_isolation.SchoolIsolationTests.test_deferred_email_revalidates_school_equality_and_suspension`
- `apps.core.tests.test_school_isolation.SchoolIsolationTests.test_faculty_cannot_read_or_mutate_foreign_events_consultations_or_queues`
- `apps.core.tests.test_school_isolation.SchoolIsolationTests.test_foreign_notification_ids_and_private_photos_are_not_accessible`
- `apps.core.tests.test_school_isolation.SchoolIsolationTests.test_forged_cross_school_relations_and_context_leakage_are_rejected`
- `apps.core.tests.test_school_isolation.SchoolIsolationTests.test_invitation_identity_checks_do_not_reassign_other_schools_users`
- `apps.core.tests.test_school_isolation.SchoolIsolationTests.test_invite_activation_inherits_school_and_failed_save_keeps_invite`
- `apps.core.tests.test_school_isolation.SchoolIsolationTests.test_invites_and_new_colleges_inherit_sender_school_and_ignore_forged_school`
- `apps.core.tests.test_school_isolation.SchoolIsolationTests.test_missing_school_and_suspended_existing_sessions_are_blocked_for_each_role`
- `apps.core.tests.test_school_isolation.SchoolIsolationTests.test_only_system_admin_can_browse_across_schools_in_database_admin`
- `apps.core.tests.test_school_isolation.SchoolIsolationTests.test_profile_colleges_and_admin_role_edit_cannot_be_forged`
- `apps.core.tests.test_school_isolation.SchoolIsolationTests.test_public_dashboard_has_interim_login_and_school_scope`
- `apps.core.tests.test_school_isolation.SchoolIsolationTests.test_student_cannot_cancel_or_delete_guessed_foreign_consultation`
- `apps.core.tests.test_school_isolation.SchoolIsolationTests.test_student_directory_schedule_booking_walkins_and_subscriptions`
- `apps.core.tests.test_school_isolation.SchoolIsolationTests.test_student_management_requires_role_and_scopes_both_list_and_delete`
- `apps.core.tests.test_school_isolation.SchoolIsolationTests.test_superadmin_pages_and_guessed_management_ids`
- `apps.core.tests.test_school_isolation.SchoolIsolationTests.test_suspended_school_blocks_existing_google_login_and_invite_activation`
