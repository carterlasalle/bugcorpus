"""Bounded history mining: candidates from git evidence, never auto-confirmed."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

FIX_RE = re.compile(
    r"\b(fix|fixes|fixed|bug|regression|hotfix|patch|resolve[sd]?)\b", re.IGNORECASE
)
TEST_RE = re.compile(r"\btest", re.IGNORECASE)


# trace:v1 id=impl.bugcorpus-miner.history work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-0VGE5410
def mine(repo: str | Path, since: str | None = None, limit: int = 20) -> list[dict]:
    cmd = [
        "git",
        "log",
        f"--max-count={limit}",
        "--pretty=format:%H%x00%s%x00%b%x00%an%x00%ad",
        "--date=short",
        "--name-status",
    ]
    if since:
        cmd.append(since + "..HEAD")
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, cwd=repo, check=False, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    out, cands = p.stdout, []
    for chunk in out.split("\n\n"):
        lines = chunk.splitlines()
        if not lines:
            continue
        head = lines[0].split("\x00")
        if len(head) < 5:
            continue
        sha, subj, body, author, date = (
            head[0].split()[-1] if " " in head[0] else head[0],
            head[1] if len(head) > 1 else "",
            head[2] if len(head) > 2 else "",
            head[3] if len(head) > 3 else "",
            head[4] if len(head) > 4 else "",
        )
        files = [ln[2:] for ln in lines[1:] if re.match(r"^[AMD]\s", ln)]
        score, reasons = 0, []
        if FIX_RE.search(subj + " " + body):
            score += 3
            reasons.append("fix-like message")
        touched_test = any(TEST_RE.search(f) for f in files)
        if touched_test:
            score += 2
            reasons.append("touches tests")
        if re.search(r"#\d+", subj + body):
            score += 1
            reasons.append("issue reference")
        if score >= 3:
            cands.append(
                {
                    "sha": sha,
                    "subject": subj,
                    "author": author,
                    "date": date,
                    "files": files,
                    "score": score,
                    "reasons": reasons,
                    "status": "candidate (needs agent review)",
                }
            )
    return cands[:limit]
