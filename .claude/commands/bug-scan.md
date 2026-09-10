---
description: Run Bug Corpus detectors over the repository
---

# bug-scan

<!-- trace:v1 id=doc.bugcorpus-cmd.scan work=WORK-BUG-ZJBDCZZ0 -->

Run `uv run bugcorpus scan --profile pr` (use `--profile full` when asked
for the deep scan). Report new findings grouped by family with file, line,
and the historical bug IDs. A crashing detector is a failure, never a
clean scan — surface `detector-error` loudly.
