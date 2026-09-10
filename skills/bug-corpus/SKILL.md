---
name: bug-corpus
description: Turn a confirmed bug into a permanent static detector. Use when a bug is found or fixed, a regression or root cause is discussed, similar bugs must be found elsewhere, a bug class must be prevented, or a Semgrep/CodeQL/Pysa/ast-grep rule is requested. Runs on `uv run bugcorpus`.
---

# bug-corpus
<!-- trace:v1 id=doc.bugcorpus-skill work=WORK-BUG-ZJBDCZZ0 -->

Every confirmed bug must become a permanent deterministic detector, not just a regression test.

## When this applies
<!-- trace:v1 id=doc.bugcorpus-skill-triggers work=WORK-BUG-ZJBDCZZ0 -->

Found/fixed a bug, regression, root cause; asked to prevent a bug class, search for siblings, write a Semgrep/CodeQL/Pysa/ast-grep rule.

## Workflow
<!-- trace:v1 id=doc.bugcorpus-skill-workflow work=WORK-BUG-ZJBDCZZ0 -->

1. Fix the bug first; prove the fix with the repo's normal tests.
2. `uv run bugcorpus learn --title "..."` — captures evidence, ranks families.
3. State symptom vs root cause vs violated invariant (detectors target the invariant).
4. `uv run bugcorpus search <keywords>` — extend a proven detector over a new one.
5. `uv run bugcorpus synthesize BC-NNNNNN` — picks the cheapest adequate engine.
6. Verify: `uv run bugcorpus verify BC-NNNNNN` (positives fire, negatives silent).
7. Attack the detector (rename, alias, move, rephrase), then `uv run bugcorpus scan`.
8. New detectors land in `shadow`; promote to `warning`/`blocking` only on full fixture recall + zero negative false positives.

Do NOT learn typos, formatting, dependency bumps, or style opinions. Never gate a promoted detector on an LLM at scan time.

References: `references/ladder.md`, `references/fixtures.md`, `references/promotion.md`.
