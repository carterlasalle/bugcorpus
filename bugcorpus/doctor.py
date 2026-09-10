"""Tool discovery: report capabilities, never hard-fail on missing engines."""

from __future__ import annotations

import shutil
import subprocess

TOOLS = {
    "ruff": ["--version"],
    "basedpyright": ["--version"],
    "pyright": ["--version"],
    "mypy": ["--version"],
    "pylint": ["--version"],
    "ast-grep": ["--version"],
    "semgrep": ["--version"],
    "codeql": ["--version"],
    "pyre": ["--version"],
    "python": ["--version"],
}


# trace:exempt reason=internal-detail
def probe(tool: str) -> dict:
    path = shutil.which(tool)
    if not path:
        install = {
            "ruff": "uv add ruff / pipx install ruff",
            "semgrep": "uv tool install semgrep",
            "ast-grep": "brew install ast-grep / cargo install ast-grep",
            "codeql": "https://codeql.github.com/docs/codeql-cli/",
            "pyre": "pip install pyre-check",
        }.get(tool, f"install {tool}")
        return {"tool": tool, "available": False, "path": None, "version": None, "install": install}
    try:
        p = subprocess.run(
            [tool, *TOOLS[tool]], capture_output=True, text=True, timeout=15, check=False
        )
        ver = (p.stdout or p.stderr).strip().splitlines()
        return {
            "tool": tool,
            "available": True,
            "path": path,
            "version": ver[0][:120] if ver else "unknown",
            "install": None,
        }
    except (OSError, subprocess.SubprocessError):
        return {
            "tool": tool,
            "available": False,
            "path": path,
            "version": None,
            "install": f"install {tool}",
        }


# trace:v1 id=impl.bugcorpus-doctor.corpus-health work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-0VGE5410
def corpus_health(cwd: str | None = None) -> list[dict]:
    """Audit the corpus setup itself: discovery, manifests, families, scope.

    Catches the failure mode where everything looks installed but nothing
    is discovered or scanned: nested detector dirs, unknown manifest keys,
    scope globs matching zero files.
    """
    from . import store
    from .models import COSTS, ENGINES, SEVERITIES, STATES, Detector

    issues: list[dict] = []

    def err(msg: str) -> None:
        issues.append({"level": "error", "message": msg})

    def warn(msg: str) -> None:
        issues.append({"level": "warning", "message": msg})

    dids = store.list_detectors(cwd)
    base = store.cdir(cwd) / "detectors"
    if not dids and base.exists() and any(base.iterdir()):
        err(
            "detectors/ is non-empty but no detectors discovered: check nested layout and detector.yaml manifests"
        )
    known_keys = set(Detector.__dataclass_fields__)
    for did in dids:
        try:
            det, ddir = store.load_detector(cwd, did)
        except (OSError, ValueError):
            err(f"detector {did}: manifest unreadable")
            continue
        try:
            raw = store.load_yaml(ddir / "detector.yaml")
        except (OSError, ValueError):
            raw = {}
        for key in sorted(set(raw) - known_keys):
            hint = " (did you mean 'catches'?)" if key == "bug" else ""
            warn(f"detector {did}: unknown manifest key {key!r}{hint}")
        if det.engine not in ENGINES:
            err(f"detector {did}: unknown engine {det.engine!r}")
        if det.state not in STATES:
            err(f"detector {did}: unknown state {det.state!r}")
        if det.cost not in COSTS:
            warn(f"detector {did}: unknown cost {det.cost!r}")
        if "severity" in raw and raw["severity"] not in SEVERITIES:
            warn(
                f"detector {did}: suspicious severity {raw['severity']!r} "
                f"(expected one of {', '.join(SEVERITIES)})"
            )
        if not det.family:
            warn(f"detector {did}: no family assigned")
        for bid in det.catches:
            if bid not in store.list_bugs(cwd):
                warn(f"detector {did}: catches unknown bug {bid}")
    bugs = [store.load_bug(cwd, b) for b in store.list_bugs(cwd)]
    unfamilied = sorted(b.id for b in bugs if not b.family_id)
    if unfamilied:
        warn(f"bugs without family: {', '.join(unfamilied)}")
    for fid in store.list_families(cwd):
        members = [b.id for b in bugs if b.family_id == fid]
        fams = store.load_family(cwd, fid)
        declared = fams.get("members", members)
        if not members and not declared:
            warn(f"family {fid}: no member bugs")
    try:
        from .scanner import collect_files, config

        repo = store.root(cwd)
        files = collect_files(repo, config(str(repo)))
        if not files:
            err("scan scope matches zero files: check [scan] include patterns in config.toml")
        elif not any(not f.startswith(".bugcorpus/") for f in files):
            warn("scan scope matches only .bugcorpus paths: no repository source will be scanned")
    except (OSError, ValueError):
        warn("could not evaluate scan scope")
    states = []
    for did in dids:
        try:
            det, _ = store.load_detector(cwd, did)
            states.append(det.state)
        except (OSError, ValueError):
            pass
    if "blocking" in states and not (store.cdir(cwd) / "baseline.json").exists():
        warn("blocking detectors present but no baseline.json recorded")
    return issues


# trace:v1 id=impl.bugcorpus-doctor.capabilities work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-8HPVNRVG
def doctor() -> dict:
    tools = [probe(t) for t in TOOLS]
    engines = {
        "existing": True,
        "lexical": True,
        "custom": True,
        "ast-grep": shutil.which("ast-grep") is not None,
        "semgrep": shutil.which("semgrep") is not None,
        "semgrep-taint": shutil.which("semgrep") is not None,
        "codeql": shutil.which("codeql") is not None,
        "pysa": shutil.which("pyre") is not None,
    }
    return {
        "tools": tools,
        "engines": engines,
        "corpus": corpus_health(),
        "recommendation": "custom+lexical always available; "
        "install ast-grep/semgrep for stronger structural rules",
    }
