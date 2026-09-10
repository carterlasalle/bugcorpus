# ADR-001: Bare-checkout adapter surfaces over plugin installs

<!-- trace:v1 id=ADR-001 work=WORK-BUG-ZJBDCZZ0 -->

Date: 2026-09-10. Status: accepted.

## Context
<!-- trace:v1 id=doc.adr-001-context work=WORK-BUG-ZJBDCZZ0 -->

Bug Corpus must work identically under OMP, Claude Code, and Codex, with the
deterministic core authoritative. Each harness offers heavier distribution
(Claude marketplaces, Codex plugins, OMP marketplace/npm) that requires
explicit user install steps, trust approvals, or restarts — and whose schemas
we cannot execute here.

## Decision
<!-- trace:v1 id=doc.adr-001-decision work=WORK-BUG-ZJBDCZZ0 -->

Ship only surfaces that work from a bare repo checkout, verified against
primary docs on 2026-09-10:

- Claude Code: `.claude/skills/bug-corpus/`, `.claude/commands/*.md`,
  `.claude/settings.json` hook merge, `.mcp.json` merge.
- Codex: `.agents/skills/bug-corpus/`, AGENTS.md pointer,
  `.codex/hooks.json`, `.codex/config.toml` MCP merge.
- OMP: `.omp/skills/bug-corpus/` plus a real extension package
  (`.omp/extensions/bug-corpus/{package.json,bug-corpus.ts}`), mirroring the
  in-tree tracelayer gate's transport (async spawn, fail-open, timeout).

`bugcorpus adapters install` copies verbatim sources and merges structured
configs without clobbering; `adapters install --check` verifies sync in CI.

## Alternatives considered
<!-- trace:v1 id=doc.adr-001-alternatives-considered work=WORK-BUG-ZJBDCZZ0 -->

- Marketplace/plugin packaging per harness: rejected — install friction,
  per-harness review/trust flows, and no way to execute-verify here.
- One shared generated config: rejected — each surface has a real schema
  (Agents Skills frontmatter, hooks.json shapes, plugin manifests differ).

## Consequences
<!-- trace:v1 id=doc.adr-001-consequences work=WORK-BUG-ZJBDCZZ0 -->

Trust gates remain the user's one manual step (Codex hooks trust, Claude MCP
approval, OMP session restart); install prints them. If a harness later
offers verified zero-step distribution, revisit.
