"""stale-state-after-await-v1: snapshot used after await without refresh.

Minimum semantic model:
  need: function-local def/use, await boundary detection, variable rebinding
  do NOT need: global points-to analysis, full type inference,
    interprocedural propagation (documented v1 limit: values passed through
    helpers or aliased through containers are missed; a future v2 may add that).

Protocol: `python detect.py --format json <files...>` prints a JSON list of
{path,start_line,end_line,message,explanation,evidence,remediation}.
"""
from __future__ import annotations

import argparse
import ast
import glob
import json
import sys

MESSAGE = ("Snapshot obtained before an await is reused afterward. "
           "Snapshots may become stale across suspension points.")
EXPLANATION = ("Derived from BC-000001 (family stale-state-after-await): a StateStore "
               "snapshot taken before an await was dereferenced after the await, "
               "observing state invalidated by a concurrent task.")
REMEDIATION = "Reacquire the snapshot after the final await before using it."


# trace:exempt reason=internal-detail
def is_acquire_call(node: ast.AST) -> bool:
    if isinstance(node, ast.Await):
        node = node.value
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
    return "snapshot" in name.lower()


# trace:v1 id=impl.detector-stale-state.check work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-FESAJNS2
def check_file(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=path)
    except (SyntaxError, OSError, UnicodeDecodeError):
        return []
    findings = []
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]:
        acquires: list[tuple[int, str]] = []  # (lineno, var) from snapshot calls
        writes: dict[str, list[int]] = {}  # every plain assignment per var
        awaits: list[int] = []
        uses: list[tuple[int, str]] = []
        for n in ast.walk(fn):
            if isinstance(n, ast.Await):
                awaits.append(n.lineno)
            elif (isinstance(n, ast.Assign) and len(n.targets) == 1
                    and isinstance(n.targets[0], ast.Name)):
                writes.setdefault(n.targets[0].id, []).append(n.lineno)
                if is_acquire_call(n.value):
                    acquires.append((n.lineno, n.targets[0].id))
            elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                uses.append((n.lineno, n.id))
        if not awaits:
            continue
        tracked = {v for _, v in acquires}
        reported: set[str] = set()
        for lineno, var in sorted(uses):
            if var not in tracked or var in reported:
                continue
            acq = [a for a, v in acquires if v == var and a < lineno]
            aws = [w for w in awaits if w < lineno]
            prior_writes = [w for w in writes.get(var, []) if w < lineno]
            if not prior_writes:
                continue
            last_write = max(prior_writes)
            # a reassignment from any source after the await drops the stale value
            if acq and aws and max(acq) < max(aws) and last_write in acq:
                findings.append({
                    "path": path, "start_line": lineno, "end_line": lineno,
                    "message": MESSAGE, "explanation": EXPLANATION,
                    "evidence": f"{var} acquired line {max(acq)}, "
                                f"await line {max(aws)}, used line {lineno}",
                    "remediation": REMEDIATION})
                reported.add(var)
    return findings


# trace:exempt reason=thin-subprocess-shim
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", default="json")
    ap.add_argument("files", nargs="*")
    a = ap.parse_args()
    paths: list[str] = []
    for f in a.files:
        paths.extend(glob.glob(f, recursive=True) or [f])
    out = []
    for p in paths:
        if p.endswith(".py"):
            try:
                out.extend(check_file(p))
            except OSError:
                continue
    if a.format == "json":
        json.dump(out, sys.stdout, indent=2)
    else:
        for f in out:
            print(f"{f['path']}:{f['start_line']}: {f['message']}")


if __name__ == "__main__":
    main()
