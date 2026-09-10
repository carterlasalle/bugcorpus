# Bug Corpus — design
<!-- trace:v1 id=doc.bugcorpus-design work=WORK-BUG-ZJBDCZZ0 -->


## Problem
<!-- trace:v1 id=doc.bugcorpus-problem work=WORK-BUG-ZJBDCZZ0 -->

Fixed bugs regress as bug *classes*: the fix ships as a one-off patch with
no permanent class-level detector. See `docs/specs/bug-corpus.md`.

## Approach
<!-- trace:v1 id=doc.bugcorpus-approach work=WORK-BUG-ZJBDCZZ0 -->

Compile `confirmed bug + evidence + fix` into a promoted deterministic
detector: BugCase → minimized reproducer → violated invariant → semantic
signature → cheapest adequate engine → adversarial evaluation → promotion
(`shadow → warning → blocking`). Full pipeline in README “Real workflow”.

## Layers
<!-- trace:v1 id=doc.bugcorpus-layers work=WORK-BUG-ZJBDCZZ0 -->

1. **Corpus** (`.bugcorpus/corpus/`, `families/`): records + lineage.
   Families are independent of cases; detectors protect families.
2. **Synthesis/evaluation** (`synthesizer.py`, `verifier.py`): evidence packs,
   ladder recommendation, fixture + adversarial metrics. `verify` ignores
   baselines by design.
3. **Scanner** (`engines.py`, `scanner.py`): subprocess adapters normalizing
   to one Finding schema (SARIF export-only). `scan` honors baselines.
   Crashes are `detector-error`, never clean.
4. **Agents** (`skills/`, `adapters/`, `mcp_server.py`): one canonical skill,
   thin per-harness adapters over the CLI. See ADR-001.
5. **CI** (`.github/workflows/bugcorpus.yml`): `verify` + `pr` scan per PR,
   `full` on schedule. Blocking findings/errors fail the build.

## Key decisions
<!-- trace:v1 id=doc.bugcorpus-decisions work=WORK-BUG-ZJBDCZZ0 -->

- ADR-001 bare-checkout adapters; ADR-002 subprocess detector protocol;
  ADR-003 lineage-merged fixtures; ADR-004 TraceLayer scope.
- Fingerprints exclude line numbers (stable across movement).
- Lexical matching is tokenize-aware (comments/strings masked).
- Reassignment from any source clears snapshot-staleness (v1 model).

## Non-goals
<!-- trace:v1 id=doc.bugcorpus-nongoals work=WORK-BUG-ZJBDCZZ0 -->

LLM-gated scanning, a markdown bug diary, duplicate generic linting,
marketplace/plugin distribution (revisit per ADR-001).
