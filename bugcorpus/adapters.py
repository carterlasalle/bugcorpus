"""Idempotent cross-harness adapter installation. One canonical skill source."""

from __future__ import annotations

from pathlib import Path

CANON = Path("skills/bug-corpus/SKILL.md")
POINTER = """This repository uses Bug Corpus.
For confirmed defects or requests to search for similar bugs,
use the repository's bug-corpus skill and `uv run bugcorpus`.
See skills/bug-corpus/SKILL.md.
"""
MANAGED_BEGIN = "<!-- managed-bugcorpus:start -->"
MANAGED_END = "<!-- managed-bugcorpus:end -->"


# trace:exempt reason=internal-detail
def _managed_block() -> str:
    return f"{MANAGED_BEGIN}\n{POINTER.strip()}\n{MANAGED_END}\n"


# trace:exempt reason=internal-detail
def upsert_managed(path: Path) -> str:
    block = _managed_block()
    if path.exists():
        text = path.read_text()
        if MANAGED_BEGIN in text and MANAGED_END in text:
            pre = text.split(MANAGED_BEGIN)[0]
            post = text.split(MANAGED_END)[1]
            path.write_text(pre + block + post.lstrip("\n"))
            return "updated"
        path.write_text(text.rstrip("\n") + "\n\n" + block)
        return "appended"
    path.write_text(block)
    return "created"


# trace:v1 id=impl.bugcorpus-adapters.install work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-MKCEMW39
def install(repo: str | Path, harnesses: list[str] | None = None) -> dict:
    repo = Path(repo)
    if not (repo / CANON).exists():
        return {"ok": False, "error": "canonical skill missing: skills/bug-corpus/SKILL.md"}
    targets = {
        "claude": {"skills": [".claude/skills/bug-corpus/SKILL.md"], "pointers": ["CLAUDE.md"]},
        "codex": {"skills": [".codex/skills/bug-corpus/SKILL.md"], "pointers": ["CODEX.md"]},
        "omp": {
            "skills": [".omp/skills/bug-corpus/SKILL.md", ".agents/skills/bug-corpus/SKILL.md"],
            "pointers": [],
        },
        "pi": {"skills": [".pi/skills/bug-corpus/SKILL.md"], "pointers": []},
        "hermes": {"skills": [".hermes/skills/bug-corpus/SKILL.md"], "pointers": []},
    }
    if harnesses:
        targets = {k: v for k, v in targets.items() if k in harnesses}
    report: dict = {"ok": True, "skills": [], "pointers": []}
    src = (repo / CANON).read_text()
    for entry in targets.values():
        for skill_rel in entry["skills"]:
            dest = repo / skill_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists() or dest.read_text() != src:
                dest.write_text(src)
                report["skills"].append(f"{skill_rel} (installed)")
            else:
                report["skills"].append(f"{skill_rel} (unchanged)")
        for p in entry["pointers"]:
            report["pointers"].append(f"{p}: {upsert_managed(repo / p)}")
    # AGENTS.md pointer (bounded managed section, never overwrite user content)
    agents = repo / "AGENTS.md"
    if agents.exists():
        html_begin, html_end = "<!-- bugcorpus:start -->", "<!-- bugcorpus:end -->"
        text = agents.read_text()
        block = f"{html_begin}\n{POINTER.strip()}\n{html_end}\n"
        if html_begin in text and html_end in text:
            pre = text.split(html_begin)[0]
            post = text.split(html_end)[1]
            agents.write_text(pre + block + post.lstrip("\n"))
            report["pointers"].append("AGENTS.md: updated")
        else:
            agents.write_text(text.rstrip("\n") + "\n\n" + block)
            report["pointers"].append("AGENTS.md: appended")
    # OMP plugin manifest (thin adapter over the CLI core)
    omp_plugin = repo / ".omp" / "extensions" / "bug-corpus" / "plugin.json"
    if "omp" in targets:
        omp_plugin.parent.mkdir(parents=True, exist_ok=True)
        if not omp_plugin.exists():
            omp_plugin.write_text(
                '{\n  "name": "bug-corpus",\n'
                '  "commands": ["/bug-corpus", "/bug-learn", "/bug-scan"],\n'
                '  "entry": "uv run bugcorpus"\n}\n'
            )
            report["skills"].append(".omp/extensions/bug-corpus/plugin.json (installed)")
    return report
