# School foundation verification

Local in-memory SQLite only. Staging and production were not accessed by this suite.

| Run | Tests | Failures | Errors |
| --- | ---: | ---: | ---: |
| Before School changes | 312 | 39 | 9 |
| After School changes | 325 | 39 | 9 |

All 48 failing occurrences have exactly the same fully qualified test name, subtest parameters and outcome as the captured baseline. No new failing cases, removed failing cases or failure/error transitions.

All 13 new School foundation/migration tests passed; the six staging seed tests also passed. Historical comparisons against the requested 21-failure/3-error baseline remain documented in `multischool-before.md`.

## Passing new tests

- `apps.core.tests.test_schools.SchoolFoundationTests.test_adnu_is_created_without_domain_or_account_promotion`
- `apps.core.tests.test_schools.SchoolFoundationTests.test_code_is_locked_and_queryset_edits_cannot_bypass_audit`
- `apps.core.tests.test_schools.SchoolFoundationTests.test_college_names_codes_and_generation_are_per_school`
- `apps.core.tests.test_schools.SchoolFoundationTests.test_domain_removal_and_rename_are_audited`
- `apps.core.tests.test_schools.SchoolFoundationTests.test_domains_normalize_validate_and_are_unique_between_schools`
- `apps.core.tests.test_schools.SchoolFoundationTests.test_name_and_suspension_edits_record_actor_time_old_and_new`
- `apps.core.tests.test_schools.SchoolFoundationTests.test_only_schoolless_active_system_admin_can_edit`
- `apps.core.tests.test_schools.SchoolFoundationTests.test_schools_and_history_cannot_be_deleted_or_rewritten`
- `apps.core.tests.test_school_migration.SchoolMigrationTests.test_faculty_college_disagreement_is_not_silently_repaired`
- `apps.core.tests.test_school_migration.SchoolMigrationTests.test_forward_backfill_and_reverse_preserve_records_roles_and_manifest`
- `apps.core.tests.test_school_migration.SchoolMigrationTests.test_rollback_refuses_after_domain_assignment`
- `apps.core.tests.test_school_migration.SchoolMigrationTests.test_rollback_refuses_when_a_second_school_exists`
- `apps.core.tests.test_school_migration.SchoolMigrationTests.test_unresolved_college_refuses_without_partial_backfill`

The adjacent JSON contains exact failing identities for subsequent comparisons. Full tracebacks remain in the ignored root `multischool-school-phase-tests.log`.
