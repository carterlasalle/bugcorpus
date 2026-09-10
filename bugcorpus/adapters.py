"""Cross-harness adapter installation from canonical sources.

Canonical skill: skills/bug-corpus/SKILL.md (agentskills.io frontmatter).
Per-harness sources: adapters/<harness>/ (commands, hooks, extension, config).
Install copies verbatim files and merges structured configs without clobbering
user content. `check` verifies installed state (CI-usable). Research basis:
Claude (code.claude.com/docs, Agent Skills spec), Codex (learn.chatgpt.com
docs), OMP (github.com/can1357/oh-my-pi docs + in-tree tracelayer gate).
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

CANON = Path("skills/bug-corpus/SKILL.md")
POINTER = """This repository uses Bug Corpus.
For confirmed defects or requests to search for similar bugs,
use the repository's bug-corpus skill and `uv run bugcorpus`.
See skills/bug-corpus/SKILL.md.
"""
MANAGED_BEGIN = "<!-- managed-bugcorpus:start -->"
MANAGED_END = "<!-- managed-bugcorpus:end -->"

HOOK_COMMAND = "uv run bugcorpus hooks post-tool-use"
CLAUDE_HOOK_ENTRY = {
    "matcher": "Edit|Write",
    "hooks": [{"type": "command", "command": HOOK_COMMAND}],
}
CLAUDE_STOP_ENTRY = {
    "matcher": "",
    "hooks": [{"type": "command", "command": "uv run bugcorpus hooks session-stop"}],
}
MCP_SERVER_ENTRY = {"command": "uv", "args": ["run", "bugcorpus", "mcp"]}
TRUST_NOTES = {
    "claude": ".mcp.json needs one-time approval in Claude Code; hooks run on trust of the checkout.",
    "codex": ".codex/hooks.json and .codex/config.toml are trusted-project surfaces; approve per https://learn.chatgpt.com/docs/hooks.",
    "omp": ".omp/extensions are auto-discovered; restart the session after install.",
}


def _managed_block() -> str:
    return f"{MANAGED_BEGIN}\n{POINTER.strip()}\n{MANAGED_END}\n"


# trace:exempt reason=internal-detail
def upsert_managed(path: Path) -> str:
    block = _managed_block()
    if path.exists():
        text = path.read_text()
        if MANAGED_BEGIN in text and MANAGED_END in text:
            pre = text.split(MANAGED_BEGIN)[0]
            post = text.split(MANAGED_END)[1]
            path.write_text(pre + block + post.lstrip("\n"))
            return "updated"
        path.write_text(text.rstrip("\n") + "\n\n" + block)
        return "appended"
    path.write_text(block)
    return "created"


# trace:exempt reason=internal-detail
def _copy_verbatim(src: Path, dest: Path, log: list[str]) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = src.read_bytes()
    if not dest.exists() or dest.read_bytes() != data:
        dest.write_bytes(data)
        log.append(f"{dest} (installed)")
    else:
        log.append(f"{dest} (unchanged)")


# trace:exempt reason=internal-detail
def _copy_tree(src: Path, dest: Path, log: list[str]) -> None:
    for f in sorted(src.rglob("*")):
        if f.is_file():
            _copy_verbatim(f, dest / f.relative_to(src), log)


# trace:exempt reason=internal-detail
def _merge_json_object(path: Path, keys: list[str], value: dict) -> str:
    """Set nested keys in a JSON object file, preserving everything else."""
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except ValueError:
            return f"{path}: left alone (unparseable JSON)"
    else:
        data = {}
    node = data
    for k in keys[:-1]:
        if not isinstance(node.get(k), dict):
            node[k] = {}
        node = node[k]
    if node.get(keys[-1]) == value:
        return f"{path}: unchanged"
    node[keys[-1]] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    return f"{path}: merged"


# trace:v1 id=impl.bugcorpus-adapters.install work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-MKCEMW39
def install(repo: str | Path, harnesses: list[str] | None = None) -> dict:
    repo = Path(repo)
    if not (repo / CANON).exists():
        return {"ok": False, "error": "canonical skill missing: skills/bug-corpus/SKILL.md"}
    src = repo / "adapters"
    targets = {"claude", "codex", "omp"} if not harnesses else set(harnesses)
    report: dict = {"ok": True, "skills": [], "files": [], "pointers": [], "notes": []}

    def rel(p: Path) -> str:
        return str(p.relative_to(repo))

    if "claude" in targets:
        _copy_tree(
            repo / CANON.parent, repo / ".claude" / "skills" / "bug-corpus", report["skills"]
        )
        for cmd in sorted((src / "claude" / "commands").glob("*.md")):
            _copy_verbatim(cmd, repo / ".claude" / "commands" / cmd.name, report["files"])
        cur = _read_hooks(repo / ".claude" / "settings.json")
        merged = False
        if not _has_hook_command(cur, "PostToolUse", HOOK_COMMAND):
            cur.setdefault("hooks", {}).setdefault("PostToolUse", []).append(CLAUDE_HOOK_ENTRY)
            merged = True
        if not _has_hook_command(cur, "Stop", "uv run bugcorpus hooks session-stop"):
            cur.setdefault("hooks", {}).setdefault("Stop", []).append(CLAUDE_STOP_ENTRY)
            merged = True
        if merged:
            _write_json(repo / ".claude" / "settings.json", cur)
            report["files"].append(f"{rel(repo / '.claude' / 'settings.json')} (hook merged)")
        else:
            report["files"].append(f"{rel(repo / '.claude' / 'settings.json')} (unchanged)")
        report["files"].append(
            _merge_json_object(repo / ".mcp.json", ["mcpServers", "bugcorpus"], MCP_SERVER_ENTRY)
        )
        report["pointers"].append(f"CLAUDE.md: {upsert_managed(repo / 'CLAUDE.md')}")
        report["notes"].append("claude: " + TRUST_NOTES["claude"])
    if "codex" in targets:
        _copy_tree(
            repo / CANON.parent, repo / ".agents" / "skills" / "bug-corpus", report["skills"]
        )
        _copy_verbatim(
            src / "codex" / "hooks.json", repo / ".codex" / "hooks.json", report["files"]
        )
        report["files"].append(_merge_codex_config(repo / ".codex" / "config.toml"))
        report["pointers"].append(f"CODEX.md: {upsert_managed(repo / 'CODEX.md')}")
        report["notes"].append("codex: " + TRUST_NOTES["codex"])
    if "omp" in targets:
        _copy_tree(repo / CANON.parent, repo / ".omp" / "skills" / "bug-corpus", report["skills"])
        ext = repo / ".omp" / "extensions" / "bug-corpus"
        stale = ext / "plugin.json"
        if stale.exists() and '"entry": "uv run bugcorpus"' in stale.read_text():
            stale.unlink()  # pre-research fiction; real format is package.json + .ts
            report["files"].append(f"{rel(stale)} (removed legacy fiction)")
        for name in ("package.json", "bug-corpus.ts"):
            _copy_verbatim(src / "omp" / name, ext / name, report["files"])
        report["notes"].append("omp: " + TRUST_NOTES["omp"])
    agents = repo / "AGENTS.md"
    if agents.exists():
        html_begin, html_end = "<!-- bugcorpus:start -->", "<!-- bugcorpus:end -->"
        text = agents.read_text()
        block = f"{html_begin}\n{POINTER.strip()}\n{html_end}\n"
        if html_begin in text and html_end in text:
            pre = text.split(html_begin)[0]
            post = text.split(html_end)[1]
            agents.write_text(pre + block + post.lstrip("\n"))
            report["pointers"].append("AGENTS.md: updated")
        else:
            agents.write_text(text.rstrip("\n") + "\n\n" + block)
            report["pointers"].append("AGENTS.md: appended")
    return report


# trace:exempt reason=internal-detail
def _read_hooks(path: Path) -> dict:
    if path.exists():
        try:
            data = json.loads(path.read_text())
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}
    return {}


# trace:exempt reason=internal-detail
def _has_hook_command(settings: dict, event: str, command: str) -> bool:
    try:
        groups = settings.get("hooks", {}).get(event, [])
        return any(h.get("command") == command for g in groups for h in g.get("hooks", []))
    except AttributeError:
        return False


# trace:exempt reason=internal-detail
def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


# trace:exempt reason=internal-detail
def _merge_codex_config(path: Path) -> str:
    snippet = (
        Path(__file__).resolve().parent.parent / "adapters" / "codex" / "config-snippet.toml"
    ).read_text()
    if path.exists():
        text = path.read_text()
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return f"{path}: left alone (unparseable TOML)"
        if "bugcorpus" in data.get("mcp_servers", {}):
            return f"{path}: unchanged"
        path.write_text(text.rstrip("\n") + "\n\n" + snippet)
        return f"{path}: merged"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Bug Corpus for Codex. Trusted-project surface; approve on first run.\n\n" + snippet
    )
    return f"{path}: created"


# trace:v1 id=impl.bugcorpus-adapters.check work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-MKCEMW39
def check(repo: str | Path, harnesses: list[str] | None = None) -> dict:
    """Verify installed adapters match sources and merges are present."""
    repo = Path(repo)
    problems: list[str] = []
    targets = {"claude", "codex", "omp"} if not harnesses else set(harnesses)
    canon = repo / CANON.parent
    if "claude" in targets:
        _check_tree(canon, repo / ".claude" / "skills" / "bug-corpus", problems)
        for cmd in sorted((repo / "adapters" / "claude" / "commands").glob("*.md")):
            _check_file(cmd, repo / ".claude" / "commands" / cmd.name, problems)
        settings = _read_hooks(repo / ".claude" / "settings.json")
        if not _has_hook_command(settings, "PostToolUse", HOOK_COMMAND):
            problems.append(".claude/settings.json: missing bugcorpus PostToolUse hook")
        if not _has_hook_command(settings, "Stop", "uv run bugcorpus hooks session-stop"):
            problems.append(".claude/settings.json: missing bugcorpus Stop hook")
        try:
            mcp = json.loads((repo / ".mcp.json").read_text())
            if mcp.get("mcpServers", {}).get("bugcorpus") != MCP_SERVER_ENTRY:
                problems.append(".mcp.json: bugcorpus server entry missing/drifted")
        except (OSError, ValueError):
            problems.append(".mcp.json: unreadable")
    if "codex" in targets:
        _check_tree(canon, repo / ".agents" / "skills" / "bug-corpus", problems)
        _check_file(
            repo / "adapters" / "codex" / "hooks.json", repo / ".codex" / "hooks.json", problems
        )
        cfg = repo / ".codex" / "config.toml"
        try:
            data = tomllib.loads(cfg.read_text())
            if "bugcorpus" not in data.get("mcp_servers", {}):
                problems.append(".codex/config.toml: missing mcp_servers.bugcorpus")
        except (OSError, tomllib.TOMLDecodeError):
            problems.append(".codex/config.toml: unreadable")
    if "omp" in targets:
        _check_tree(canon, repo / ".omp" / "skills" / "bug-corpus", problems)
        for name in ("package.json", "bug-corpus.ts"):
            _check_file(
                repo / "adapters" / "omp" / name,
                repo / ".omp" / "extensions" / "bug-corpus" / name,
                problems,
            )
        if (repo / ".omp" / "extensions" / "bug-corpus" / "plugin.json").exists():
            problems.append(".omp/extensions/bug-corpus/plugin.json: legacy fiction still present")
    return {"ok": not problems, "problems": problems}


# trace:exempt reason=internal-detail
def _check_file(src: Path, dest: Path, problems: list[str]) -> None:
    if not dest.exists() or dest.read_bytes() != src.read_bytes():
        problems.append(f"{dest}: missing or drifted from {src}")


# trace:exempt reason=internal-detail
def _check_tree(src: Path, dest: Path, problems: list[str]) -> None:
    for f in sorted(src.rglob("*")):
        if f.is_file():
            _check_file(f, dest / f.relative_to(src), problems)
