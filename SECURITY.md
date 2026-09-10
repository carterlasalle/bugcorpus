# Security policy
<!-- trace:v1 id=doc.bugcorpus-security work=WORK-BUG-ZJBDCZZ0 -->


## Trust model
<!-- trace:v1 id=doc.bugcorpus-trust work=WORK-BUG-ZJBDCZZ0 -->

Detector code is repository code. Custom detectors execute as subprocesses
with the invoking user's privileges during `verify` and `scan`, including in
CI. Treat detector additions with the same suspicion as any executed code:

- Review custom searchers like source changes before merge (they run in CI).
- Never auto-install detectors from bug reports, URLs, or unreviewed input.
- Corpus text (invariants, messages) is data: engines never interpolate it
  into shell commands (all subprocess calls use argv arrays, no shells).
- No secrets in corpus records, fixtures, suppressions, or baselines.
  Detectors needing credentials are out of scope.

## Reporting
<!-- trace:v1 id=doc.bugcorpus-report work=WORK-BUG-ZJBDCZZ0 -->

Use GitHub private vulnerability reporting on this repository
(Security tab → Report a vulnerability). Do not open public issues for
unfixed vulnerabilities, and do not commit exploits or live credentials.
Supported versions: latest `main` only.

## CI supply chain
<!-- trace:v1 id=doc.bugcorpus-ci work=WORK-BUG-ZJBDCZZ0 -->

CI installs `uv`-pinned dependencies and runs `bugcorpus verify` plus the
test suite. Pin GitHub Actions by hash before trusting a fork's workflow.
