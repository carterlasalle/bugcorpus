# BC-000003 doctor/scan hang on unenrolled root

Symptom: `bugcorpus doctor` outside any enrolled repo hangs (cancelled
after 18s in $HOME).

Root cause: `store.root()` falls back to cwd; `collect_files` then runs
`**/*.py` over the arbitrary tree.

Invariant: file collection never executes without a corpus dir.

Protection (rung 0): `test_unenrolled_roots_never_glob` —
unenrolled roots yield `[]` and a 'not enrolled' report.
Fixed in PR #22 (merge e7a1210).
