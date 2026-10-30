# System Admin verification

The complete local suite uses isolated in-memory SQLite and never connects to staging or production.

| Run | Tests | Failures | Errors |
| --- | ---: | ---: | ---: |
| Before System Admin area | 347 | 39 | 9 |
| After System Admin area | 369 | 39 | 9 |

All 48 failing occurrences match exactly by fully qualified test name, subtest parameters and failure/error outcome. No new failing cases, removed cases or outcome transitions. The adjacent JSON records every failing identity and the full log checksum. The suite remains failing overall.

The original 21-failure/3-error historical baseline predates the current expanded suite. See [multischool-before.md](multischool-before.md) and its JSON for the name-by-name comparison; the extra failures were present before this implementation.

All 22 new System Admin tests passed:

- `apps.systemadmin.tests.test_systemadmin.SystemAdminTests.test_account_edit_does_not_change_school_email_or_role_and_status_preserves_last_admin`
- `apps.systemadmin.tests.test_systemadmin.SystemAdminTests.test_activation_requires_verified_google_and_uses_invited_school_without_domain_rule`
- `apps.systemadmin.tests.test_systemadmin.SystemAdminTests.test_bootstrap_command_preview_conversion_preserves_google_link_and_replacement`
- `apps.systemadmin.tests.test_systemadmin.SystemAdminTests.test_bootstrap_new_account_requires_apply_and_verified_google_first_login`
- `apps.systemadmin.tests.test_systemadmin.SystemAdminTests.test_bootstrap_rejects_ambiguous_identity_and_arbitrary_role_conversion`
- `apps.systemadmin.tests.test_systemadmin.SystemAdminTests.test_both_tabs_render_all_schools_accounts_and_pending_invites`
- `apps.systemadmin.tests.test_systemadmin.SystemAdminTests.test_create_school_requires_domains_normalizes_and_logs_actor`
- `apps.systemadmin.tests.test_systemadmin.SystemAdminTests.test_delivery_failure_keeps_retryable_invite`
- `apps.systemadmin.tests.test_systemadmin.SystemAdminTests.test_django_admin_role_conversion_clears_school_and_guards_last_superadmin`
- `apps.systemadmin.tests.test_systemadmin.SystemAdminTests.test_edit_name_and_replace_last_domain_keeps_code_locked_and_audit`
- `apps.systemadmin.tests.test_systemadmin.SystemAdminTests.test_failed_activation_retains_invite_and_signup_round_trip_rechecks_server_state`
- `apps.systemadmin.tests.test_systemadmin.SystemAdminTests.test_invalid_duplicate_and_empty_domains_do_not_create_partial_school`
- `apps.systemadmin.tests.test_systemadmin.SystemAdminTests.test_invite_any_email_domain_delivers_school_specific_email_and_rejects_collisions`
- `apps.systemadmin.tests.test_systemadmin.SystemAdminTests.test_only_schoolless_active_systemadmin_can_enter_every_endpoint`
- `apps.systemadmin.tests.test_systemadmin.SystemAdminTests.test_pending_invite_edit_deactivate_reactivate_and_resend`
- `apps.systemadmin.tests.test_systemadmin.SystemAdminTests.test_restored_signup_session_activates_only_from_live_server_invite`
- `apps.systemadmin.tests.test_systemadmin.SystemAdminTests.test_school_account_cannot_create_superadmin_invite_or_use_faculty_invite_collision`
- `apps.systemadmin.tests.test_systemadmin.SystemAdminTests.test_school_suspended_between_prelogin_and_save_prevents_activation`
- `apps.systemadmin.tests.test_systemadmin.SystemAdminTests.test_state_changes_require_post_and_csrf`
- `apps.systemadmin.tests.test_systemadmin.SystemAdminTests.test_suspension_and_reactivation_preserve_records_and_block_existing_session`
- `apps.systemadmin.tests.test_systemadmin.SystemAdminTests.test_systemadmin_redirect_bypasses_profile_setup_and_suspended_school`
- `apps.systemadmin.tests.test_systemadmin.SystemAdminTests.test_unverified_google_cancelled_invite_and_suspended_school_cannot_activate`

The School migration tests now restore the latest schema and use the actual applied migration state after a guarded reverse. The allauth tests include real account persistence, verified Google identity association and serialization through a delayed signup.
