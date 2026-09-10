"""Minimal MCP server (stdio JSON-RPC) over the same library the CLI uses."""

from __future__ import annotations

import json
import sys

TOOLS = [
    "bugcorpus_status",
    "bugcorpus_search",
    "bugcorpus_show",
    "bugcorpus_related",
    "bugcorpus_verify",
    "bugcorpus_scan",
]


# trace:v1 id=impl.bugcorpus-mcp.dispatch work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-MKCEMW39
def dispatch(name: str, args: dict):
    from . import store
    from .scanner import run_scan
    from .searcher import related, search
    from .verifier import verify_all

    cwd = args.get("cwd")
    if name == "bugcorpus_status":
        return {
            "bugs": len(store.list_bugs(cwd)),
            "detectors": len(store.list_detectors(cwd)),
            "families": len(store.list_families(cwd)),
        }
    if name == "bugcorpus_search":
        return search(cwd, args.get("query", ""))
    if name == "bugcorpus_show":
        return vars(store.load_bug(cwd, args["id"]))
    if name == "bugcorpus_related":
        return related(cwd, args["id"])
    if name == "bugcorpus_verify":
        from pathlib import Path

        return verify_all(Path(store.root(cwd)))
    if name == "bugcorpus_scan":
        return run_scan(str(store.root(cwd)), profile=args.get("profile", "pr"))
    raise ValueError(f"unknown tool {name}")


# trace:exempt reason=thin-stdio-loop
def serve() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            rid = req.get("id")
            if req.get("method") == "tools/list":
                res = {"tools": [{"name": t} for t in TOOLS]}
            elif req.get("method") == "tools/call":
                p = req.get("params", {})
                res = {"result": dispatch(p.get("name", ""), p.get("arguments", {}))}
            else:
                res = {"error": f"unknown method {req.get('method')}"}
            sys.stdout.write(json.dumps({"id": rid, **res}) + "\n")
            sys.stdout.flush()
        except Exception as e:  # noqa: BLE001 -- protocol must never crash the server
            sys.stdout.write(json.dumps({"error": str(e)[:500]}) + "\n")
            sys.stdout.flush()
