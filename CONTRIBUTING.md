# Contributing

<!-- trace:v1 id=doc.bugcorpus-contributing work=WORK-BUG-ZJBDCZZ0 -->

## Setup
<!-- trace:v1 id=doc.bugcorpus-contributing-setup work=WORK-BUG-ZJBDCZZ0 -->

```sh
uv sync
uv run bugcorpus doctor
```

## Everyday loop
<!-- trace:v1 id=doc.bugcorpus-contributing-loop work=WORK-BUG-ZJBDCZZ0 -->

```sh
uv run pytest tests/ -q                 # full suite (<10s)
uv run bugcorpus verify                 # corpus + detector fixtures
uv run bugcorpus scan --profile pr      # what CI gates on
```

## Adding a bug + detector
<!-- trace:v1 id=doc.bugcorpus-contributing-add work=WORK-BUG-ZJBDCZZ0 -->

1. Fix the bug; prove it with the normal test suite.
2. `uv run bugcorpus learn --title "..."`; fill symptom vs root cause vs
   violated invariant (collapsing them fails validation).
3. `uv run bugcorpus search ...` — extend a family/detector before new ones.
4. Add minimized fixtures (positive, negative, adversarial both polarities).
5. `uv run bugcorpus verify <BC-ID>` must pass; new detectors land in
   `shadow`. `promote --to blocking` enforces full recall + zero negatives.
6. Read the `bug-corpus` skill (`skills/bug-corpus/SKILL.md`) — it is the
   canonical workflow for humans and agents alike.

## Adapter changes
<!-- trace:v1 id=doc.bugcorpus-contributing-adapters work=WORK-BUG-ZJBDCZZ0 -->

Edit sources under `adapters/` or `skills/bug-corpus/`, then
`uv run bugcorpus adapters install` and `uv run bugcorpus adapters install --check`.
Installed copies under `.claude/`, `.codex/`, `.agents/`, `.omp/` are
generated — never edit them directly.

## Quality gates (all must pass)
<!-- trace:v1 id=doc.bugcorpus-contributing-gates work=WORK-BUG-ZJBDCZZ0 -->

```sh
uvx ruff@latest check bugcorpus/ tests/ && uvx ruff@latest format --check bugcorpus/ tests/
pyright bugcorpus/ tests/ .bugcorpus/detectors/
trace verify --changed
```

Line coverage gate: ≥85% (`coverage run -m pytest`, `coverage report`).
