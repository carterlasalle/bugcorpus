"""Synthesis workflow: evidence-pack assembly + ladder recommendation (deterministic).

An LLM may draft a detector from the pack, but execution/validation never
needs one. This module never calls an LLM; it prepares the evidence pack and
records the chosen engine + rationale.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from . import store
from .searcher import related

LADDER = ["existing", "lexical", "ast-grep", "semgrep", "semgrep-taint", "codeql", "pysa", "custom"]
LADDER_GUIDE = {
    "existing": "already caught by a configured analyzer — record rule, add regression check",
    "lexical": "stable textual structure (forbidden API/helper)",
    "ast-grep": "syntax-tree relationships suffice",
    "semgrep": "semantic structural pattern across the file",
    "semgrep-taint": "source → propagation → sink dataflow",
    "codeql": "interprocedural / cross-file / path-sensitive reasoning",
    "pysa": "project-specific taint sources/sinks/propagations in Python",
    "custom": "purpose-built searcher; document minimum semantic model",
}


# trace:v1 id=impl.bugcorpus-synth.evidence-pack work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-FESAJNS2
def evidence_pack(cwd, bid: str) -> dict:
    b = store.load_bug(cwd, bid)
    base = store.bug_dir(cwd, bid)
    pack = {
        "id": b.id,
        "title": b.title,
        "invariant": b.violated_invariant,
        "root_cause": b.root_cause,
        "symptom": b.symptom,
        "signature": b.semantic_signature,
        "symbols": b.relevant_symbols,
        "calls": b.relevant_calls,
        "family": b.family_id,
        "related": related(cwd, bid),
    }
    for name in ("original.diff", "fix.diff"):
        p = base / "evidence" / name
        if p.exists():
            pack[name] = p.read_text()[:8000]
    fx: dict[str, list[str]] = {}
    for sub in ("positive", "negative", "adversarial"):
        d = base / "fixtures" / sub
        if d.exists():
            fx[sub] = [str(p) for p in sorted(d.glob("*")) if p.is_file()]
    pack["fixtures"] = fx
    return pack


# trace:v1 id=impl.bugcorpus-synth.ladder work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-FESAJNS2
def recommend_engine(pack: dict, available: dict[str, bool] | None = None) -> dict:
    sig = pack.get("signature", {}) or {}
    flow = bool(sig.get("dataflow") or sig.get("taint") or "sink" in str(sig).lower())
    xfile = bool(sig.get("cross_file") or sig.get("interprocedural"))
    syntax = bool(sig.get("ast") or sig.get("syntax"))
    text = bool(sig.get("lexical") or sig.get("forbidden_api"))
    if xfile:
        want = "codeql"
    elif flow and available and available.get("semgrep-taint"):
        want = "semgrep-taint"
    elif flow:
        want = "custom"
    elif syntax and available and available.get("ast-grep"):
        want = "ast-grep"
    elif syntax:
        want = "semgrep" if (available or {}).get("semgrep") else "custom"
    elif text:
        want = "lexical"
    else:
        want = "custom"
    if available and not available.get(want, True):
        want = "custom"  # always available fallback
    return {"engine": want, "rationale": LADDER_GUIDE[want], "ladder": LADDER}


# trace:v1 id=impl.bugcorpus-synth.plan work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-FESAJNS2
def write_plan(cwd, bid: str, engine: str | None = None) -> Path:
    from .doctor import doctor

    pack = evidence_pack(cwd, bid)
    avail = doctor()["engines"]
    rec = (
        recommend_engine(pack, avail)
        if not engine
        else {"engine": engine, "rationale": LADDER_GUIDE[engine], "ladder": LADDER}
    )
    plan = {
        "bug": bid,
        "family": pack["family"],
        "related": pack["related"],
        "recommended_engine": rec["engine"],
        "rationale": rec["rationale"],
        "evidence": {k: v for k, v in pack.items() if k != "related"},
        "checklist": [
            "minimize reproducer",
            "positive fixture",
            "fixed negative fixture",
            "neighboring negatives",
            "synthesize detector",
            "verify fixtures",
            "adversarial variants",
            "scan repo",
            "evaluation report",
            "recommend promotion (shadow first)",
        ],
    }
    p = store.bug_dir(cwd, bid) / "detector-plan.yaml"
    p.write_text(yaml.safe_dump(plan, sort_keys=False))
    return p
