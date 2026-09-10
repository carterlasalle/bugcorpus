"""Deterministic lexical search over titles, invariants, symbols, families."""

from __future__ import annotations

import re

from . import store


# trace:v1 id=impl.bugcorpus-search.lexical work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-0VGE5410
def search(cwd, query: str) -> list[dict]:
    toks = [t.lower() for t in re.findall(r"[a-zA-Z0-9_.\-/]+", query)]
    hits = []
    for bid in store.list_bugs(cwd):
        try:
            b = store.load_bug(cwd, bid)
        except OSError:
            continue
        hay = " ".join(
            [
                b.id,
                b.title,
                b.symptom,
                b.root_cause,
                b.violated_invariant,
                b.subsystem,
                b.family_id,
                " ".join(b.relevant_symbols),
                " ".join(b.relevant_calls),
                " ".join(b.relevant_modules),
                str(b.semantic_signature),
            ]
        ).lower()
        score = sum(hay.count(t) for t in toks)
        if score:
            hits.append(
                {
                    "id": b.id,
                    "title": b.title,
                    "family": b.family_id,
                    "score": score,
                    "invariant": b.violated_invariant[:200],
                }
            )
    for fid in store.list_families(cwd):
        try:
            fam = store.load_family(cwd, fid)
        except OSError:
            continue
        hay = f"{fid} {fam}".lower()
        score = sum(hay.count(t) for t in toks)
        if score:
            hits.append(
                {
                    "id": f"family:{fid}",
                    "title": fam.get("title", fid),
                    "family": fid,
                    "score": score,
                    "invariant": "",
                }
            )
    return sorted(hits, key=lambda h: -h["score"])


# trace:v1 id=impl.bugcorpus-search.related work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-0VGE5410
def related(cwd, bid: str) -> list[dict]:
    base = store.load_bug(cwd, bid)
    out = []
    for other in store.list_bugs(cwd):
        if other == bid:
            continue
        try:
            b = store.load_bug(cwd, other)
        except OSError:
            continue
        score = 0
        if other in (base.related_bug_cases or []):
            score += 5  # explicitly declared relationship
        if b.family_id and b.family_id == base.family_id:
            score += 10
        score += len(set(b.relevant_symbols) & set(base.relevant_symbols)) * 3
        score += len(set(b.relevant_calls) & set(base.relevant_calls)) * 3
        if b.subsystem and b.subsystem == base.subsystem:
            score += 2
        # invariant word overlap
        aw = set(re.findall(r"[a-z]{4,}", base.violated_invariant.lower()))
        bw = set(re.findall(r"[a-z]{4,}", b.violated_invariant.lower()))
        score += len(aw & bw)
        if score:
            out.append({"id": b.id, "title": b.title, "family": b.family_id, "score": score})
    return sorted(out, key=lambda h: -h["score"])[:10]
