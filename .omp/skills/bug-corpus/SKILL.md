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
9. Close the loop in the same session: `uv run bugcorpus promote --auto`,
   open a PR, set `gh pr merge --auto --merge` so green CI merges it.
   Never leave an unlearned fix behind — the stop hook drafts it as proposed.
10. Every confirmed fix ends with a BugCase ID. When no static rule fits,
    record rung 0: the pytest regression test is the detector
    (`source: regression-test`, `detector_status: tested`). A fix with no
    BugCase and no written reason is an unfinished fix.

Do NOT learn typos, formatting, dependency bumps, or style opinions. Never gate a promoted detector on an LLM at scan time. Never create corpus entries from heuristics alone: `proposed` drafts from `learn --auto` carry no invariant until an agent refines them.

## Sharing detectors (community exchange)
<!-- trace:v1 id=doc.bugcorpus-skill-community work=WORK-BUG-ZJBDCZZ0 -->

Detectors are portable. Everything needed is in the CLI — never explore the bugcorpus repo:

  bugcorpus community export <detector-id> --output /tmp/share
  bugcorpus community publish --base community
  bugcorpus community list --ref community
  bugcorpus community install --ref community --detector <id>

Export bundles detector + fixtures + provenance; publish pushes your branch and opens a review PR against the `community` branch. That branch holds only shared detectors (never merge it into main). Imports always land as `shadow`; promote locally only after review.

References: `references/ladder.md`, `references/fixtures.md`, `references/promotion.md`.
