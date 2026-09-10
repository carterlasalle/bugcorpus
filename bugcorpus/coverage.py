"""Coverage matrix: bugs × engines plus family rollups, from live verification."""

from __future__ import annotations

import json
from pathlib import Path

from . import store
from .models import ENGINES
from .verifier import verify_detector

MATRIX_VERSION = 2
MATRIX_NAME = "coverage-matrix.json"
SHORT = {
    "existing": "exist",
    "lexical": "lex",
    "ast-grep": "agrep",
    "semgrep": "semgrep",
    "semgrep-taint": "s-taint",
    "codeql": "codeql",
    "pysa": "pysa",
    "custom": "custom",
}


# trace:v1 id=impl.bugcorpus-coverage.build work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-FESAJNS2
def build_matrix(repo: Path, timeout: int = 60) -> dict:
    """Verify every detector and tabulate bugs × engines plus family rollups."""
    cwd = str(repo)
    dets: dict[str, dict] = {}
    for did in store.list_detectors(cwd):
        det, _ = store.load_detector(cwd, did)
        v = verify_detector(repo, did, timeout)
        m = v["metrics"]
        n_neg = m["negatives"]
        dets[did] = {
            "id": did,
            "version": det.version,
            "engine": det.engine,
            "state": det.state,
            "family": det.family,
            "catches": sorted(set(det.catches)),
            "ok": v["ok"],
            "error": v["error"],
            "blocking_eligible": v["blocking_eligible"],
            "known": f"{m['caught']}/{m['positives']}",
            "known_recall": m["recall"],
            "adv": f"{m['adv_positives'] - len(m['adv_missed'])}/{m['adv_positives']}",
            "adv_recall": m["adv_recall"],
            "neg_fp": len(m["false_positives"]),
            "neg_fp_rate": (len(m["false_positives"]) / n_neg) if n_neg else 0.0,
        }
    bugs: dict[str, dict] = {}
    for bid in store.list_bugs(cwd):
        b = store.load_bug(cwd, bid)
        caught_by = sorted(
            did
            for did, d in dets.items()
            if d["ok"] and (bid in d["catches"] or did in (b.detector_ids or []))
        )
        covered = {dets[did]["engine"] for did in caught_by}
        bugs[bid] = {
            "title": b.title,
            "family": b.family_id,
            "detectors": caught_by,
            "engines": {e: (e in covered) for e in ENGINES},
        }
    families: dict[str, dict] = {}
    for fid in store.list_families(cwd):
        fam = store.load_family(cwd, fid)
        members = [bid for bid, b in bugs.items() if b["family"] == fid]
        live = [d for d in dets.values() if d["family"] == fid and d["state"] != "retired"]
        live.sort(key=lambda d: (d["version"], d["id"]))
        families[fid] = {
            "title": fam.get("title", fid),
            "members": {
                bid: {
                    "caught": bool(bugs[bid]["detectors"]),
                    "by": sorted(d["id"] for d in live if bid in d["catches"]),
                }
                for bid in members
            },
            "detectors": live,
        }
    return {
        "version": MATRIX_VERSION,
        "generated_at": store.utcnow(),
        "engines": list(ENGINES),
        "bugs": bugs,
        "families": families,
    }


# trace:exempt reason=internal-detail
def write_matrix(repo: Path, timeout: int = 60) -> tuple[dict, Path]:
    matrix = build_matrix(repo, timeout)
    out = store.cdir(str(repo)) / "generated" / MATRIX_NAME
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(matrix, indent=2) + "\n")
    return matrix, out


# trace:exempt reason=internal-detail
def render_human(matrix: dict) -> str:
    engines = matrix["engines"]
    header = f"{'bug':<10}" + "".join(f"{SHORT.get(e, e[:8]):<9}" for e in engines)
    rows = [header.rstrip()]
    for bid, b in matrix["bugs"].items():
        cells = "".join(f"{'✓' if b['engines'][e] else '':<9}" for e in engines)
        rows.append(f"{bid:<10}" + cells)
    blocks = []
    for fid, fam in matrix["families"].items():
        lines = [f"FAM {fid} ({fam['title']}):"]
        for bid, mem in fam["members"].items():
            tick = "✓" if mem["caught"] else "✗"
            lines.append(f"    {bid} {tick} ({', '.join(mem['by']) or 'uncaught'})")
        for d in fam["detectors"]:
            lines.append(f"    detector: {d['id']} ({d['engine']}, v{d['version']})")
            lines.append(f"    known recall:       {d['known_recall']:.1%} ({d['known']})")
            lines.append(f"    adversarial recall: {d['adv_recall']:.1%} ({d['adv']})")
            lines.append(f"    negative FP rate:   {d['neg_fp_rate']:.1%}")
            lines.append(f"    state:              {d['state'].upper()}")
        blocks.append("\n".join(lines))
    table = "\n".join(r.rstrip() for r in rows)
    return "Bug Corpus coverage\n" + table + "\n\n" + "\n\n".join(blocks)
