# Changelog
<!-- trace:v1 id=doc.bugcorpus-changelog work=WORK-BUG-ZJBDCZZ0 -->


## 0.1.0 — 2026-09-10
<!-- trace:v1 id=doc.bugcorpus-release-0-1-0 work=WORK-BUG-ZJBDCZZ0 -->

Initial implementation: corpus (BugCase/family/lineage), synthesis ladder
with adversarial fixture evaluation, deterministic scanner (8 engine
adapters, profiles, fingerprints, suppressions, baselines, SARIF), `bugcorpus`
CLI, canonical `bug-corpus` skill with verified OMP/Claude/Codex adapters,
MCP server, history mining, and CI gates. Sample cases `BC-000001`
(stale-state-after-await, custom searcher) and `BC-000002`
(unsafe-dynamic-execution, lexical rule).
