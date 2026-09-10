"""Tiny SDK for custom detectors. Keep small and composable."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from .fingerprint import fingerprint
from .models import Finding


@dataclass
class ScanScope:
    files: list[str]
    changed_lines: dict[str, set[int]] | None = None  # path -> lines, None = full


@dataclass
class DetectorMetadata:
    id: str
    family: str
    bug_cases: list[str] = field(default_factory=list)
    severity: str = "medium"
    confidence: str = "medium"


# trace:exempt reason=internal-detail
def parse(path: str) -> ast.Module | None:
    try:
        return ast.parse(Path(path).read_text(), filename=path)
    except (SyntaxError, OSError, UnicodeDecodeError):
        return None


# trace:exempt reason=internal-detail
def enclosing_symbol(tree: ast.Module, lineno: int) -> str:
    best, depth_best = "", -1
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if not node.lineno <= lineno <= (node.end_lineno or node.lineno):
            continue
        if node.lineno >= depth_best:
            best, depth_best = node.name, node.lineno
    return best


# trace:exempt reason=internal-detail
def snippet_at(path: str, lineno: int) -> str:
    try:
        lines = Path(path).read_text().splitlines()
        if 1 <= lineno <= len(lines):
            return lines[lineno - 1].strip()
    except OSError:
        pass
    return ""


# trace:v1 id=impl.bugcorpus-sdk.make-finding work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-FESAJNS2
def make_finding(
    meta: DetectorMetadata,
    path: str,
    node: ast.AST,
    message: str,
    explanation: str = "",
    remediation: str = "",
    evidence: str = "",
) -> Finding:
    lineno = getattr(node, "lineno", 1)
    end = getattr(node, "end_lineno", lineno) or lineno
    tree = parse(path)
    enc = enclosing_symbol(tree, lineno) if tree else ""
    snip = evidence or snippet_at(path, lineno)
    return Finding(
        detector_id=meta.id,
        path=path,
        start_line=lineno,
        end_line=end,
        severity=meta.severity,
        confidence=meta.confidence,
        message=message,
        explanation=explanation,
        evidence=snip,
        remediation=remediation,
        bug_family=meta.family,
        bug_cases=list(meta.bug_cases),
        fingerprint=fingerprint(meta.id, path, enc, snip or message),
    )


# trace:exempt reason=internal-detail
def in_changed(scope: ScanScope, path: str, lineno: int) -> bool:
    if scope.changed_lines is None:
        return True
    lines = scope.changed_lines.get(path)
    if lines is None:
        # changed-file mode: file not in diff -> skip unless full scan
        return False
    return lineno in lines


# trace:exempt reason=internal-detail
def python_files(repo_root: str, files: list[str]) -> list[str]:
    out = []
    for f in files:
        p = Path(repo_root) / f if not Path(f).is_absolute() else Path(f)
        if p.suffix == ".py" and p.is_file():
            out.append(str(p))
    return out
