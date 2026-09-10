# ADR-003: Detector fixture suites merge lineage from caught BugCases

<!-- trace:v1 id=ADR-003 work=WORK-BUG-ZJBDCZZ0 -->

Date: 2026-09-10. Status: accepted.

## Context
<!-- trace:v1 id=doc.adr-003-context work=WORK-BUG-ZJBDCZZ0 -->

A family detector must be strengthenable for a new BugCase without silently
dropping old ones (`stale-state-after-await-v1` later extended for a
helper-propagated variant). Detector-owned fixture dirs alone cannot enforce
that; authors forget to copy old fixtures.

## Decision
<!-- trace:v1 id=doc.adr-003-decision work=WORK-BUG-ZJBDCZZ0 -->

`verify` builds each detector's suite as its own `fixtures/` plus the
fixtures of every BugCase in its manifest `catches` list (bare
`adversarial/` dirs split by filename polarity). Corpus fixtures are
therefore the single source of truth; extending a detector means appending
`catches` entries, and verification reruns all historical fixtures plus
adversarial recall gating for `blocking` promotion.

## Alternatives considered
<!-- trace:v1 id=doc.adr-003-alternatives-considered work=WORK-BUG-ZJBDCZZ0 -->

- Copying fixtures per detector version: rejected — drift and silent drops.
- One detector per BugCase: rejected — contradicts family-based protection.

## Consequences
<!-- trace:v1 id=doc.adr-003-consequences work=WORK-BUG-ZJBDCZZ0 -->

`catches` is load-bearing: an incorrect entry silently widens a suite.
`validate_corpus` plus `verify` surface unreadable records, and review must
treat `catches` edits as semantic changes.
