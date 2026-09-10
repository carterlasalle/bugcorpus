# ADR-002: Custom detectors run as subprocesses over a JSON contract

<!-- trace:v1 id=ADR-002 work=WORK-BUG-ZJBDCZZ0 -->

Date: 2026-09-10. Status: accepted.

## Context
<!-- trace:v1 id=doc.adr-002-context work=WORK-BUG-ZJBDCZZ0 -->

Purpose-built searchers (ladder level 8) can be written in any language, but
the orchestrator must treat a crash as `detector-error`, never a clean scan,
and must run detectors with timeouts in CI without importing untrusted code
into its own process.

## Decision
<!-- trace:v1 id=doc.adr-002-decision work=WORK-BUG-ZJBDCZZ0 -->

`python entrypoint --format json <files...>` printing a JSON list of findings
(`bugcorpus detector run DETECTOR --format json` equivalent). The orchestrator
absolutizes paths, sets `cwd` to the repo root, enforces the configured
timeout, and maps nonzero exit / timeout / unparseable output to
`detector-error`, which fails blocking scans.

## Alternatives considered
<!-- trace:v1 id=doc.adr-002-alternatives-considered work=WORK-BUG-ZJBDCZZ0 -->

- In-process plugin API: rejected — a crashing analyzer would take down the
  scan and blur the trust boundary between corpus data and runner.
- SARIF as the canonical schema: rejected — SARIF is export-only; the small
  internal Finding schema keeps fingerprints, lineage, and remediation
  first-class.

## Consequences
<!-- trace:v1 id=doc.adr-002-consequences work=WORK-BUG-ZJBDCZZ0 -->

Detectors stay language-neutral and independently executable, at the cost of
one subprocess spawn per detector per scan (negligible next to analysis).
