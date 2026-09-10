# Bug Corpus — requirements
<!-- trace:v1 id=doc.bugcorpus-spec work=WORK-BUG-ZJBDCZZ0 -->

Work: initial implementation of the bug-to-detector compiler.

## Corpus persists BugCases, families, and lineage

<!-- trace:v1 id=REQ-BUG-0VGE5410 work=WORK-BUG-ZJBDCZZ0 -->

BugCase records carry stable `BC-NNNNNN` ids and keep symptom, root cause,
and violated invariant distinct, plus a machine-readable semantic signature.
Families group cases independently of individual bugs; detectors record which
cases they catch and which implementations they supersede.

## Synthesis is evidence-driven and adversarially evaluated

<!-- trace:v1 id=REQ-BUG-FESAJNS2 work=WORK-BUG-ZJBDCZZ0 -->

Each BugCase assembles an evidence pack and recommends the cheapest adequate
engine on the ladder (existing, lexical, ast-grep, semgrep, taint, CodeQL,
Pysa, custom). Candidates must pass positive, negative, and adversarial
fixtures with measured recall and precision before promotion; blocking
requires full positive recall and zero negative false positives.

## Scanner runtime is deterministic and LLM-free

<!-- trace:v1 id=REQ-BUG-8HPVNRVG work=WORK-BUG-ZJBDCZZ0 -->

CI executes all promoted detectors without an LLM through engine adapters,
with `fast`/`pr`/`full` profiles, fingerprints stable across line movement,
structured suppressions, baseline mode for legacy debt, and SARIF export.
Crashing detectors report `detector-error`, never a clean scan.

## Agent integration is a thin adapter over the core

<!-- trace:v1 id=REQ-BUG-MKCEMW39 work=WORK-BUG-ZJBDCZZ0 -->

One canonical `bug-corpus` skill plus idempotent installs for OMP, Claude
Code, and Codex, and an MCP server that calls the same library as the CLI.
Corpus, synthesis, and scanning work with no agent installed.

## CI gates corpus and detector changes

<!-- trace:v1 id=REQ-BUG-WSZJ7M37 work=WORK-BUG-ZJBDCZZ0 -->

Changes to corpus or detector files run fixture verification; PRs run the
`pr` scan profile; blocking findings or detector errors fail the build.
