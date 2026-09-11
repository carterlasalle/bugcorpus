# trace:exempt reason=test-fixture-intentional-detector-pattern
"""Detector for BC-000002: change-base fan-out inside per-item loops.

Contract: `python detect.py --format json <files...>` prints a JSON list of
findings. Unparsable/unreadable files report `detector-error`, never silence;
non-Python files are out of scope and skipped.

Minimum semantic model: any `default_base()` call lexically inside a
`for`/`while` body is a finding, regardless of indirection (the method always
spawns multiple git subprocesses, so per-item invocation is the violation;
hoisting is the only fix). Explicitly NOT modeled: whether the loop is
hot, single-subprocess calls in loops, other expensive APIs.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys


def _loops(tree: ast.Module):
    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            yield node


def _has_default_base(node: ast.AST) -> list[int]:
    lines = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name == "default_base":
                lines.append(sub.lineno)
    return lines


def _callee_targets(tree: ast.Module) -> dict:
    """Function name -> default_base() call lines (one hop, same file)."""
    targets = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lines = _has_default_base(node)
            if lines:
                targets[node.name] = lines
    return targets


def _findings_for(path: str, text: str) -> list[dict]:
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as exc:
        return [
            {
                "file": path,
                "line": exc.lineno or 1,
                "rule": "BC-000002",
                "severity": "detector-error",
                "message": f"unparsable file: {exc}",
            }
        ]
    findings = []
    callees = _callee_targets(tree)
    for loop in _loops(tree):
        seen: set = set()
        for lineno in _has_default_base(loop):
            seen.add(lineno)
            findings.append(
                {
                    "file": path,
                    "line": lineno,
                    "rule": "BC-000002",
                    "severity": "warning",
                    "message": (
                        "default_base() inside a loop body: hoist the change-base "
                        "resolution out of the loop and thread it as a parameter"
                    ),
                }
            )
        for sub in ast.walk(loop):
            if not isinstance(sub, ast.Call):
                continue
            func = sub.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name in callees and sub.lineno not in seen:
                findings.append(
                    {
                        "file": path,
                        "line": sub.lineno,
                        "rule": "BC-000002",
                        "severity": "warning",
                        "message": (
                            f"{name}() calls default_base() and is invoked inside a "
                            "loop body: hoist the change-base resolution out of "
                            "the loop and thread it as a parameter"
                        ),
                    }
                )
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", default="json")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)
    out: list[dict] = []
    for path in args.files:
        if not path.endswith(".py"):
            continue  # out of scope: declared languages=[python], not an error
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            out.append(
                {
                    "file": path,
                    "line": 1,
                    "rule": "BC-000002",
                    "severity": "detector-error",
                    "message": f"unreadable file: {exc}",
                }
            )
            continue
        out.extend(_findings_for(path, text))
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
