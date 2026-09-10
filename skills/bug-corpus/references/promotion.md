# Promotion — draft → candidate → shadow → warning → blocking
<!-- trace:v1 id=doc.bugcorpus-promotion work=WORK-BUG-ZJBDCZZ0 -->

- candidate: fixture suite passes
- shadow: runs in CI, never fails builds
- warning: surfaced prominently, non-blocking
- blocking: 100% positive recall + 0 negative false positives + adversarial
  recall at threshold (see `.bugcorpus/config.toml` [promotion])

`bugcorpus promote DET --to blocking` enforces thresholds automatically.
False positives are detector bugs until proven otherwise — improve the
detector before reaching for suppressions. Suppressions live in
`.bugcorpus/suppressions/` with detector, fingerprint, reason, timestamp.
Known-positive fixtures intentionally fire during `scan`. Before promoting to
`blocking`, record their fingerprints in `.bugcorpus/baseline.json` so CI
fails only on new findings. This never weakens `verify`, which ignores the
baseline and always requires fixtures to fire.
