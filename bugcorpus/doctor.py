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
        "recommendation": "custom+lexical always available; "
        "install ast-grep/semgrep for stronger structural rules",
    }
