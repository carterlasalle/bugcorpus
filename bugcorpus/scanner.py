"""Deterministic scanner runtime: profiles, scopes, baseline, suppressions."""

from __future__ import annotations

import fnmatch
import subprocess
import tomllib
from pathlib import Path

from . import store
from .engines import ENGINES, load_manifest
from .fingerprint import fingerprint
from .models import Finding

PROFILES = ("fast", "pr", "full")
PROFILE_ENGINES = {
    "fast": {"lexical", "ast-grep", "custom", "existing"},
    "pr": {"lexical", "ast-grep", "custom", "existing", "semgrep", "semgrep-taint"},
    "full": {
        "lexical",
        "ast-grep",
        "custom",
        "existing",
        "semgrep",
        "semgrep-taint",
        "codeql",
        "pysa",
    },
}
PROFILE_COST = {
    "fast": {"cheap"},
    "pr": {"cheap", "medium"},
    "full": {"cheap", "medium", "expensive"},
}


# trace:exempt reason=internal-detail
def config(cwd=None) -> dict:
    p = store.cdir(cwd) / "config.toml"
    if p.exists():
        with open(p, "rb") as f:
            return tomllib.load(f)
    return {}


# trace:exempt reason=internal-detail
def collect_files(repo: Path, cfg: dict) -> list[str]:
    inc = cfg.get("scan", {}).get("include", ["**/*.py"])
    exc = set(cfg.get("scan", {}).get("exclude", [".venv/**", ".git/**", ".bugcorpus/cache/**"]))
    files = []
    for pat in inc:
        for p in repo.glob(pat):
            if p.is_file():
                rel = str(p.relative_to(repo))
                if not any(fnmatch.fnmatch(rel, e) or rel.startswith(e.rstrip("*")) for e in exc):
                    files.append(rel)
    return sorted(set(files))


# trace:exempt reason=internal-detail
def changed_files(repo: Path, diff: str | None) -> tuple[list[str], dict[str, set[int]]]:
    """Return (files, changed_lines). None diff -> git status based changed set."""
    if diff and "..." in diff:
        base, head = diff.split("...", 1)
        rng = f"{base}...{head or 'HEAD'}"
    elif diff:
        rng = diff
    else:
        rng = None
    try:
        if rng:
            out = subprocess.run(
                ["git", "diff", "--numstat", "--unified=0", rng],
                capture_output=True,
                text=True,
                cwd=repo,
                check=False,
                timeout=30,
            ).stdout
            # need file list + lines; simpler: numstat for files, diff -U0 parse for lines
            detail = subprocess.run(
                ["git", "diff", "-U0", rng],
                capture_output=True,
                text=True,
                cwd=repo,
                check=False,
                timeout=30,
            ).stdout
        else:
            detail = subprocess.run(
                ["git", "diff", "-U0"],
                capture_output=True,
                text=True,
                cwd=repo,
                check=False,
                timeout=30,
            ).stdout
            out = ""
        _ = out
        files: dict[str, bool] = {}
        lines: dict[str, set[int]] = {}
        cur = ""
        import re

        for ln in detail.splitlines():
            if ln.startswith("+++ b/"):
                cur = ln[6:]
                files[cur] = True
            else:
                m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", ln)
                if m and cur:
                    start, count = int(m.group(1)), int(m.group(2) or 1)
                    lines.setdefault(cur, set()).update(range(start, start + count))
        return sorted(files), lines
    except (OSError, subprocess.SubprocessError):
        return [], {}


# trace:v1 id=impl.bugcorpus-scanner.enrich work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-8HPVNRVG
def enrich(repo: Path, manifest: dict, raw: dict) -> Finding:
    path = raw.get("path", "")
    try:
        rel = str(Path(path).relative_to(repo))
    except ValueError:
        rel = path
    enc = raw.get("enclosing", "")
    if not enc and rel:
        try:
            import ast as _ast

            tree = _ast.parse((repo / rel).read_text(errors="replace"))
            for node in _ast.walk(tree):
                if not isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
                    continue
                if node.lineno <= int(raw.get("start_line", 1)) <= (node.end_lineno or node.lineno):
                    enc = node.name
        except (OSError, SyntaxError, ValueError):
            enc = ""
    fp = raw.get("fingerprint") or fingerprint(
        manifest["id"], rel, enc, raw.get("evidence", "") or raw.get("message", "")
    )
    return Finding(
        detector_id=manifest["id"],
        path=rel,
        start_line=int(raw.get("start_line", 1)),
        start_column=int(raw.get("start_column", 1)),
        end_line=int(raw.get("end_line", raw.get("start_line", 1))),
        end_column=int(raw.get("end_column", 1)),
        severity=raw.get("severity", manifest.get("severity", "medium")),
        confidence=raw.get("confidence", manifest.get("confidence", "medium")),
        message=raw.get("message", ""),
        explanation=raw.get("explanation", ""),
        evidence=raw.get("evidence", ""),
        fingerprint=fp,
        remediation=raw.get("remediation", manifest.get("remediation", "")),
        bug_family=manifest.get("family", ""),
        bug_cases=list(manifest.get("catches", [])),
    )


# trace:exempt reason=internal-detail
def suppressed(f: Finding, rules: list[dict]) -> bool:
    for r in rules:
        if r.get("detector") not in (None, f.detector_id):
            continue
        if r.get("fingerprint") and r["fingerprint"] != f.fingerprint:
            continue
        if r.get("path") and r["path"] != f.path:
            continue
        return True
    return False


# trace:v1 id=impl.bugcorpus-scanner.run work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-8HPVNRVG
def run_scan(
    repo_root: str | None = None,
    profile: str = "pr",
    scope: str = "all",
    diff: str | None = None,
    detectors: list[str] | None = None,
    include_unavailable: bool = True,
    files: list[str] | None = None,  # explicit targets (hooks); overrides scope
) -> dict:
    repo = Path(repo_root or store.root()).resolve()
    cfg = config(str(repo))
    timeout = int(cfg.get("scan", {}).get("timeout_seconds", 120))
    all_files = collect_files(repo, cfg)
    if files is not None:
        file_list = files
    elif scope == "changed" or diff:
        changed, _ = changed_files(repo, diff)
        file_list = changed or all_files
    else:
        file_list = all_files
    # drop fixture/suppression noise? No: scan everything configured.
    results: list[dict] = []
    counts = {"clean": 0, "findings": 0, "detector-error": 0, "unavailable": 0}
    for did in detectors or store.list_detectors(str(repo)):
        try:
            manifest = load_manifest(store.detector_dir(str(repo), did))
        except OSError:
            continue
        if profile in PROFILE_ENGINES:
            if manifest.get("engine") not in PROFILE_ENGINES[profile]:
                continue
            if manifest.get("cost", "cheap") not in PROFILE_COST[profile]:
                continue
        if manifest.get("state") == "retired":
            continue
        engine = ENGINES.get(manifest.get("engine", "custom"))
        if engine is None:
            results.append(
                {
                    "detector": did,
                    "status": "detector-error",
                    "detail": "unknown engine",
                    "findings": [],
                }
            )
            counts["detector-error"] += 1
            continue
        # requires_full_scan detectors ignore changed scoping
        target = all_files if manifest.get("requires_full_scan") else file_list
        try:
            res = engine.scan(repo, manifest, store.detector_dir(str(repo), did), target, timeout)
        except Exception as e:  # noqa: BLE001 -- crash isolation: a detector error must fail loudly, never read as clean
            from .engines import EngineResult as _ER

            res = _ER([], "detector-error", f"crash: {e}")
        findings = [enrich(repo, manifest, r).to_dict() for r in res.findings]
        if res.status == "unavailable" and not include_unavailable:
            continue
        counts[res.status] = counts.get(res.status, 0) + 1
        results.append(
            {"detector": did, "status": res.status, "detail": res.detail, "findings": findings}
        )
    # suppressions
    rules = store.load_suppressions(str(repo))
    for r in results:
        kept = [f for f in r["findings"] if not suppressed_dict(f, rules)]
        r["suppressed"] = len(r["findings"]) - len(kept)
        r["findings"] = kept
    # baseline: only-new semantics for CI (fixture verification never uses baseline)
    baseline = load_baseline(repo)
    new_findings = [f for r in results for f in r["findings"] if f["fingerprint"] not in baseline]
    return {
        "repo": str(repo),
        "profile": profile,
        "scope": scope,
        "counts": counts,
        "detectors": results,
        "findings": [f for r in results for f in r["findings"]],
        "new_findings": new_findings,
        "baseline_size": len(baseline),
    }


# trace:exempt reason=internal-detail
def suppressed_dict(f: dict, rules: list[dict]) -> bool:
    for r in rules:
        if r.get("detector") not in (None, f.get("detector_id")):
            continue
        if r.get("fingerprint") and r["fingerprint"] != f.get("fingerprint"):
            continue
        if r.get("path") and r["path"] != f.get("path"):
            continue
        return True
    return False


# trace:exempt reason=internal-detail
def load_baseline(repo: Path) -> set[str]:
    p = repo / ".bugcorpus" / "baseline.json"
    if not p.exists():
        return set()
    try:
        import json as _j

        data = _j.loads(p.read_text())
        return set(data.get("fingerprints", []))
    except (OSError, ValueError):
        return set()


# trace:v1 id=impl.bugcorpus-scanner.ci-gate work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-WSZJ7M37
def blocking_failed(scan: dict) -> bool:
    """CI gate: any blocking-state detector with new findings or errors fails."""
    for d in scan["detectors"]:
        try:
            m = load_manifest(store.detector_dir(scan["repo"], d["detector"]))
        except OSError:
            continue
        if m.get("state") != "blocking":
            continue
        if d["status"] == "detector-error":
            return True
        if any(
            f["fingerprint"] in {n["fingerprint"] for n in scan["new_findings"]}
            for f in d["findings"]
        ):
            return True
    # a blocking detector that errored anywhere is a failure (no silent pass)
    return any(
        d["status"] == "detector-error" and _is_blocking(scan["repo"], d["detector"])
        for d in scan["detectors"]
    )


# trace:exempt reason=internal-detail
def _is_blocking(repo: str, did: str) -> bool:
    try:
        return load_manifest(store.detector_dir(repo, did)).get("state") == "blocking"
    except OSError:
        return False
