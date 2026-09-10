"""Minimal MCP server (stdio JSON-RPC) over the same library the CLI uses.

Speaks the Model Context Protocol handshake hosts require: initialize /
notifications / tools/list / tools/call with JSON-RPC 2.0 envelopes.
Tool implementations live in dispatch(); the transport adds no logic.
"""

from __future__ import annotations

import json
import sys
from typing import Any

TOOL_SCHEMAS: dict[str, dict] = {
    "bugcorpus_status": {
        "description": "Counts of known bugs, detectors, and families.",
        "inputSchema": {
            "type": "object",
            "properties": {"cwd": {"type": "string"}},
        },
    },
    "bugcorpus_search": {
        "description": "Search bug cases, invariants, symbols, and families.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "cwd": {"type": "string"}},
            "required": ["query"],
        },
    },
    "bugcorpus_show": {
        "description": "Show one BugCase record.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "cwd": {"type": "string"}},
            "required": ["id"],
        },
    },
    "bugcorpus_related": {
        "description": "Bugs related to one BugCase (same family, shared symbols).",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "cwd": {"type": "string"}},
            "required": ["id"],
        },
    },
    "bugcorpus_verify": {
        "description": "Verify detector fixtures (recall/precision metrics).",
        "inputSchema": {
            "type": "object",
            "properties": {"cwd": {"type": "string"}},
        },
    },
    "bugcorpus_scan": {
        "description": "Scan the repo with promoted detectors.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "profile": {"type": "string", "enum": ["fast", "pr", "full"]},
                "cwd": {"type": "string"},
            },
        },
    },
}

SERVER_INFO = {"name": "bugcorpus", "version": "0.1.0"}


# trace:v1 id=impl.bugcorpus-mcp.dispatch work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-MKCEMW39
def dispatch(name: str, args: dict) -> Any:
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


# trace:exempt reason=internal-detail
def _result(rid: Any, result: dict) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": rid, "result": result})


# trace:exempt reason=internal-detail
def _error(rid: Any, code: int, message: str) -> str:
    payload: dict = {"jsonrpc": "2.0", "error": {"code": code, "message": message}}
    if rid is not None:
        payload["id"] = rid
    return json.dumps(payload)


# trace:exempt reason=internal-detail
def handle_message(msg: dict) -> str | None:
    """One JSON-RPC message in, one response string out (None = notification)."""
    method = msg.get("method")
    rid = msg.get("id")
    params = msg.get("params", {}) or {}
    if method == "initialize":
        version = params.get("protocolVersion", "2024-11-05")
        return _result(
            rid,
            {
                "protocolVersion": version,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        )
    if method == "ping":
        return _result(rid, {})
    if method == "tools/list":
        return _result(
            rid,
            {"tools": [{"name": name, **schema} for name, schema in TOOL_SCHEMAS.items()]},
        )
    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {}) or {}
        if name not in TOOL_SCHEMAS:
            return _error(rid, -32602, f"unknown tool {name!r}")
        try:
            result = dispatch(name, args)
        except Exception as e:  # noqa: BLE001 -- tool failure is data, not transport failure
            return _result(
                rid,
                {
                    "content": [{"type": "text", "text": f"error: {e}"[:2000]}],
                    "isError": True,
                },
            )
        return _result(
            rid, {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}
        )
    if rid is None:
        return None  # notification (initialized, cancelled, ...): no response
    return _error(rid, -32601, f"unknown method {method!r}")


# trace:exempt reason=thin-stdio-loop
def serve() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue  # never let a bad line corrupt the stream
        try:
            out = handle_message(msg)
        except Exception as e:  # noqa: BLE001 -- protocol must never crash the server
            out = _error(msg.get("id"), -32603, f"internal error: {e}"[:500])
        if out is not None:
            sys.stdout.write(out + "\n")
            sys.stdout.flush()
