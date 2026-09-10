---
name: Bug report
about: Report a defect as future detector evidence
title: "[bug] "
labels: ["bug"]
---

## Symptom

What did you observe? (Not why — just the incorrect behavior.)

## Root cause (if known)

Why is the code wrong?

## Violated invariant

What rule should a detector enforce so this class cannot recur?
Target the invariant, not the single line.

## Reproducer

Minimal steps or snippet. A maintainer will minimize it into
`.bugcorpus/corpus/BC-NNNNNN/fixtures/` during `bugcorpus learn`.
