# trace:exempt reason=test-fixture-intentional-detector-pattern
"""Detector for BC-000001: pop/del clears lost under merge-on-write.

Contract: `python merge_pop_clear.py --format json <files...>` prints a JSON
list of findings. A crash is reported as a `detector-error` finding, never as
clean output.

Minimum semantic model: a file is a merge-store when it defines a
`_merge_*` helper or a `_write` that calls one; inside such files, `.pop()`
and `del` targeting state dicts in `*clear*` methods cannot survive the merge
and must be `None`-tombstone writes instead. Files without merge logic are
out of scope (plain-overwrite pop is correct there).
"""

from __future__ import annotations

import argparse
import ast
import json
import sys


def _is_merge_store(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("_merge_"):
            return True
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "_write":
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                func = sub.func
                name = ""
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if "merge" in name:
                    return True
    return False


def _clear_functions(tree: ast.Module):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and "clear" in node.name:
            yield node


def _findings_for(path: str, text: str) -> list[dict]:
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as exc:
        return [
            {
                "file": path,
                "line": exc.lineno or 1,
                "rule": "BC-000001",
                "severity": "detector-error",
                "message": f"unparsable file: {exc}",
            }
        ]
    if not _is_merge_store(tree):
        return []
    findings = []
    for func in _clear_functions(tree):
        for sub in ast.walk(func):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                if sub.func.attr == "pop":
                    findings.append(
                        {
                            "file": path,
                            "line": sub.lineno,
                            "rule": "BC-000001",
                            "severity": "warning",
                            "message": (
                                f"{func.name}: dict.pop deletion will not survive "
                                "merge-on-write; write None instead"
                            ),
                        }
                    )
            elif isinstance(sub, ast.Delete):
                findings.append(
                    {
                        "file": path,
                        "line": sub.lineno,
                        "rule": "BC-000001",
                        "severity": "warning",
                        "message": (
                            f"{func.name}: del deletion will not survive "
                            "merge-on-write; write None instead"
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
                    "rule": "BC-000001",
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
