# Changelog
<!-- trace:v1 id=doc.bugcorpus-changelog work=WORK-BUG-ZJBDCZZ0 -->


## 0.3.1 — 2026-09-11
<!-- trace:v1 id=doc.bugcorpus-release-0-3-1 work=WORK-BUG-ZJBDCZZ0 -->

Hostile-environment hardening: doctor/scan never glob unenrolled roots,
show/related/synthesize report missing records cleanly, hooks never block
on a terminal. Three BugCases (BC-000003/4/5) registered with rung-0 test
linkage, skill close-out rule, CI triggers on trace config.

<!-- trace:v1 id=doc.bugcorpus-release-0-3-0 work=WORK-BUG-ZJBDCZZ0 -->

Readable human CLI: every command has `--help` text and a sectioned
renderer (no more raw JSON dumps), runnable next-steps sit alone on
their own line, and `init` reports what it did. The canonical skill now
documents the community exchange, so agents never need to explore the
bugcorpus repo. No ANSI color, so readability never depends on theme
contrast. `--json` unchanged.

## 0.2.0 — 2026-09-10
<!-- trace:v1 id=doc.bugcorpus-release-0-2-0 work=WORK-BUG-ZJBDCZZ0 -->

Community detector exchange (`community export|import|list|install|publish`)
with PR-gated trust: imports land at shadow or draft, provenance records
origin, and the blank `community` branch keeps shared detectors out of
default checkouts until curated. Adapter install merges hooks instead of
overwriting foreign entries; `node_modules` excluded from default scan scope.

## 0.1.1 — 2026-09-10
<!-- trace:v1 id=doc.bugcorpus-release-0-1-1 work=WORK-BUG-ZJBDCZZ0 -->

MIT license. PyPI distribution with bundled adapter payload, `bugcorpus
update`, invocation-aware adapters, real MCP protocol, blocking gate with
baseline, reviewdog annotations, coverage matrix artifact.
<!-- trace:v1 id=doc.bugcorpus-release-0-1-0 work=WORK-BUG-ZJBDCZZ0 -->

Initial implementation: corpus (BugCase/family/lineage), synthesis ladder
with adversarial fixture evaluation, deterministic scanner (8 engine
adapters, profiles, fingerprints, suppressions, baselines, SARIF), `bugcorpus`
CLI, canonical `bug-corpus` skill with verified OMP/Claude/Codex adapters,
MCP server, history mining, and CI gates. Sample cases `BC-000001`
(stale-state-after-await, custom searcher) and `BC-000002`
(unsafe-dynamic-execution, lexical rule).
