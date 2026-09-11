# BC-000005 hook entrypoints block on terminal stdin

Symptom: hand-run `bugcorpus hooks ...` on a TTY hangs until Ctrl-D.

Root cause: unconditional `sys.stdin.read()` in both hook entrypoints.

Invariant: no piped event means no work — instant silent exit 0.

Protection (rung 0): `test_hooks_never_read_a_terminal` (fake TTY
whose read() raises if touched).
Fixed in PR #23 (merge a623b12).
