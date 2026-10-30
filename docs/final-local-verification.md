# Multi-school local verification

Verified on October 30, 2026 against the current **unpushed working copy**.
No push, deployment, account conversion, or Supabase operation was performed.
Application code and existing test files were not changed for this verification.

## Result

The multi-school automated verification passed. There are **zero new failing
cases** compared with the deferred baseline.

- **School foundation:** 8 tests passed.
- **Migration and rollback protections:** 5 tests passed.
- **Cross-school isolation:** 22 tests passed.
- **System Admin and invitations:** 22 tests passed.
- **Student registration by domain:** 22 tests passed.
- **Total focused tests: 79 passed, zero failures or errors.**

Those same 79 methods also passed during the full-suite run.

The full suite ran **391 tests**, with **39 failures and 9 errors**. Every failing
test name, subtest parameter set, and outcome matches the saved baseline exactly.
There are no newly failing cases and no removed failing cases. The full command
still exits nonzero because the known failures remain; this is a passing
comparison against the agreed baseline, not an entirely green suite.

Django system checks passed. The migration consistency check reported
**No changes detected**, meaning the current models have no pending changes
missing from migration files. This check does not apply migrations to Supabase.

## Isolation and reproducibility

Both test runs explicitly used `config.settings.test` and separate disposable
in-memory SQLite databases. Tests applied migrations only inside those local
databases, including the forward/backward migration tests.

The verification harness disabled dotenv and decouple credential-file loading,
provided synthetic import-time database settings, used local-memory email, and
blocked Python socket connections and DNS lookups. Python test subprocesses
inherited the guard. A preflight confirmed the network block; the completed
suite contained zero network-guard violations. External provider behavior was
mocked rather than exercised live.

Temporary harness files, logs, and detailed results are in the ignored folder
`.staging-backups/final-local-verification/`:

- `checks.log`: Django checks and migration consistency.
- `focused.log` and `focused-results.json`: the 79 feature tests.
- `full.log` and `full-results.json`: the complete suite.

The portable evidence is
[final-local-verification.json](test-baselines/final-local-verification.json).
It records the baseline comparison, individual failing cases, the focused test
inventory, and hashes of application/configuration/template source files.
Hashes identify the working files tested, since the changes are not committed.

The test labels were:

```text
apps.core.tests.test_schools
apps.core.tests.test_school_migration
apps.core.tests.test_school_isolation
apps.systemadmin.tests.test_systemadmin
apps.core.tests.test_student_domains
```

The underlying Django commands are `check`, `makemigrations --check --dry-run`,
the focused test labels, and the full test suite, each with
`--settings=config.settings.test`. The temporary harness additionally supplies
credential-file isolation, the network guard, and machine-readable results.

## Next step

Proceed to the manual staging checks: second-school setup, Super Admin invite
and Google activation, student domain registration and school-specific college
selection, cross-school access attempts, and suspension/reactivation.

Local automated verification does not verify a deployed environment, live
Google/email delivery, or production database state. The successful earlier
production-copy migration rehearsal remains separate evidence. No production
rollout is authorized by this report.
