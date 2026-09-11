# BC-000004 show/related/synthesize leak raw Errno on missing BugCase

Symptom: missing records print `error: [Errno 2] No such file or
directory: ...bug.yaml`.

Root cause: `store.load_bug` OSError reached main()'s generic handler.

Invariant: missing records surface as named errors, never raw OSErrors.

Protection (rung 0): `test_bug_commands_report_enrollment_not_errno`
plus `test_show_unknown_id_names_the_bug` and the updated
`test_cli_surfaces_errors_loudly`.
Fixed in PR #23 (merge a623b12).
