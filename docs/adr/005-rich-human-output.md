# ADR-005: Rich for human CLI output only

<!-- trace:v1 id=ADR-005 work=WORK-BUG-ZJBDCZZ0 -->

Date: 2026-09-11. Status: accepted.

## Context
<!-- trace:v1 id=doc.adr-005-context work=WORK-BUG-ZJBDCZZ0 -->

Human `bugcorpus` output was stdlib `print`: unaligned columns, raw JSON
fallbacks, no progress signal during slow scans. A sibling project
(bughunt) using Rich reads materially better for the same information.

## Decision
<!-- trace:v1 id=doc.adr-005-decision work=WORK-BUG-ZJBDCZZ0 -->

Depend on `rich` for the human rendering layer only (`print_human` in
`bugcorpus/cli.py` plus a scan progress indicator). Rules:

- `--json` output is byte-identical and never touches Rich.
- No hand-rolled dim/low-contrast styling: default Rich theme only, so
  readability never depends on terminal theme. Rich already respects
  `NO_COLOR` and degrades to plain text on pipes (which is also what the
  test suite captures).
- Tables only where cells are short single tokens (detector lists,
  matches, families); prose and command next-steps stay plain lines so
  they remain copy-pasteable and assertion-stable.
- Detector engines, scanner, verifier, and store never import Rich.

## Alternatives considered
<!-- trace:v1 id=doc.adr-005-alternatives-considered work=WORK-BUG-ZJBDCZZ0 -->

- Stdlib-only alignment (`shutil` + manual padding): rejected — a poor
  reimplementation of column layout, wrapping, and terminal detection
  that an established library already owns.
- Full TUI (Textual): rejected — interactive screens break piping,
  CI logs, and hook contexts; the CLI must stay non-interactive.
- Custom ANSI colors: rejected — hand-picked shades are exactly what
  breaks on low-contrast themes; Rich's defaults plus NO_COLOR support
  dominate it.

## Consequences
<!-- trace:v1 id=doc.adr-005-consequences work=WORK-BUG-ZJBDCZZ0 -->

Runtime dependencies grow from one (`pyyaml`) to two (`rich`). Human
output gains aligned tables and a scan spinner on TTYs; CI logs and
pipes are unchanged plain text.
