# Fixtures — every detector needs all four
<!-- trace:v1 id=doc.bugcorpus-fixtures work=WORK-BUG-ZJBDCZZ0 -->

- positive: MUST trigger (minimized, ~15 lines, not a 400-line module)
- negative: nearby valid code that MUST NOT trigger (e.g. refreshed snapshot)
- adversarial positive: same semantics, different shape (renames, helpers, syntax)
- adversarial negative: looks similar, semantically valid (reacquire after await)

Keep the original production diff under `evidence/` alongside the minimized fixtures.
