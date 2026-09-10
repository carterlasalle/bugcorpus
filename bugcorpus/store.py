"""Corpus storage: paths, load/save, IDs, indexes."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import yaml

from .models import BugCase, Detector

CORPUS_DIR = ".bugcorpus"


# trace:exempt reason=internal-detail
def root(cwd: str | None = None) -> Path:
    base = Path(cwd or Path.cwd())
    cur = base.resolve()
    for cand in (cur, *cur.parents):
        if (cand / CORPUS_DIR / "config.toml").exists() or (cand / CORPUS_DIR).exists():
            return cand
    return base


# trace:exempt reason=internal-detail
def cdir(cwd: str | None = None) -> Path:
    return root(cwd) / CORPUS_DIR


# trace:exempt reason=internal-detail
def bug_dir(cwd: str | None, bid: str) -> Path:
    return cdir(cwd) / "corpus" / bid


# trace:exempt reason=internal-detail
def detector_dir(cwd: str | None, did: str) -> Path:
    # detectors live at .bugcorpus/detectors/<did>/ (flat; engine in manifest)
    return cdir(cwd) / "detectors" / did


# trace:exempt reason=internal-detail
def load_yaml(p: Path) -> dict:
    return yaml.safe_load(p.read_text()) or {}


# trace:exempt reason=internal-detail
def dump_yaml(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))


# trace:v1 id=impl.bugcorpus-store.load-bug work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-0VGE5410
def load_bug(cwd: str | None, bid: str) -> BugCase:
    d = load_yaml(bug_dir(cwd, bid) / "bug.yaml")
    known = {f for f in BugCase.__dataclass_fields__}
    return BugCase(**{k: v for k, v in d.items() if k in known})


# trace:v1 id=impl.bugcorpus-store.save-bug work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-0VGE5410
def save_bug(cwd: str | None, bug: BugCase) -> None:
    from dataclasses import asdict

    dump_yaml(bug_dir(cwd, bug.id) / "bug.yaml", asdict(bug))


# trace:exempt reason=internal-detail
def list_bugs(cwd: str | None = None) -> list[str]:
    base = cdir(cwd) / "corpus"
    if not base.exists():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir() and re.match(r"^BC-\d{6}$$", p.name))


# trace:v1 id=impl.bugcorpus-store.next-id work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-0VGE5410
def next_bug_id(cwd: str | None = None) -> str:
    ids = list_bugs(cwd)
    n = max((int(i[3:]) for i in ids), default=0) + 1
    return f"BC-{n:06d}"


# trace:v1 id=impl.bugcorpus-store.load-detector work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-0VGE5410
def load_detector(cwd: str | None, did: str) -> tuple[Detector, Path]:
    d = detector_dir(cwd, did)
    manifest = d / "detector.yaml"
    data = load_yaml(manifest)
    known = {f for f in Detector.__dataclass_fields__}
    return Detector(**{k: v for k, v in data.items() if k in known}), d


# trace:exempt reason=internal-detail
def list_detectors(cwd: str | None = None) -> list[str]:
    base = cdir(cwd) / "detectors"
    if not base.exists():
        return []
    out = []
    for p in base.iterdir():
        if p.is_dir() and (p / "detector.yaml").exists():
            out.append(p.name)
        elif p.is_file() and p.suffix in (".yaml", ".yml"):
            out.append(p.stem)  # legacy single-file layout
    return sorted(out)


# trace:exempt reason=internal-detail
def load_family(cwd: str | None, fid: str) -> dict:
    return load_yaml(cdir(cwd) / "families" / f"{fid}.yaml")


# trace:exempt reason=internal-detail
def list_families(cwd: str | None = None) -> list[str]:
    base = cdir(cwd) / "families"
    if not base.exists():
        return []
    return sorted(p.stem for p in base.glob("*.yaml"))


# trace:exempt reason=internal-detail
def load_suppressions(cwd: str | None = None) -> list[dict]:
    out: list[dict] = []
    base = cdir(cwd) / "suppressions"
    if base.exists():
        for p in sorted(base.glob("*.yaml")):
            data = load_yaml(p)
            items = data.get("suppressions", data if isinstance(data, list) else [])
            if isinstance(items, list):
                out.extend(items)
    return out


# trace:exempt reason=internal-detail
def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# trace:v1 id=impl.bugcorpus-store.write-index work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-0VGE5410
def write_index(cwd: str | None = None) -> dict:
    """Regenerate generated/*.json indexes. Returns corpus index."""
    c = cdir(cwd)
    bugs, dets = [], []
    for bid in list_bugs(cwd):
        try:
            b = load_bug(cwd, bid)
            bugs.append(
                {
                    "id": b.id,
                    "title": b.title,
                    "family": b.family_id,
                    "detectors": b.detector_ids,
                    "severity": b.severity,
                    "symbols": b.relevant_symbols,
                    "subsystem": b.subsystem,
                    "invariant": b.violated_invariant,
                }
            )
        except Exception:  # noqa: BLE001 -- index degrades per-record, never crashes
            bugs.append({"id": bid, "error": "unreadable"})
    for did in list_detectors(cwd):
        try:
            d, _ = load_detector(cwd, did)
            dets.append(
                {
                    "id": d.id,
                    "engine": d.engine,
                    "state": d.state,
                    "family": d.family,
                    "catches": d.catches,
                    "cost": d.cost,
                    "version": d.version,
                }
            )
        except Exception:  # noqa: BLE001 -- index degrades per-record, never crashes
            dets.append({"id": did, "error": "unreadable"})
    gen = c / "generated"
    gen.mkdir(parents=True, exist_ok=True)
    corpus_index = {"bugs": bugs, "families": list_families(cwd)}
    (gen / "corpus-index.json").write_text(json.dumps(corpus_index, indent=2))
    (gen / "detector-index.json").write_text(json.dumps({"detectors": dets}, indent=2))
    matrix = {}
    for b in bugs:
        row = {}
        for d in dets:
            row[d["id"]] = d.get("id") in (b.get("detectors") or []) or b.get("id") in (
                d.get("catches") or []
            )
        matrix[b.get("id", "?")] = row
    (gen / "coverage-matrix.json").write_text(json.dumps(matrix, indent=2))
    return corpus_index
