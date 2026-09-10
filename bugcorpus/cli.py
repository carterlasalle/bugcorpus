"""bugcorpus CLI: all capabilities from the spec, one thin dispatch layer."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from . import store


# trace:exempt reason=internal-detail
def _out(data, as_json: bool):
    if as_json:
        print(json.dumps(data, indent=2, default=str))
    else:
        print_human(data)


# trace:exempt reason=internal-detail
def print_human(data):
    if isinstance(data, dict) and "findings" in data and "counts" in data:
        c = data["counts"]
        n_det = len(data.get("detectors", []))
        print(
            f"Bug Corpus\n{n_det} detectors\n"
            f"{c.get('clean', 0)} passed\n"
            f"{len(data.get('findings', []))} findings\n"
            f"{c.get('unavailable', 0)} unavailable\n"
            f"{c.get('detector-error', 0)} detector error"
        )
        if data.get("new_findings"):
            print("\nNEW FINDINGS")
            for f in data["new_findings"][:20]:
                print(
                    f"{f.get('bug_family', '')} {f.get('detector_id', '')} "
                    f"{f.get('path', '')}:{f.get('start_line', '')} {f.get('message', '')[:100]}"
                )
        return
    if isinstance(data, dict) and "ok" in data and "detectors" in data:
        print("verify: " + ("OK" if data["ok"] else "FAIL"))
        for r in data["detectors"]:
            m = r.get("metrics", {})
            print(
                f"  {r['detector']}: {'ok' if r['ok'] else 'FAIL'} "
                f"recall={m.get('recall', '?')} adv_recall={m.get('adv_recall', '?')} "
                f"fp={m.get('false_positives', [])} {r.get('error', '')}"
            )
        for e in data.get("schema_errors", []):
            print(f"  schema: {e}")
        return
    print(json.dumps(data, indent=2, default=str))


# trace:exempt reason=thin-cli-dispatch
def cmd_init(a):
    c = Path.cwd() / ".bugcorpus" if a.path == "." else Path(a.path) / ".bugcorpus"
    if c.exists() and not a.force:
        return {"ok": True, "msg": f"{c} already exists"}
    for sub in (
        "corpus",
        "families",
        "detectors",
        "detector-tests",
        "suppressions",
        "schemas",
        "generated",
    ):
        (c / sub).mkdir(parents=True, exist_ok=True)
    if not (c / "config.toml").exists():
        (c / "config.toml").write_text(DEFAULT_CONFIG)
    for name, content in SCHEMAS.items():
        (c / "schemas" / name).write_text(content)
    store.write_index(str(c.parent))
    return {"ok": True, "msg": f"initialized {c}"}


# trace:v1 id=impl.bugcorpus-cli.learn work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-0VGE5410
def cmd_learn(a):
    """Guided learn: capture evidence, rank families, create BugCase skeleton."""
    import yaml as _yaml

    from .searcher import search

    bid = store.next_bug_id()
    if a.before or a.after or a.from_worktree:
        ev = capture_diff(a.before, a.after)
    else:
        ev = {"original.diff": "", "fix.diff": ""}
    cands = search(None, a.title or a.message or "bug") if (a.title or a.message) else []
    bug = {
        "id": bid,
        "title": a.title or "untitled bug",
        "status": "confirmed",
        "created_at": store.utcnow(),
        "language": "python",
        "severity": "medium",
        "confidence": "medium",
        "symptom": a.message or "",
        "root_cause": "",
        "violated_invariant": "",
        "family_id": a.family or "",
        "related_candidates": [c["id"] for c in cands[:5]],
    }
    d = store.bug_dir(None, bid)
    (d / "evidence").mkdir(parents=True, exist_ok=True)
    (d / "evidence" / "original.diff").write_text(ev.get("original.diff", ""))
    (d / "evidence" / "fix.diff").write_text(ev.get("fix.diff", ""))
    (d / "evidence" / "metadata.json").write_text(
        json.dumps({"source": "learn", "before": a.before, "after": a.after}, indent=2)
    )
    (d / "bug.yaml").write_text(_yaml.safe_dump(bug, sort_keys=False))
    (d / "summary.md").write_text(
        f"# {bid} {bug['title']}\n\nTODO: fill symptom/root_cause/violated_invariant.\n"
    )
    for sub in ("positive", "negative", "adversarial"):
        (d / "fixtures" / sub).mkdir(parents=True, exist_ok=True)
    store.write_index()
    steps = [
        "state symptom vs root_cause vs violated_invariant",
        "minimize reproducer into fixtures/positive + fixtures/negative",
        f"run: bugcorpus synthesize {bid}",
        f"run: bugcorpus verify {bid}",
    ]
    return {"id": bid, "family_candidates": cands[:5], "next_steps": steps}


# trace:exempt reason=internal-detail
def capture_diff(before, after) -> dict:
    try:
        if before and after:
            out = subprocess.run(
                ["git", "diff", f"{before}..{after}"],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            ).stdout
            return {"original.diff": "", "fix.diff": out}
        out = subprocess.run(
            ["git", "diff"], capture_output=True, text=True, check=False, timeout=30
        ).stdout
        return {"original.diff": "", "fix.diff": out}
    except (OSError, subprocess.SubprocessError):
        return {"original.diff": "", "fix.diff": ""}


# trace:exempt reason=thin-cli-dispatch
def cmd_show(a):
    return asdict(store.load_bug(None, a.id))


# trace:exempt reason=thin-cli-dispatch
def cmd_related(a):
    from .searcher import related

    return related(None, a.id)


# trace:exempt reason=thin-cli-dispatch
def cmd_search(a):
    from .searcher import search

    return search(None, a.query)


# trace:exempt reason=thin-cli-dispatch
def cmd_family_list(a):
    _ = a
    return store.list_families()


# trace:exempt reason=thin-cli-dispatch
def cmd_family_show(a):
    return store.load_family(None, a.id)


# trace:v1 id=impl.bugcorpus-cli.synthesize work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-FESAJNS2
def cmd_synthesize(a):
    from .synthesizer import write_plan

    target = a.id or a.family
    if a.family and not a.id:
        # family-level: plan per member bug
        members = [b for b in store.list_bugs() if store.load_bug(None, b).family_id == a.family]
        return {"family": a.family, "plans": [str(write_plan(None, m)) for m in members]}
    p = write_plan(None, target, engine=a.engine)
    return {"plan": str(p)}


# trace:v1 id=impl.bugcorpus-cli.verify work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-FESAJNS2
def cmd_verify(a):
    from pathlib import Path as _P

    from .verifier import verify_all

    repo = _P(store.root())
    if a.detector:
        return verify_all(repo, detector=a.detector)
    if a.id and a.id.startswith("BC-"):
        return verify_all(repo, only=a.id)
    return verify_all(repo)


# trace:v1 id=impl.bugcorpus-cli.scan work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-8HPVNRVG
def cmd_scan(a):
    from .scanner import blocking_failed, run_scan

    res = run_scan(
        profile=a.profile,
        scope="changed" if a.changed else "all",
        diff=a.diff,
        detectors=a.detector,
    )
    res["blocking_failed"] = blocking_failed(res)
    return res


# trace:exempt reason=thin-cli-dispatch
def cmd_detector_list(a):
    _ = a
    out = []
    for did in store.list_detectors():
        try:
            from .engines import load_manifest

            m = load_manifest(store.detector_dir(None, did))
            out.append(
                {
                    "id": did,
                    "engine": m.get("engine"),
                    "state": m.get("state"),
                    "family": m.get("family"),
                    "catches": m.get("catches", []),
                }
            )
        except OSError:
            out.append({"id": did, "error": "unreadable"})
    return out


# trace:exempt reason=thin-cli-dispatch
def cmd_detector_show(a):
    from .engines import load_manifest

    return load_manifest(store.detector_dir(None, a.id))


# trace:v1 id=impl.bugcorpus-cli.detector-run work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-8HPVNRVG
def cmd_detector_run(a):
    from .engines import ENGINES, load_manifest
    from .scanner import enrich

    repo = store.root()
    manifest = load_manifest(store.detector_dir(None, a.id))
    engine = ENGINES[manifest.get("engine", "custom")]
    import tomllib as _t

    cfg = {}
    p = repo / ".bugcorpus" / "config.toml"
    if p.exists():
        with open(p, "rb") as f:
            cfg = _t.load(f)
    res = engine.scan(
        repo,
        manifest,
        store.detector_dir(None, a.id),
        a.files or ["."],
        int(cfg.get("scan", {}).get("timeout_seconds", 120)),
    )
    return {
        "status": res.status,
        "detail": res.detail,
        "findings": [enrich(repo, manifest, r).to_dict() for r in res.findings],
    }


# trace:v1 id=impl.bugcorpus-cli.promote work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-FESAJNS2
def cmd_promote(a):
    import yaml as _yaml

    d = store.detector_dir(None, a.id)
    mp = d / "detector.yaml"
    m = _yaml.safe_load(mp.read_text()) or {}
    old = m.get("state")
    if a.to == "blocking":
        from pathlib import Path as _P

        from .verifier import verify_detector

        v = verify_detector(_P(store.root()), a.id)
        if not v["ok"] or not v.get("blocking_eligible"):
            return {
                "ok": False,
                "error": "thresholds unmet; run bugcorpus verify --detector " + a.id,
                "verify": v,
            }
    m["state"] = a.to
    mp.write_text(_yaml.safe_dump(m, sort_keys=False))
    # lineage: record promotion in bug records
    for bid in m.get("catches", []):
        try:
            b = store.load_bug(None, bid)
            if a.id not in b.detector_ids:
                b.detector_ids.append(a.id)
            b.detector_status = a.to
            store.save_bug(None, b)
        except OSError:
            pass
    store.write_index()
    return {"ok": True, "detector": a.id, "from": old, "to": a.to}


# trace:exempt reason=thin-cli-dispatch
def cmd_suppress(a):
    import yaml as _yaml

    if a.list_only:
        return store.load_suppressions()
    entry = {"detector": a.detector, "reason": a.reason, "created_at": store.utcnow()}
    if a.fingerprint:
        entry["fingerprint"] = a.fingerprint
    if a.path:
        entry["path"] = a.path
    if a.expires:
        entry["expires_at"] = a.expires
    p = store.cdir() / "suppressions" / f"{a.detector}.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    data = _yaml.safe_load(p.read_text()) if p.exists() else {}
    items = data.get("suppressions", []) if isinstance(data, dict) else []
    items.append(entry)
    p.write_text(_yaml.safe_dump({"suppressions": items}, sort_keys=False))
    return {"ok": True, "entry": entry}


# trace:exempt reason=thin-cli-dispatch
def cmd_doctor(a):
    _ = a
    from .doctor import doctor

    return doctor()


# trace:exempt reason=thin-cli-dispatch
def cmd_adapters(a):
    from .adapters import check, install

    if a.check:
        return check(store.root(), harnesses=a.only)
    return install(store.root(), harnesses=a.only)


# trace:exempt reason=thin-cli-dispatch
def cmd_export(a):
    from .sarif import to_sarif
    from .scanner import run_scan

    res = run_scan(profile=a.profile)
    if a.format == "sarif":
        return to_sarif(res)
    return res


# trace:exempt reason=thin-cli-dispatch
def cmd_mine(a):
    from .miner import mine

    return mine(store.root(), since=a.since, limit=a.limit)


# trace:exempt reason=thin-cli-dispatch
def cmd_mcp(a):
    _ = a
    from .mcp_server import serve

    serve()
    return {"ok": True}


# trace:exempt reason=internal-detail
def hook_file_from_event(obj) -> str:
    """Liberal recursive search for a *.py path in hook JSON (Claude/Codex shapes differ)."""
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
        elif isinstance(cur, str) and cur.endswith(".py") and len(cur) < 512:
            return cur
    return ""


# trace:v1 id=impl.bugcorpus-cli.hooks work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-8HPVNRVG
def cmd_hooks(a):
    """Cheap post-edit hook: fast-profile scan of the touched file. Always exits 0."""
    _ = a
    import json as _json

    from .engines import load_manifest
    from .scanner import run_scan

    try:
        raw = sys.stdin.read()
        event = _json.loads(raw) if raw.strip() else {}
        path = hook_file_from_event(event)
        if not path.endswith(".py"):
            return  # silent: nothing relevant to scan
        res = run_scan(profile="fast", files=[path])
        states = {}
        for d in res["detectors"]:
            try:
                states[d["detector"]] = load_manifest(store.detector_dir(None, d["detector"])).get(
                    "state", ""
                )
            except OSError:
                states[d["detector"]] = ""
        lines = []
        for d in res["detectors"]:
            if d["status"] == "detector-error":
                lines.append(
                    f"bugcorpus hook: detector {d['detector']} errored; "
                    f"run `uv run bugcorpus verify --detector {d['detector']}`"
                )
        for f in res["findings"]:
            if states.get(f["detector_id"]) in ("warning", "blocking"):
                lines.append(
                    f"bugcorpus hook: {f['detector_id']} {f['path']}:"
                    f"{f['start_line']} {f['message'][:160]}"
                )
        if lines:
            print("\n".join(lines))
    except (OSError, ValueError):
        pass  # hooks are advisory; CI verify/scan fail loudly instead
    return


# trace:exempt reason=internal-detail
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bugcorpus", description="Bug Corpus")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--cwd", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init")
    s.add_argument("path", nargs="?", default=".")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("learn")
    s.add_argument("--title", default="")
    s.add_argument("-m", "--message", default="")
    s.add_argument("--before", default="")
    s.add_argument("--after", default="")
    s.add_argument("--from-worktree", action="store_true")
    s.add_argument("--family", default="")
    s.set_defaults(fn=cmd_learn)

    s = sub.add_parser("show")
    s.add_argument("id")
    s.set_defaults(fn=cmd_show)
    s = sub.add_parser("related")
    s.add_argument("id")
    s.set_defaults(fn=cmd_related)
    s = sub.add_parser("search")
    s.add_argument("query")
    s.set_defaults(fn=cmd_search)

    s = sub.add_parser("family")
    fs = s.add_subparsers(dest="fcmd", required=True)
    f = fs.add_parser("list")
    f.set_defaults(fn=cmd_family_list)
    f = fs.add_parser("show")
    f.add_argument("id")
    f.set_defaults(fn=cmd_family_show)

    s = sub.add_parser("synthesize")
    s.add_argument("id", nargs="?")
    s.add_argument("--family", default="")
    s.add_argument("--engine", default=None)
    s.set_defaults(fn=cmd_synthesize)

    s = sub.add_parser("verify")
    s.add_argument("id", nargs="?")
    s.add_argument("--detector", default=None)
    s.set_defaults(fn=cmd_verify)

    s = sub.add_parser("scan")
    s.add_argument("--profile", default="pr", choices=["fast", "pr", "full"])
    s.add_argument("--all", action="store_true")
    s.add_argument("--changed", action="store_true")
    s.add_argument("--diff", default=None)
    s.add_argument("--detector", action="append", default=None)
    s.set_defaults(fn=cmd_scan)

    s = sub.add_parser("detector")
    ds = s.add_subparsers(dest="dcmd", required=True)
    d = ds.add_parser("list")
    d.set_defaults(fn=cmd_detector_list)
    d = ds.add_parser("show")
    d.add_argument("id")
    d.set_defaults(fn=cmd_detector_show)
    d = ds.add_parser("run")
    d.add_argument("id")
    d.add_argument("files", nargs="*")
    d.set_defaults(fn=cmd_detector_run)

    s = sub.add_parser("promote")
    s.add_argument("id")
    s.add_argument(
        "--to",
        required=True,
        choices=["draft", "candidate", "shadow", "warning", "blocking", "retired"],
    )
    s.set_defaults(fn=cmd_promote)

    s = sub.add_parser("suppress")
    s.add_argument("detector", nargs="?")
    s.add_argument("--fingerprint", default="")
    s.add_argument("--path", default="")
    s.add_argument("--reason", default="")
    s.add_argument("--expires", default="")
    s.add_argument("--list", dest="list_only", action="store_true")
    s.set_defaults(fn=cmd_suppress)

    s = sub.add_parser("doctor")
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("adapters")
    ad = s.add_subparsers(dest="acmd", required=True)
    a = ad.add_parser("install")
    a.add_argument("--only", action="append", default=None)
    a.add_argument(
        "--check",
        action="store_true",
        help="verify installed adapters match sources instead of installing",
    )
    a.set_defaults(fn=cmd_adapters)

    s = sub.add_parser("export")
    s.add_argument("format", nargs="?", default="sarif")
    s.add_argument("--profile", default="full")
    s.set_defaults(fn=cmd_export)

    s = sub.add_parser("mine-history")
    s.add_argument("--since", default=None)
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(fn=cmd_mine)
    s = sub.add_parser("mcp")
    s.set_defaults(fn=cmd_mcp)

    s = sub.add_parser("hooks")
    hs = s.add_subparsers(dest="hcmd", required=True)
    h = hs.add_parser("post-tool-use")
    h.set_defaults(fn=cmd_hooks)
    return p


DEFAULT_CONFIG = """# Bug Corpus configuration
[corpus]
root = ".bugcorpus"

[scan]
include = ["bugcorpus/**/*.py", ".bugcorpus/detectors/**/*.py", ".bugcorpus/corpus/**/fixtures/**/*.py"]
exclude = [".venv/**", ".git/**", ".bugcorpus/cache/**"]
timeout_seconds = 120
profiles = ["fast", "pr", "full"]

[promotion]
recall = 1.0
neg_fp = 0
adv_recall_blocking = 1.0

[baseline]
file = ".bugcorpus/baseline.json"
fail_on_new_blocking = true
"""

SCHEMAS = {
    "bug-case.schema.json": '{"title":"bug-case","type":"object","required":["id","title","symptom","root_cause","violated_invariant"]}',
    "detector.schema.json": '{"title":"detector","type":"object","required":["id","engine","state","family"]}',
    "finding.schema.json": '{"title":"finding","type":"object","required":["detector_id","path","start_line","fingerprint","message"]}',
}


# trace:v1 id=impl.bugcorpus-cli.dispatch work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-8HPVNRVG
def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv  # accepted before or after the subcommand
    argv = [a for a in argv if a != "--json"]
    args = build_parser().parse_args(argv)
    if args.cwd:
        import os

        os.chdir(args.cwd)
    try:
        res = args.fn(args)
    except (OSError, ValueError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if res is None:
        return 0
    _out(res, as_json or args.json)
    # exit codes: verify/scan failures must fail CI loudly
    if isinstance(res, dict):
        if "ok" in res and res["ok"] is False:
            return 1
        if res.get("blocking_failed"):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
