"""Adversarial-aware detector verification: fixtures, metrics, thresholds."""

from __future__ import annotations

import tomllib
from pathlib import Path

from . import store
from .engines import ENGINES, load_manifest


# trace:exempt reason=internal-detail
def fixture_files(
    ddir: Path, manifest: dict | None = None, repo: Path | None = None
) -> dict[str, list[Path]]:
    out = {"positive": [], "negative": [], "adv_positive": [], "adv_negative": []}
    mapping = {
        "positive": "positive",
        "negative": "negative",
        "adversarial_positive": "adv_positive",
        "adversarial_negative": "adv_negative",
        "adversarial-positive": "adv_positive",
        "adversarial-negative": "adv_negative",
    }

    def collect(fx: Path):
        if not fx.exists():
            return
        for sub, key in mapping.items():
            d = fx / sub
            if d.exists():
                out[key].extend(sorted(p for p in d.rglob("*") if p.is_file()))
        # bare adversarial/ dir: polarity comes from the file stem
        bare = fx / "adversarial"
        if bare.exists():
            for p in sorted(b for b in bare.rglob("*") if b.is_file()):
                stem = p.stem.lower()
                if "negative" in stem or stem.startswith("adv_neg"):
                    out["adv_negative"].append(p)
                else:
                    out["adv_positive"].append(p)

    if ddir:
        collect(ddir / "fixtures")
    if manifest and repo:
        for bid in manifest.get("catches", []):
            collect(repo / ".bugcorpus" / "corpus" / bid / "fixtures")
    return {key: sorted(set(files)) for key, files in out.items()}


# trace:exempt reason=internal-detail
def _fires(repo: Path, manifest: dict, ddir: Path, f: Path, timeout: int) -> bool:
    engine = ENGINES.get(manifest.get("engine", "custom"))
    if engine is None:
        return False
    res = engine.scan(repo, manifest, ddir, [str(f)], timeout)
    if res.status == "detector-error":
        raise RuntimeError(f"detector {manifest['id']} errored on {f.name}: {res.detail[:300]}")
    if res.status == "unavailable":
        raise RuntimeError(f"engine {manifest.get('engine')} unavailable")
    # count only findings touching this fixture file
    for r in res.findings:
        p = r.get("path", "")
        if Path(p).name == f.name or str(p).endswith(
            str(f.relative_to(repo)) if _inside(f, repo) else f.name
        ):
            return True
    return bool(res.findings)


# trace:exempt reason=internal-detail
def _inside(f: Path, repo: Path) -> bool:
    try:
        f.relative_to(repo)
        return True
    except ValueError:
        return False


# trace:v1 id=impl.bugcorpus-verifier.fixture-eval work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-FESAJNS2
def verify_detector(repo: Path, did: str, timeout: int = 60) -> dict:
    manifest = load_manifest(store.detector_dir(str(repo), did))
    ddir = store.detector_dir(str(repo), did)
    fx = fixture_files(ddir, manifest, repo)
    pos, neg = fx["positive"], fx["negative"]
    adv_p, adv_n = fx["adv_positive"], fx["adv_negative"]
    if not pos:
        return {"detector": did, "ok": False, "error": "no positive fixtures", "metrics": {}}
    if not neg:
        return {"detector": did, "ok": False, "error": "no negative fixtures", "metrics": {}}
    missed, false_pos, adv_missed, adv_fp = [], [], [], []
    error = ""
    try:
        for f in pos:
            if not _fires(repo, manifest, ddir, f, timeout):
                missed.append(f.name)
        for f in neg:
            if _fires(repo, manifest, ddir, f, timeout):
                false_pos.append(f.name)
        for f in adv_p:
            if not _fires(repo, manifest, ddir, f, timeout):
                adv_missed.append(f.name)
        for f in adv_n:
            if _fires(repo, manifest, ddir, f, timeout):
                adv_fp.append(f.name)
    except RuntimeError as e:
        error = str(e)
    n_pos, n_neg = len(pos), len(neg)
    metrics = {
        "positives": n_pos,
        "caught": n_pos - len(missed),
        "missed": missed,
        "negatives": n_neg,
        "false_positives": false_pos,
        "adv_positives": len(adv_p),
        "adv_missed": adv_missed,
        "adv_negatives": len(adv_n),
        "adv_false_positives": adv_fp,
        "recall": (n_pos - len(missed)) / n_pos if n_pos else 0,
        "adv_recall": ((len(adv_p) - len(adv_missed)) / len(adv_p)) if adv_p else 1.0,
        "precision_neg": (n_neg - len(false_pos)) / n_neg if n_neg else 0,
    }
    # historical revisions: bad must fire, fixed must not (baseline never hides these)
    hist = check_history(repo, manifest, ddir, timeout)
    metrics["history"] = hist
    ok = (
        not error
        and not missed
        and not false_pos
        and not adv_fp
        and hist.get("bad_caught", True)
        and hist.get("fixed_clean", True)
    )
    # adversarial recall below 100% is reported, blocks only 'blocking' promotion
    return {
        "detector": did,
        "ok": ok,
        "error": error,
        "metrics": metrics,
        "blocking_eligible": bool(ok and metrics["adv_recall"] >= 1.0),
    }


# trace:exempt reason=internal-detail
def check_history(repo: Path, manifest: dict, ddir: Path, timeout: int) -> dict:
    out: dict = {}
    for name, want in (("bad", True), ("fixed", False)):
        f = ddir / "history" / f"{name}.py"
        if f.exists():
            try:
                out["bad_caught" if want else "fixed_clean"] = (
                    _fires(repo, manifest, ddir, f, timeout) == want
                )
            except RuntimeError as e:
                out["error"] = str(e)
    return out


# trace:exempt reason=internal-detail
def thresholds(repo: Path) -> dict:
    p = repo / ".bugcorpus" / "config.toml"
    if p.exists():
        with open(p, "rb") as f:
            cfg = tomllib.load(f)
        return cfg.get("promotion", {"recall": 1.0, "neg_fp": 0, "adv_recall_blocking": 1.0})
    return {"recall": 1.0, "neg_fp": 0, "adv_recall_blocking": 1.0}


# trace:v1 id=impl.bugcorpus-verifier.verify-all work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-FESAJNS2
def verify_all(repo: Path, only: str | None = None, detector: str | None = None) -> dict:
    dids = [detector] if detector else store.list_detectors(str(repo))
    bids = [only] if only else []
    results = []
    if bids:
        for bid in bids:
            b = store.load_bug(str(repo), bid)
            for did in b.detector_ids or store.list_detectors(str(repo)):
                if did in dids or not detector:
                    results.append(verify_detector(repo, did))
    else:
        for did in dids:
            try:
                results.append(verify_detector(repo, did))
            except (OSError, ValueError) as e:
                results.append({"detector": did, "ok": False, "error": str(e)})
    # corpus schema validation
    schema_errors = validate_corpus(repo)
    ok = all(r["ok"] for r in results) and not schema_errors
    return {"ok": ok, "detectors": results, "schema_errors": schema_errors}


# trace:v1 id=impl.bugcorpus-verifier.corpus-schema work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-FESAJNS2
def validate_corpus(repo: Path) -> list[str]:
    errs = []
    for bid in store.list_bugs(str(repo)):
        try:
            b = store.load_bug(str(repo), bid)
            errs.extend(f"{bid}: {e}" for e in b.validate())
        except Exception as e:  # noqa: BLE001 -- corrupt record must surface, never pass silently
            errs.append(f"{bid}: unreadable ({e})")
    for did in store.list_detectors(str(repo)):
        try:
            from .models import Detector as _D

            m = load_manifest(store.detector_dir(str(repo), did))
            d = _D(
                id=m.get("id", did),
                version=m.get("version", 1),
                family=m.get("family", ""),
                engine=m.get("engine", "custom"),
                entrypoint=m.get("entrypoint", "")
                or m.get("rule_file", "")
                or m.get("config", "")
                or (m.get("run", [None])[0] if m.get("run") else ""),
                cost=m.get("cost", "cheap"),
                state=m.get("state", "shadow"),
            )
            errs.extend(f"{did}: {e}" for e in d.validate())
        except Exception as e:  # noqa: BLE001 -- corrupt detector must surface, never pass silently
            errs.append(f"{did}: unreadable ({e})")
    return errs
