# Community detectors

Shared [Bug Corpus](https://github.com/carterlasalle/bugcorpus) detectors.
Anyone can contribute; the maintainer reviews every addition before merge.
Detectors are executable code — this branch is a trust boundary, not a feed.

This branch is intentionally **blank apart from shared detectors**: no copy
of the main source tree, so pull-request diffs contain only the detector
under review and there is nothing stale to conflict with. Two contributions
adding the same detector id collide at merge time — that is the review gate
working, not an accident.

## Layout

- Detectors live under `.bugcorpus/detectors/community/<detector-id>/` with
  a `detector.yaml`, any entrypoint code, and `fixtures/` (positive,
  negative, adversarial). No fixture, no merge.
- This branch is **never merged into `main`**. Shared code stays out of
  default checkouts and CI until the maintainer curates it there.

## Contribute yours

```sh
bugcorpus community export my-detector --output /tmp/share
git fetch origin community
git checkout -b share/my-detector origin/community
# copy /tmp/share/my-detector to .bugcorpus/detectors/community/my-detector/
git add .bugcorpus/detectors/community/my-detector && git commit -m "Share my-detector"
bugcorpus community publish --base community
```

## Review checklist (for the maintainer)

1. `detector.yaml` parses; id is new and sensibly namespaced.
2. Fixtures prove the invariant: positives fire, negatives don't, adversarial
   positives survive renaming/restructuring.
3. Scope is tight (`languages`, paths) — no repo-wide regex dragnets.
4. Entrypoint code: argv arrays, no shells, no network, no untrusted
   interpolation. Read it like a dependency.
5. `bugcorpus verify` passes on the bundle standalone. Note: CI green on the
   PR proves fixtures pass, not that the code is safe — the review is human.
6. Only minimized fixtures travel — no production code from the contributor's
   repo.

## Use someone else's

```sh
bugcorpus community list --ref community
bugcorpus community install --ref community --detector their-detector
bugcorpus verify --detector their-detector   # trust, then verify anyway
```

Imports always land as `shadow` (or `draft` when fixtures fail) and only
promote through local `verify` + `promote` thresholds.
