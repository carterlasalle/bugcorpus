# Bug Corpus — domain vocabulary

<!-- trace:v1 id=doc.bugcorpus-context work=WORK-BUG-ZJBDCZZ0 -->

Use these terms exactly. Do not invent synonyms.

- **BugCase** (`BC-NNNNNN`): one confirmed bug — symptom, root cause, and
  violated invariant kept distinct, plus a semantic signature. Identity is
  the BC number, never a filename or issue number.
- **Symptom / root cause / violated invariant**: what the user saw / why the
  code was wrong / the rule detectors target. Collapsing them is a schema
  error.
- **Semantic signature**: machine-readable description of the bug independent
  of source text (calls, flows, boundaries, sanitizers).
- **Family**: a bug class (e.g. `stale-state-after-await`) independent of
  individual BugCases. One detector may protect many cases.
- **Detector**: a deterministic check on the synthesis ladder
  (`existing → lexical → ast-grep → semgrep → taint → codeql → pysa →
  custom`). States: `draft → candidate → shadow → warning → blocking →
  retired`.
- **Fixture**: `positive` (must fire), `negative` (must not),
  `adversarial-positive/negative` (same semantics, new shape / similar shape,
  valid). Minimized (~15 lines), never production dumps.
- **Finding**: one detector hit with a stable **fingerprint** (no line
  numbers), explanation, and remediation.
- **Suppression**: structured, auditable exception (detector, fingerprint,
  reason, timestamp) — a detector bug until proven otherwise.
- **Baseline**: recorded legacy findings; CI fails only on *new* findings.
  Never applies to fixture verification.
- **Lineage**: `catches` (detector→cases) and `detector_ids` (case→detectors);
  verification merges caught cases' fixtures into every detector run.
