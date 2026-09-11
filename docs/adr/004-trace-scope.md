# ADR-004: TraceLayer scope excludes corpus data and generated files

<!-- trace:v1 id=ADR-004 work=WORK-BUG-ZJBDCZZ0 -->

Date: 2026-09-10. Status: accepted.

## Context
<!-- trace:v1 id=doc.adr-004-context work=WORK-BUG-ZJBDCZZ0 -->

TraceLayer demands per-boundary accounting for changed files. Applied
literally to `.bugcorpus/`, every YAML key of every BugCase record and every
fixture function would need a marker — ceremony on data, not behavior.

## Decision
<!-- trace:v1 id=doc.adr-004-decision work=WORK-BUG-ZJBDCZZ0 -->

Trace the code that manages the corpus (`bugcorpus/*.py`, detector logic,
adapter installer) and the adapter/CI contracts. Exclude via `trace ignore`:

- `.bugcorpus/` (records, fixtures, evidence, generated indexes — data),
- `uv.lock`, `pyrightconfig.json`, `CODEX.md`, `.codex/hooks.json`
  (generated manifests the tool cites as typical exclusions),
- `bughunt.toml`, `bun.lock`, `package.json`, `.pyre_configuration`,
  `.pyre/` (foreign-managed bootstrap from a bughunt evaluation run:
  markers would be clobbered by that tool or pollute its configs, and the
  files carry no Bug Corpus behavior. Revisit if any of these paths
  becomes repository-owned).

Bug Corpus's own lineage (`catches`, coverage matrix) remains the audit trail
for corpus data. Revisit if TraceLayer gains data-record semantics.

## Alternatives considered
<!-- trace:v1 id=doc.adr-004-alternatives-considered work=WORK-BUG-ZJBDCZZ0 -->

- Per-key markers on records: rejected — hundreds of markers with zero
  behavioral signal, guaranteeing marker fatigue and gaming.
- Leaving the gate red: rejected — a permanently red gate teaches agents to
  ignore gates.

## Consequences
<!-- trace:v1 id=doc.adr-004-consequences work=WORK-BUG-ZJBDCZZ0 -->

`trace verify --changed` stays green and meaningful; corpus-data review
relies on `bugcorpus verify` plus human review of `catches` changes.
