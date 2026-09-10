# Bug Corpus
<!-- trace:v1 id=doc.bugcorpus-readme work=WORK-BUG-ZJBDCZZ0 -->

A compiler from historical bugs into permanent deterministic detectors.
A fixed bug becomes structured evidence (`BugCase` → minimized reproducer →
violated invariant → semantic signature → detector candidates → adversarial
evaluation → promoted detector), and CI runs every promoted detector without an LLM.

## Quickstart
<!-- trace:v1 id=doc.bugcorpus-readme-quickstart work=WORK-BUG-ZJBDCZZ0 -->

Prerequisites: Python 3.11+, `uv`.

```sh
uv sync
uv run bugcorpus doctor     # tool capabilities
uv run bugcorpus verify     # validate corpus + detector fixtures
uv run bugcorpus scan       # run promoted detectors (add --json for machines)
```

## Real workflow
<!-- trace:v1 id=doc.bugcorpus-readme-workflow work=WORK-BUG-ZJBDCZZ0 -->

```sh
# 1. fix the bug, prove the fix with normal tests
uv run bugcorpus learn --title "stale snapshot reused after await"
# 3. state symptom vs root cause vs violated invariant in .bugcorpus/corpus/BC-NNNNNN/bug.yaml
# 4. check for siblings before inventing a detector
uv run bugcorpus search "snapshot await stale"
uv run bugcorpus related BC-000001
# 5. synthesize (cheapest adequate engine) + verify + attack + scan
uv run bugcorpus synthesize BC-000001
uv run bugcorpus verify BC-000001
uv run bugcorpus scan --all
# 6. promote explicitly: shadow → warning → blocking
uv run bugcorpus promote stale-state-after-await-v1 --to warning
```

Detectors that fail fixture verification can never be `blocking` — `promote`
enforces 100% positive recall and zero negative false positives.

## Architecture
<!-- trace:v1 id=doc.bugcorpus-readme-architecture work=WORK-BUG-ZJBDCZZ0 -->

Five layers; the first three work with no agent installed:

1. **Corpus** (`.bugcorpus/corpus/BC-NNNNNN/`, `families/`) — bug cases with
   symptom/root-cause/invariant kept distinct, semantic signatures, lineage.
2. **Synthesis/evaluation** (`bugcorpus/synthesizer.py`, `verifier.py`) — evidence
   packs, cheapest-engine ladder, fixture + adversarial evaluation, metrics.
3. **Scanner runtime** (`engines.py`, `scanner.py`) — engine adapters
   (existing, lexical, ast-grep, semgrep, semgrep-taint, codeql, pysa, custom),
   profiles (`fast`/`pr`/`full`), baselines, stable fingerprints, SARIF export.
4. **Agent integration** (`skills/bug-corpus/`, `adapters.py`, `mcp_server.py`) —
   one canonical skill, thin per-harness installs (OMP, Claude Code, Codex),
   optional MCP server over the same library the CLI uses.
5. **CI/developer integration** (`.github/workflows/bugcorpus.yml`) —
   `verify` + `scan --profile pr` on PRs, full scan on schedule.

A crashing detector reports `detector-error`, never a clean scan.
Baseline mode hides old repo debt but never historical fixtures.

## Repo map
<!-- trace:v1 id=doc.bugcorpus-readme-map work=WORK-BUG-ZJBDCZZ0 -->

| Area | Path |
|---|---|
| CLI/core | `bugcorpus/` |
| Corpus state | `.bugcorpus/` |
| Canonical skill | `skills/bug-corpus/SKILL.md` |
| Tests | `tests/bugcorpus/` |
| CI | `.github/workflows/bugcorpus.yml` |

## Commands
<!-- trace:v1 id=doc.bugcorpus-readme-commands work=WORK-BUG-ZJBDCZZ0 -->

`init`, `learn [--from-worktree|--before|--after]`, `show`, `related`,
`search`, `family list|show`, `synthesize [--family]`, `verify [--detector]`,
`scan [--all|--changed|--diff|--profile]`, `detector list|show|run`,
`promote --to`, `suppress`, `doctor`, `adapters install`, `export sarif`,
`mine-history`, `mcp`.
