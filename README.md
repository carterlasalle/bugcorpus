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

## Install
<!-- trace:v1 id=doc.bugcorpus-readme-install work=WORK-BUG-ZJBDCZZ0 -->

Prerequisites: Python 3.11+, [`uv`](https://docs.astral.sh/uv/), git.
No account, daemon, or network service is required — the core is local files
plus deterministic executables.

```sh
git clone <your-fork-or-this-repo> && cd bugcorpus
uv sync
uv run bugcorpus adapters install   # skills, commands, hooks, MCP entries
uv run bugcorpus adapters install --check   # verify sync (also runs in CI)
```

Per-harness, everything works from the checkout; each line is a trust step
owned by you, not by the installer:

- **Claude Code**: skill + `/bug-corpus` `/bug-learn` `/bug-scan` commands
  load automatically. Approve `.mcp.json` once when prompted. The
  PostToolUse hook runs a silent fast scan after Python edits; the Stop
  hook reminds you only if the session fixed a bug without learning it.
- **Codex**: skill (explicit `$bug-corpus` or automatic) plus AGENTS.md
  pointer load automatically. Trust project hooks once
  (`/hooks` — see <https://learn.chatgpt.com/docs/hooks>); MCP entry in
  `.codex/config.toml` needs approval on first run.
- **OMP**: `.omp/extensions/bug-corpus` auto-loads: the same three slash
  commands plus the cheap post-edit scan. Restart the session after install.

Uninstall: `git clean` the installed paths (they are all listed by
`adapters install --check` problems when drifted) or keep the core and
delete the harness directories; `bugcorpus verify` and `scan` never need
any adapter present.

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
`coverage` (bugs × engines plus family recall rollups, from live verification),
`scan [--all|--changed|--diff|--profile]`, `detector list|show|run`,
`promote --to`, `suppress`, `doctor`, `adapters install [--only,--check]`,
`export sarif`, `mine-history`, `mcp`, `hooks post-tool-use`.

## Agent adapters
<!-- trace:v1 id=doc.bugcorpus-readme-adapters work=WORK-BUG-ZJBDCZZ0 -->

One canonical skill (`skills/bug-corpus/SKILL.md`, Agent Skills frontmatter);
`uv run bugcorpus adapters install` copies it plus per-harness surfaces and
merges configs without clobbering. Everything works from a bare checkout:

| Harness | Shipped | Manual step |
|---|---|---|
| Claude Code | `.claude/skills/`, `.claude/commands/` (bug-corpus/learn/scan), settings hook merge, `.mcp.json` merge | approve MCP once |
| Codex | `.agents/skills/`, AGENTS.md pointer, `.codex/hooks.json`, `.codex/config.toml` MCP merge | trust project hooks |
| OMP | `.omp/skills/`, `.omp/extensions/bug-corpus/` (real extension: `/bug-corpus` `/bug-learn` `/bug-scan` + cheap post-edit hook) | restart session |

Post-edit hooks in every harness call `uv run bugcorpus hooks post-tool-use`:
fast-profile scan of the touched file, silent unless a warning/blocking
detector fires, always exit 0 (advisory — CI enforces). Details and
alternatives in `docs/adr/001-bare-checkout-adapters.md`.
