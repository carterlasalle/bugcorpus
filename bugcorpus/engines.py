"""Detector engine adapters. One abstraction, subprocess-based, no sprinkling."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class EngineResult:
    findings: list[dict]
    status: str  # clean | findings | detector-error | unavailable
    detail: str = ""


class Engine:
    name = "base"

    # trace:exempt reason=internal-detail
    def available(self) -> tuple[bool, str]:
        return True, "builtin"

    # trace:v1 id=impl.bugcorpus-engines.protocol work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-8HPVNRVG
    def scan(
        self, repo: Path, manifest: dict, ddir: Path, files: list[str], timeout: int
    ) -> EngineResult:
        raise NotImplementedError


# trace:exempt reason=internal-detail
def _run(cmd: list[str], timeout: int, cwd: Path | None = None) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False, cwd=cwd
        )
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except OSError as e:
        return 127, "", str(e)


class ExistingEngine(Engine):
    """Level 0: defer to an already-configured analyzer; verify it stays enabled."""

    name = "existing"

    # trace:v1 id=impl.bugcorpus-engines.existing work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-8HPVNRVG
    def scan(self, repo, manifest, ddir, files, timeout):
        cfg = manifest.get("existing", {})
        tool, args = cfg.get("tool", ""), cfg.get("args", [])
        pattern = cfg.get("match_pattern", "")
        if not tool or not shutil.which(tool):
            return EngineResult([], "unavailable", f"tool {tool!r} not installed")
        # analyzers discover files themselves; never build an ARG_MAX-breaking command
        targets = files if 0 < len(files) <= 50 else ["."]
        rc, out, err = _run([tool, *args, *targets], timeout, cwd=repo)
        text = out + err
        findings = []
        if pattern and re.search(pattern, text):
            findings.append(
                {
                    "path": files[0] if len(files) == 1 else (targets[0] if targets else "."),
                    "start_line": 1,
                    "end_line": 1,
                    "message": f"existing analyzer {tool} reports {manifest['id']}",
                    "explanation": f"Rule from {tool} matched expected pattern.",
                    "evidence": pattern,
                    "remediation": manifest.get("description", ""),
                }
            )
        # existing engine: nonzero exit often means findings; trust pattern only
        _ = rc
        return EngineResult(findings, "findings" if findings else "clean", text[-2000:])


# trace:exempt reason=internal-detail
def absolute(repo: Path, files: list[str]) -> list[str]:
    return [f if Path(f).is_absolute() else str(repo / f) for f in files] or [str(repo)]


# trace:exempt reason=internal-detail
def _code_lines(suffix: str, text: str):
    """Yield (lineno, line) with comments/strings blanked for Python files.

    A lexical rule must never fire on ``eval(`` inside a comment or string.
    Masking preserves columns so findings still point at the real location.
    """
    lines = text.splitlines()
    if suffix != ".py":
        yield from enumerate(lines, 1)
        return
    import io as _io
    import tokenize as _tok

    masked = [list(ln) for ln in lines]

    def blank(tok):
        (srow, scol), (erow, ecol) = tok.start, tok.end
        for r in range(srow - 1, erow):
            if 0 <= r < len(masked):
                lo = scol if r == srow - 1 else 0
                hi = ecol if r == erow - 1 else len(masked[r])
                for c in range(lo, min(hi, len(masked[r]))):
                    masked[r][c] = " "

    try:
        for tok in _tok.generate_tokens(_io.StringIO(text).readline):
            if tok.type in (_tok.COMMENT, _tok.STRING):
                blank(tok)
    except (SyntaxError, _tok.TokenError, IndentationError):
        yield from enumerate(lines, 1)
        return
    for i, chars in enumerate(masked, 1):
        yield i, "".join(chars)


class LexicalEngine(Engine):
    """Level 1: stable textual structure only (forbidden APIs etc.)."""

    name = "lexical"

    # trace:v1 id=impl.bugcorpus-engines.lexical work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-8HPVNRVG
    def scan(self, repo, manifest, ddir, files, timeout):
        import re as _re

        pats = manifest.get("patterns", [])
        compiled = [(_re.compile(p["regex"]), p.get("message", p["regex"])) for p in pats]
        findings = []
        for f in files:
            p = repo / f if not Path(f).is_absolute() else Path(f)
            if not p.is_file():
                continue
            try:
                text = p.read_text(errors="replace")
            except OSError:
                continue
            for i, line in _code_lines(p.suffix, text):
                for rx, msg in compiled:
                    if rx.search(line):
                        findings.append(
                            {
                                "path": str(p),
                                "start_line": i,
                                "end_line": i,
                                "message": msg,
                                "explanation": manifest.get("description", ""),
                                "evidence": line.strip()[:300],
                                "remediation": manifest.get("remediation", ""),
                            }
                        )
        return EngineResult(findings, "findings" if findings else "clean")


class AstGrepEngine(Engine):
    """Level 2: ast-grep rules."""

    name = "ast-grep"

    # trace:exempt reason=internal-detail
    def available(self):
        return (True, "ok") if shutil.which("ast-grep") else (False, "ast-grep not installed")

    # trace:v1 id=impl.bugcorpus-engines.ast-grep work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-8HPVNRVG
    def scan(self, repo, manifest, ddir, files, timeout):
        ok, why = self.available()
        if not ok:
            return EngineResult([], "unavailable", why)
        rule = manifest.get("rule_file", "rule.yaml")
        rp = ddir / rule
        if not rp.exists():
            return EngineResult([], "detector-error", f"missing rule {rule}")
        cmd = ["ast-grep", "scan", "--rule", str(rp), "--json"]
        if files:
            cmd += files
        rc, out, err = _run(cmd, timeout, cwd=repo)
        if rc not in (0, 1):
            return EngineResult([], "detector-error", (err or out)[-2000:])
        findings = []
        try:
            data = json.loads(out or "[]")
            items = data if isinstance(data, list) else data.get("matches", data.get("results", []))
            for m in items if isinstance(items, list) else []:
                rng = m.get("range", {})
                findings.append(
                    {
                        "path": m.get("path") or m.get("file", ""),
                        "start_line": rng.get("start", {}).get("line", 1),
                        "end_line": rng.get("end", {}).get("line", 1),
                        "message": m.get("message", manifest["id"]),
                        "explanation": manifest.get("description", ""),
                        "evidence": (m.get("text") or "")[:300],
                    }
                )
        except (ValueError, AttributeError) as e:
            return EngineResult([], "detector-error", f"parse failure: {e}")
        return EngineResult(findings, "findings" if findings else "clean")


class SemgrepEngine(Engine):
    """Levels 3-4: structural + taint rules."""

    name = "semgrep"

    # trace:exempt reason=internal-detail
    def available(self):
        return (True, "ok") if shutil.which("semgrep") else (False, "semgrep not installed")

    # trace:v1 id=impl.bugcorpus-engines.semgrep work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-8HPVNRVG
    def scan(self, repo, manifest, ddir, files, timeout):
        ok, why = self.available()
        if not ok:
            return EngineResult([], "unavailable", why)
        cfg = manifest.get("config", "rule.yaml")
        cp = ddir / cfg
        if not cp.exists():
            return EngineResult([], "detector-error", f"missing config {cfg}")
        cmd = ["semgrep", "--config", str(cp), "--json", "--quiet"]
        cmd += files or [str(repo)]
        rc, out, err = _run(cmd, timeout, cwd=repo)
        if rc not in (0, 1, 2, 7):
            return EngineResult([], "detector-error", (err or out)[-2000:])
        try:
            data = json.loads(out or "{}")
        except ValueError as e:
            return EngineResult([], "detector-error", f"parse failure: {e}")
        findings = []
        for r in data.get("results", []):
            findings.append(
                {
                    "path": r.get("path", ""),
                    "start_line": r.get("start", {}).get("line", 1),
                    "end_line": r.get("end", {}).get("line", 1),
                    "message": r.get("extra", {}).get("message", manifest["id"]),
                    "explanation": manifest.get("description", ""),
                    "evidence": (r.get("extra", {}).get("lines") or "")[:300],
                }
            )
        errs = data.get("errors", [])
        status = "findings" if findings else ("detector-error" if errs else "clean")
        return EngineResult(findings, status, "; ".join(e.get("message", "") for e in errs)[:500])


class CodeQLEngine(Engine):
    """Level 5: checked-in CodeQL queries; runs only if codeql present."""

    name = "codeql"

    # trace:exempt reason=internal-detail
    def available(self):
        return (True, "ok") if shutil.which("codeql") else (False, "codeql not installed")

    # trace:v1 id=impl.bugcorpus-engines.codeql work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-8HPVNRVG
    def scan(self, repo, manifest, ddir, files, timeout):
        ok, why = self.available()
        if not ok:
            return EngineResult([], "unavailable", why)
        # Full CodeQL DB flow is repo-specific; manifest must give explicit run command.
        cmd = manifest.get("run", [])
        if not cmd:
            return EngineResult([], "detector-error", "codeql detector needs manifest.run command")
        rc, out, err = _run(cmd, timeout, cwd=repo)
        if rc != 0:
            return EngineResult([], "detector-error", (err or out)[-2000:])
        try:
            items = json.loads(out or "[]")
        except ValueError as e:
            return EngineResult([], "detector-error", f"parse failure: {e}")
        return EngineResult(
            items if isinstance(items, list) else [], "findings" if items else "clean"
        )


class PysaEngine(Engine):
    """Level 6: Pysa models; runs only if pyre present."""

    name = "pysa"

    # trace:exempt reason=internal-detail
    def available(self):
        return (True, "ok") if shutil.which("pyre") else (False, "pyre not installed")

    # trace:v1 id=impl.bugcorpus-engines.pysa work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-8HPVNRVG
    def scan(self, repo, manifest, ddir, files, timeout):
        ok, why = self.available()
        if not ok:
            return EngineResult([], "unavailable", why)
        cmd = manifest.get("run", ["pyre", "--output", "json", "check"])
        rc, out, err = _run(cmd, timeout, cwd=repo)
        if rc not in (0, 1):
            return EngineResult([], "detector-error", (err or out)[-2000:])
        try:
            data = json.loads(out or "[]")
            items = data if isinstance(data, list) else data.get("errors", [])
        except ValueError as e:
            return EngineResult([], "detector-error", f"parse failure: {e}")
        findings = [
            {
                "path": e.get("path", ""),
                "start_line": e.get("line", 1),
                "end_line": e.get("line", 1),
                "message": e.get("description", manifest["id"]),
                "explanation": manifest.get("description", ""),
                "evidence": e.get("name", ""),
            }
            for e in items
            if manifest["id"] in json.dumps(e)
        ]
        return EngineResult(findings, "findings" if findings else "clean")


class CustomEngine(Engine):
    """Levels 7-8: purpose-built searcher over the stable subprocess contract.

    Contract: `python entrypoint --format json <files...>` prints a JSON list
    of {path,start_line,end_line,message,explanation,evidence,remediation}.
    """

    name = "custom"

    # trace:v1 id=impl.bugcorpus-engines.custom work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-8HPVNRVG
    def scan(self, repo, manifest, ddir, files, timeout):
        ep = manifest.get("entrypoint", "")
        if not ep:
            return EngineResult([], "detector-error", "missing entrypoint")
        prog = ddir / ep
        if not prog.exists():
            return EngineResult([], "detector-error", f"missing {ep}")
        import sys

        cmd = [sys.executable, str(prog), "--format", "json", *absolute(repo, files)]
        rc, out, err = _run(cmd, timeout, cwd=repo)
        if rc != 0:
            return EngineResult([], "detector-error", (err or out)[-2000:])
        try:
            items = json.loads(out or "[]")
        except ValueError as e:
            return EngineResult([], "detector-error", f"parse failure: {e}")
        if not isinstance(items, list):
            return EngineResult([], "detector-error", "custom detector must print a JSON list")
        return EngineResult(items, "findings" if items else "clean")


ENGINES: dict[str, Engine] = {
    "existing": ExistingEngine(),
    "lexical": LexicalEngine(),
    "ast-grep": AstGrepEngine(),
    "semgrep": SemgrepEngine(),
    "semgrep-taint": SemgrepEngine(),
    "codeql": CodeQLEngine(),
    "pysa": PysaEngine(),
    "custom": CustomEngine(),
}


# trace:exempt reason=internal-detail
def load_manifest(ddir: Path) -> dict:
    return yaml.safe_load((ddir / "detector.yaml").read_text()) or {}
