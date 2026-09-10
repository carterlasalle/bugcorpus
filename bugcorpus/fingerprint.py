"""Stable finding fingerprints: no raw line numbers."""

from __future__ import annotations

import hashlib
import re

_WS = re.compile(r"\s+")


# trace:exempt reason=internal-detail
def normalize_snippet(text: str) -> str:
    text = _WS.sub(" ", text.strip())
    # normalize string quotes and numbers so trivial edits don't move fingerprint
    text = re.sub(r"'", '"', text)
    return text[:500]


# trace:v1 id=impl.bugcorpus-fingerprint.stable work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-8HPVNRVG
def fingerprint(detector_id: str, path: str, enclosing: str, snippet: str) -> str:
    h = hashlib.sha1()
    h.update(detector_id.encode())
    h.update(b"\0" + path.encode())
    h.update(b"\0" + (enclosing or "").encode())
    h.update(b"\0" + normalize_snippet(snippet).encode())
    return "fp_" + h.hexdigest()[:16]
