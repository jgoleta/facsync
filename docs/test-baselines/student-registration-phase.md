# Student domain registration verification

The full local suite uses isolated in-memory SQLite and never connects to staging or production.

| Run | Tests | Failures | Errors |
| --- | ---: | ---: | ---: |
| Before student domain registration | 369 | 39 | 9 |
| After student domain registration | 391 | 39 | 9 |

All 48 failing occurrences match exactly by fully qualified test name, subtest parameters and failure/error outcome. No new failing cases, removed cases or outcome transitions. The adjacent JSON records every failing identity and the log checksum. The full suite remains failing overall.

The original historical baseline was 21 failures and 3 errors on a smaller suite. Its name-by-name comparison is preserved in [multischool-before.md](multischool-before.md) and its JSON; the additional failures were present before multi-school implementation and remain unchanged in this phase.

All 22 new student domain registration tests passed:

- `apps.core.tests.test_student_domains.StudentDomainRegistrationTests.test_adnu_uses_system_admin_assigned_domain`
- `apps.core.tests.test_student_domains.StudentDomainRegistrationTests.test_case_normalization_and_multiple_explicit_domains_choose_same_school`
- `apps.core.tests.test_student_domains.StudentDomainRegistrationTests.test_delayed_signup_serialization_preserves_and_revalidates_school`
- `apps.core.tests.test_student_domains.StudentDomainRegistrationTests.test_domain_reassigned_during_signup_does_not_silently_change_school`
- `apps.core.tests.test_student_domains.StudentDomainRegistrationTests.test_domain_removed_during_signup_is_rechecked_at_save`
- `apps.core.tests.test_student_domains.StudentDomainRegistrationTests.test_existing_account_is_not_recreated_or_moved_by_registration`
- `apps.core.tests.test_student_domains.StudentDomainRegistrationTests.test_existing_student_login_retains_school_after_domain_change`
- `apps.core.tests.test_student_domains.StudentDomainRegistrationTests.test_failed_social_account_save_rolls_back_student_creation`
- `apps.core.tests.test_student_domains.StudentDomainRegistrationTests.test_forged_school_in_serialized_signup_cannot_override_domain`
- `apps.core.tests.test_student_domains.StudentDomainRegistrationTests.test_invites_still_activate_before_student_domain_rules`
- `apps.core.tests.test_student_domains.StudentDomainRegistrationTests.test_non_edu_addresses_get_exact_institutional_only_message`
- `apps.core.tests.test_student_domains.StudentDomainRegistrationTests.test_profile_offers_own_colleges_and_rejects_foreign_college_and_forged_school`
- `apps.core.tests.test_student_domains.StudentDomainRegistrationTests.test_register_page_renders_both_exact_messages`
- `apps.core.tests.test_student_domains.StudentDomainRegistrationTests.test_removed_assigned_domain_no_longer_accepts_registration`
- `apps.core.tests.test_student_domains.StudentDomainRegistrationTests.test_same_college_code_is_selected_in_student_school_and_profile_completes`
- `apps.core.tests.test_student_domains.StudentDomainRegistrationTests.test_school_suspended_between_callback_and_save_is_rechecked`
- `apps.core.tests.test_student_domains.StudentDomainRegistrationTests.test_signup_form_cannot_substitute_verified_google_email`
- `apps.core.tests.test_student_domains.StudentDomainRegistrationTests.test_subdomain_requires_explicit_assignment_and_suffix_lookalike_does_not_match`
- `apps.core.tests.test_student_domains.StudentDomainRegistrationTests.test_suspended_school_is_rejected_before_account_creation`
- `apps.core.tests.test_student_domains.StudentDomainRegistrationTests.test_unregistered_edu_domain_gets_exact_unregistered_message`
- `apps.core.tests.test_student_domains.StudentDomainRegistrationTests.test_unverified_missing_email_and_non_google_identity_are_rejected`
- `apps.core.tests.test_student_domains.StudentDomainRegistrationTests.test_verified_institutional_signup_persists_school_student_role_and_google_identity`

Existing registration and photo-signup fixtures now use verified identities and an explicitly assigned institutional domain. Their role, activation and photo assertions remain intact. All System Admin and prior school isolation tests also pass. PostgreSQL staging verification is documented in [student-registration.md](../student-registration.md).
