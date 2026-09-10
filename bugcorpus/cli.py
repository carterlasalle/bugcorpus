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
        n_det = len(data.get("detectors", []))
        print(f"Bug Corpus: {n_det} detectors")
        for r in data.get("detectors", []):
            n = len(r.get("findings", []))
            print(
                f"  {r.get('detector', '?')} [{r.get('state', '?')}]: "
                f"{r.get('status', '?')}" + (f", {n} finding(s)" if n else "")
            )
        if data.get("blocking_failed"):
            print("gate: FAIL (new blocking findings or detector errors)")
        else:
            print(
                "gate: PASS (only blocking detectors gate; "
                "warning/shadow findings never fail the build)"
            )
        if data.get("new_findings"):
            print("\nNEW FINDINGS (not in baseline)")
            for f in data["new_findings"][:20]:
                print(
                    f"{f.get('bug_family', '')} {f.get('detector_id', '')} "
                    f"{f.get('path', '')}:{f.get('start_line', '')} {f.get('message', '')[:100]}"
                )
        return
    if isinstance(data, dict) and data.get("version") == 2 and "bugs" in data:
        from .coverage import render_human

        print(render_human(data))
        return
    if isinstance(data, dict) and "bug_count" in data and "version" in data:
        print(f"bugcorpus {data['version']} ({data.get('bin', '')})")
        print(f"{data.get('bug_count', 0)} bugs, {data.get('detector_count', 0)} detectors indexed")
        print("adapters: " + ("OK" if data.get("ok") else "FAIL"))
        for note in data.get("notes", []):
            print(f"note: {note}")
        return
    if isinstance(data, dict) and "ok" in data and isinstance(data.get("detectors"), list):
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
    from .adapters import install

    c = Path.cwd() / ".bugcorpus" if a.path == "." else Path(a.path) / ".bugcorpus"
    if not c.exists() or a.force:
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
            (c / "config.toml").write_text(render_config(detect_scan_includes(c.parent)))
        for name, content in SCHEMAS.items():
            (c / "schemas" / name).write_text(content)
        store.write_index(str(c.parent))
        msg = f"initialized {c}"
    else:
        msg = f"{c} already exists"
    # init is the single setup command: corpus scaffold plus adapters,
    # so a fresh repo is ready to open and run with nothing else to invoke.
    adapters = install(str(c.parent))
    return {"ok": adapters["ok"], "msg": msg, "bin": adapters.get("bin")}


# trace:v1 id=impl.bugcorpus-cli.learn work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-0VGE5410
def cmd_learn(a):
    """Guided learn: capture evidence, rank families, create BugCase skeleton."""
    from .searcher import search

    if a.auto:
        return learn_auto_draft(a.title)

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
    _store_draft(bid, bug, ev, {"source": "learn", "before": a.before, "after": a.after})
    store.write_index()
    steps = [
        "state symptom vs root_cause vs violated_invariant",
        "minimize reproducer into fixtures/positive + fixtures/negative",
        f"run: bugcorpus synthesize {bid}",
        f"run: bugcorpus verify {bid}",
    ]
    return {"id": bid, "family_candidates": cands[:5], "next_steps": steps}


# trace:exempt reason=internal-detail
def _store_draft(bid: str, bug: dict, ev: dict, metadata: dict) -> None:
    import yaml as _yaml

    d = store.bug_dir(None, bid)
    (d / "evidence").mkdir(parents=True, exist_ok=True)
    (d / "evidence" / "original.diff").write_text(ev.get("original.diff", ""))
    (d / "evidence" / "fix.diff").write_text(ev.get("fix.diff", ""))
    (d / "evidence" / "metadata.json").write_text(json.dumps(metadata, indent=2))
    (d / "bug.yaml").write_text(_yaml.safe_dump(bug, sort_keys=False))
    (d / "summary.md").write_text(
        f"# {bid} {bug.get('title', '')}\n\nTODO: fill symptom/root_cause/violated_invariant.\n"
    )
    for sub in ("positive", "negative", "adversarial"):
        (d / "fixtures" / sub).mkdir(parents=True, exist_ok=True)


# trace:exempt reason=internal-detail
def _short_stat() -> str:
    import subprocess as _sp

    try:
        out = (
            _sp.run(
                ["git", "diff", "HEAD", "--stat"],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            .stdout.strip()
            .splitlines()
        )
    except (OSError, _sp.SubprocessError):
        return "worktree changes"
    if not out:
        return "worktree changes"
    return out[-1].strip()


# trace:v1 id=impl.bugcorpus-cli.learn-auto work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-0VGE5410
def learn_auto_draft(title: str = "") -> dict:
    """Non-interactive capture of the worktree diff as a proposed BugCase.

    Never invents symptom, cause, or invariant — those stay empty for an
    agent to fill. Dedups on the diff hash so repeated runs return the
    existing draft instead of cloning it.
    """
    import hashlib as _hashlib
    import subprocess as _sp

    try:
        # Exclude .bugcorpus itself: our own index writes would otherwise
        # change the diff (and its hash) on every run. Detector fixes still
        # go through interactive learn, which captures everything.
        diff = _sp.run(
            ["git", "diff", "HEAD", "--", ".", ":!.bugcorpus"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        ).stdout
    except (OSError, _sp.SubprocessError):
        diff = ""
    if not diff.strip():
        return {"ok": False, "reason": "clean worktree: nothing to capture"}
    sha = _hashlib.sha1(diff.encode()).hexdigest()[:12]
    for bid in store.list_bugs(None):
        try:
            meta = json.loads((store.bug_dir(None, bid) / "evidence" / "metadata.json").read_text())
        except (OSError, ValueError):
            continue
        if meta.get("diff_sha") == sha:
            return {"ok": True, "id": bid, "created": False, "reason": "draft already exists"}
    bid = store.next_bug_id()
    bug = {
        "id": bid,
        "title": title or "auto-captured worktree changes",
        "status": "proposed",
        "created_at": store.utcnow(),
        "language": "python",
        "severity": "medium",
        "confidence": "low",
        "symptom": "",
        "root_cause": "",
        "violated_invariant": "",
        "family_id": "",
    }
    _store_draft(
        bid,
        bug,
        {"original.diff": "", "fix.diff": diff},
        {"source": "learn-auto", "diff_sha": sha},
    )
    store.write_index()
    return {"ok": True, "id": bid, "created": True, "diff_sha": sha}


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


# trace:v1 id=impl.bugcorpus-cli.coverage work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-FESAJNS2
def cmd_coverage(a):
    from pathlib import Path as _P

    from .coverage import write_matrix

    _ = a
    matrix, out = write_matrix(_P(store.root()))
    matrix["_artifact"] = str(out)
    return matrix


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


# trace:v1 id=impl.bugcorpus-cli.promote-auto work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-FESAJNS2
def promote_auto() -> dict:
    """Advance every evaluated detector that meets blocking thresholds.

    Only shadow/warning detectors move, and only to blocking. Drafts and
    candidates still need agent synthesis; retired and blocking are untouched.
    Thresholds — not a human — are the gate.
    """
    import argparse as _ap
    from pathlib import Path as _P

    from .verifier import verify_detector

    repo = _P(store.root())
    promoted, skipped = [], {}
    for did in store.list_detectors(str(repo)):
        try:
            det, _ = store.load_detector(str(repo), did)
        except (OSError, ValueError):
            skipped[did] = "unreadable manifest"
            continue
        if det.state not in ("shadow", "warning"):
            skipped[did] = f"state {det.state}: auto only advances shadow/warning"
            continue
        try:
            v = verify_detector(repo, did)
        except (OSError, ValueError, RuntimeError):
            skipped[did] = "verification crashed"
            continue
        if v["ok"] and v.get("blocking_eligible"):
            r = cmd_promote(_ap.Namespace(id=did, to="blocking", auto=False))
            if r.get("ok"):
                promoted.append(did)
            else:
                skipped[did] = r.get("error", "promotion refused")
        else:
            skipped[did] = "thresholds unmet"
    return {"ok": True, "promoted": promoted, "skipped": skipped}


# trace:v1 id=impl.bugcorpus-cli.promote work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-FESAJNS2
def cmd_promote(a):
    import yaml as _yaml

    if getattr(a, "auto", False):
        return promote_auto()
    if not a.id or not a.to:
        return {"ok": False, "error": "usage: promote ID --to STATE or promote --auto"}
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
    import re as _re

    # surgical state change: a full YAML re-dump would strip comments and
    # restyle the manifest, so only the state line is touched.
    text = mp.read_text()
    new_text, n = _re.subn(
        r"^state:\s*\S+.*$", f"state: {a.to}", text, count=1, flags=_re.MULTILINE
    )
    mp.write_text(new_text if n else text.rstrip("\n") + f"\nstate: {a.to}\n")
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


# trace:v1 id=impl.bugcorpus-cli.baseline work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-WSZJ7M37
def cmd_baseline(a):
    """List current findings, or record them as the tracked-debt baseline."""
    import json as _json

    from .scanner import run_scan

    res = run_scan(profile="full")
    fps = sorted({f["fingerprint"] for f in res["findings"]})
    if not a.record:
        return {"findings": len(fps), "fingerprints": fps}
    p = store.cdir() / "baseline.json"
    p.write_text(_json.dumps({"fingerprints": fps}, indent=2) + "\n")
    return {"ok": True, "recorded": len(fps), "path": str(p)}


# trace:exempt reason=thin-cli-dispatch
def cmd_doctor(a):
    _ = a
    from .doctor import doctor

    return doctor()


# trace:exempt reason=thin-cli-dispatch
def cmd_adapters(a):
    from .adapters import check, install

    if a.check:
        return check(store.root(), harnesses=a.only, bin=a.bin)
    return install(store.root(), harnesses=a.only, bin=a.bin)


# trace:v1 id=impl.bugcorpus-cli.update work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-MKCEMW39
def cmd_update(a):
    """Refresh a repo to the running distribution: adapters + indexes."""
    from . import __version__
    from .adapters import install

    _ = a
    root = store.root()
    report = install(root)
    idx = store.write_index(str(root))
    return {
        "ok": report["ok"],
        "version": __version__,
        "bin": report.get("bin"),
        "adapters": {k: v for k, v in report.items() if k in ("skills", "files", "pointers")},
        "notes": report.get("notes", []),
        "bug_count": len(idx.get("bugs", [])),
        "detector_count": len(store.list_detectors(str(root))),
    }


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

    # Returns None so main() prints nothing: stdout is JSON-RPC only.
    serve()


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


# trace:exempt reason=internal-detail
def stop_signals(transcript: str) -> tuple[int, bool]:
    """Count bug-fix signals vs learned markers in a JSONL transcript tail."""
    import re as _re

    fix = _re.compile(r"\b(fix|fixed|fixing|bug|regression|root cause|reproducer)\b")
    learned = _re.compile(r"bugcorpus learn|/bug-learn|BC-\d|bug-corpus skill")
    hits, done = 0, False
    for ln in transcript.splitlines()[-200:]:
        low = ln.lower()
        if learned.search(low):
            done = True
        hits += len(set(fix.findall(low)))
    return min(hits, 9), done


# trace:v1 id=impl.bugcorpus-cli.session-stop work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-MKCEMW39
def cmd_hooks_stop() -> None:
    """Advisory stop reminder when a session fixed a bug without learning it."""
    import json as _json

    try:
        raw = sys.stdin.read()
        event = _json.loads(raw) if raw.strip() else {}
        tpath = event.get("transcript_path") or event.get("transcript") or ""
        if not tpath:
            return  # no session evidence available; stay silent, never guess
        try:
            with open(tpath, encoding="utf-8", errors="replace") as f:
                text = f.read()[-500_000:]
        except OSError:
            return
        hits, learned = stop_signals(text)
        if hits >= 2 and not learned:
            draft = learn_auto_draft()
            if draft.get("created"):
                print(
                    f"Bug Corpus: captured this session's diff as proposed {draft['id']} "
                    f"({_short_stat()}). It has no invariant yet — run /bug-learn "
                    f"on {draft['id']} to refine it into a detector, or leave it proposed."
                )
            elif draft.get("id"):
                print(
                    f"Bug Corpus: this session looks like it fixed a bug; {draft['id']} "
                    f"already proposes these changes. Refine it with /bug-learn."
                )
            else:
                print(
                    "Bug Corpus: this session looks like it fixed a bug. If it is a "
                    "genuine defect with a violated invariant (not a typo/format), "
                    "run /bug-learn before finishing so the bug class gains a detector."
                )
    except (OSError, ValueError):
        pass
    return


# trace:v1 id=impl.bugcorpus-cli.session-start work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-MKCEMW39
def cmd_hooks_start() -> None:
    """Announce verified load state: counts plus per-detector load checks."""
    from pathlib import Path as _P

    from . import __version__
    from .engines import ENGINES

    try:
        root = _P(store.root())
        if not (root / ".bugcorpus").is_dir():
            return  # not enrolled: silent
        cwd = str(root)
        bugs = store.list_bugs(cwd)
        fams = store.list_families(cwd)
        ok, broken, blocking = [], [], 0
        for did in store.list_detectors(cwd):
            try:
                det, _ = store.load_detector(cwd, did)
            except Exception:  # noqa: BLE001 -- hook reports load state, never crashes on it
                broken.append(did)
                continue
            eng = ENGINES.get(det.engine)
            available = eng.available()[0] if eng else False
            if det.state == "blocking":
                blocking += 1
            flag = "" if available else " (engine unavailable here)"
            ok.append(f"{did} [{det.engine}{flag}]")
        print(
            f"Bug Corpus {__version__} loaded: {len(bugs)} bugs, "
            f"{len(ok)} detectors ({blocking} blocking), {len(fams)} families."
        )
        if ok:
            print("Detectors verified loadable: " + ", ".join(sorted(ok)) + ".")
        for did in sorted(broken):
            print(f"WARNING: detector {did} failed to load; run `bugcorpus verify`.")
        print("Run /bug-learn after fixing a bug; /bug-scan to scan.")
    except (OSError, ValueError):
        pass  # hooks are advisory; never block session start
    return


# trace:v1 id=impl.bugcorpus-cli.hooks work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-8HPVNRVG
def cmd_hooks(a):
    """Cheap post-edit hook: fast-profile scan of the touched file. Always exits 0."""
    if a.hcmd == "session-stop":
        return cmd_hooks_stop()
    if a.hcmd == "session-start":
        return cmd_hooks_start()
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
    s.add_argument(
        "--auto",
        action="store_true",
        help="non-interactive: capture the worktree diff as a proposed draft",
    )
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
    s = sub.add_parser("promote")
    s.add_argument("id", nargs="?")
    s.add_argument(
        "--to",
        required=False,
        choices=["draft", "candidate", "shadow", "warning", "blocking", "retired"],
    )
    s.add_argument(
        "--auto",
        action="store_true",
        help="promote every eligible shadow/warning detector to blocking",
    )
    s.set_defaults(fn=cmd_promote)
    s = sub.add_parser("synthesize")
    s.add_argument("id", nargs="?")
    s.add_argument("--family", default="")
    s.add_argument("--engine", default=None)
    s.set_defaults(fn=cmd_synthesize)

    s = sub.add_parser("verify")
    s.add_argument("id", nargs="?")
    s.add_argument("--detector", default=None)
    s.set_defaults(fn=cmd_verify)

    s = sub.add_parser("coverage")
    s.set_defaults(fn=cmd_coverage)

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

    s = sub.add_parser("baseline")
    s.add_argument("--record", action="store_true", help="record current findings as tracked debt")
    s.set_defaults(fn=cmd_baseline)

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
    a.add_argument(
        "--bin",
        default=None,
        help="invocation written into hooks/MCP/pointers (default: bugcorpus if on PATH else 'uv run bugcorpus')",
    )
    a.set_defaults(fn=cmd_adapters)

    s = sub.add_parser("update")
    s.set_defaults(fn=cmd_update)

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
    h = hs.add_parser("session-stop")
    h.set_defaults(fn=cmd_hooks)
    h = hs.add_parser("session-start")
    h.set_defaults(fn=cmd_hooks)
    return p


# trace:exempt reason=internal-detail
LANG_GLOBS = {
    ".py": "**/*.py",
    ".ts": "**/*.ts",
    ".tsx": "**/*.tsx",
    ".js": "**/*.js",
    ".jsx": "**/*.jsx",
    ".mjs": "**/*.mjs",
    ".cjs": "**/*.cjs",
    ".go": "**/*.go",
    ".rs": "**/*.rs",
    ".java": "**/*.java",
}
SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "node_modules",
        "__pycache__",
        ".tox",
        "dist",
        "build",
        "target",
        "vendor",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
    }
)


# trace:v1 id=impl.bugcorpus-cli.scan-includes work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-0VGE5410
def detect_scan_includes(root: Path, cap: int = 8) -> list[str]:
    """Census source extensions (pruned walk) into scan include patterns."""
    import os as _os

    counts: dict[str, int] = {}
    seen = 0
    for _dirpath, dirnames, filenames in _os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            ext = Path(fn).suffix.lower()
            if ext in LANG_GLOBS:
                counts[ext] = counts.get(ext, 0) + 1
        seen += len(filenames)
        if seen > 50000:
            break
    exts = sorted(counts, key=lambda e: -counts[e])[:cap] or [".py"]
    includes = [LANG_GLOBS[e] for e in exts]
    includes.append(".bugcorpus/detectors/**/*.py")
    includes.extend(f".bugcorpus/corpus/**/fixtures/**/*{e}" for e in exts)
    return includes


# trace:exempt reason=internal-detail
def render_config(includes: list[str]) -> str:
    inc = ", ".join(f'"{p}"' for p in includes)
    return f"""# Bug Corpus configuration
[corpus]
root = ".bugcorpus"

[scan]
include = [{inc}]
exclude = [".venv/**", ".git/**", ".bugcorpus/cache/**", "node_modules/**"]
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
