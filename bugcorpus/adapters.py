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


# trace:exempt reason=internal-detail
def payload_root() -> Path:
    """Directory holding skills/ and adapters/ install sources.

    Installed wheels carry them as bugcorpus_data/ next to the package;
    a source checkout (or editable install) keeps them at the repo root.
    """
    here = Path(__file__).resolve().parent
    installed = here.parent / "bugcorpus_data"
    if (installed / "skills").is_dir() and (installed / "adapters").is_dir():
        return installed
    return here.parent


# trace:exempt reason=internal-detail
def _is_dev_checkout() -> bool:
    here = Path(__file__).resolve().parent
    return (
        (here.parent / "skills").is_dir()
        and (here.parent / "adapters").is_dir()
        and (here.parent / "pyproject.toml").exists()
    )


# trace:exempt reason=internal-detail
def default_bin() -> str:
    """How this repo should invoke bugcorpus.

    Source checkouts use `uv run bugcorpus` (works from the repo root no
    matter how hooks are spawned; .venv/bin must NOT count as "installed"
    since hook processes don't inherit it). Installed distributions use the
    `bugcorpus` entry point. Overridable per install with --bin.
    """
    if _is_dev_checkout():
        return "uv run bugcorpus"
    return "bugcorpus"


# trace:exempt reason=internal-detail
def split_bin(bin: str) -> tuple[str, list[str]]:
    parts = bin.split()
    return parts[0], parts[1:]


CANON = Path("skills/bug-corpus/SKILL.md")

MANAGED_BEGIN = "<!-- managed-bugcorpus:start -->"
MANAGED_END = "<!-- managed-bugcorpus:end -->"


# trace:exempt reason=internal-detail
def pointer_text(bin: str) -> str:
    return (
        "This repository uses Bug Corpus.\n"
        "For confirmed defects or requests to search for similar bugs,\n"
        f"use the repository's bug-corpus skill and `{bin}`.\n"
        "See skills/bug-corpus/SKILL.md.\n"
    )


# trace:exempt reason=internal-detail
def hook_post_command(bin: str) -> str:
    return f"{bin} hooks post-tool-use"


# trace:exempt reason=internal-detail
def hook_stop_command(bin: str) -> str:
    return f"{bin} hooks session-stop"


# trace:exempt reason=internal-detail
def hook_start_command(bin: str) -> str:
    return f"{bin} hooks session-start"


# trace:exempt reason=internal-detail
def mcp_server_entry(bin: str) -> dict:
    cmd, rest = split_bin(bin)
    return {"command": cmd, "args": [*rest, "mcp"]}


# trace:exempt reason=internal-detail
def codex_mcp_section(bin: str) -> str:
    cmd, rest = split_bin(bin)
    args = ", ".join([f'"{a}"' for a in [*rest, "mcp"]])
    return f'[mcp_servers.bugcorpus]\ncommand = "{cmd}"\nargs = [{args}]\n'


TRUST_NOTES = {
    "claude": ".mcp.json needs one-time approval in Claude Code; hooks run on trust of the checkout.",
    "codex": ".codex/hooks.json and .codex/config.toml are trusted-project surfaces; approve per https://learn.chatgpt.com/docs/hooks.",
    "omp": ".omp/extensions are auto-discovered; restart the session after install.",
}


def _managed_block(bin: str = "uv run bugcorpus") -> str:
    return f"{MANAGED_BEGIN}\n{pointer_text(bin).strip()}\n{MANAGED_END}\n"


# trace:exempt reason=internal-detail
def upsert_managed(path: Path, bin: str = "uv run bugcorpus") -> str:
    block = _managed_block(bin)
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
def _merge_hook_commands(path: Path, specs: list[tuple]) -> str:
    """Merge hook commands into a hooks.json-style file without clobbering.

    specs: (event, matcher or None, command, timeout). Existing entries —
    including other tools' hooks — are never touched or removed. Unparseable
    files are left alone, never overwritten.
    """
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except ValueError:
            return f"{path}: left alone (unparseable JSON)"
        if not isinstance(data, dict):
            return f"{path}: left alone (not a JSON object)"
    else:
        data = {}
    changed = False
    for event, matcher, command, timeout in specs:
        groups = data.setdefault("hooks", {}).setdefault(event, [])
        if any(h.get("command") == command for g in groups for h in g.get("hooks", [])):
            continue
        entry: dict = {"hooks": [{"type": "command", "command": command, "timeout": timeout}]}
        if matcher is not None:
            entry["matcher"] = matcher
        groups.append(entry)
        changed = True
    if not changed:
        return f"{path}: unchanged"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    return f"{path}: merged"


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
def install(repo: str | Path, harnesses: list[str] | None = None, bin: str | None = None) -> dict:
    repo = Path(repo)
    bin = bin or default_bin()
    payload = payload_root()
    skill_src = payload / CANON.parent
    if not (skill_src / "SKILL.md").exists():
        return {"ok": False, "error": f"canonical skill missing under {payload}"}
    src = payload / "adapters"
    targets = {"claude", "codex", "omp"} if not harnesses else set(harnesses)
    report: dict = {
        "ok": True,
        "bin": bin,
        "skills": [],
        "files": [],
        "pointers": [],
        "notes": [],
    }

    def rel(p: Path) -> str:
        return str(p.relative_to(repo))

    post_cmd, stop_cmd = hook_post_command(bin), hook_stop_command(bin)
    start_cmd = hook_start_command(bin)
    if "claude" in targets:
        _copy_tree(skill_src, repo / ".claude" / "skills" / "bug-corpus", report["skills"])
        for cmd in sorted((src / "claude" / "commands").glob("*.md")):
            _copy_verbatim(cmd, repo / ".claude" / "commands" / cmd.name, report["files"])
        report["files"].append(
            _merge_hook_commands(
                repo / ".claude" / "settings.json",
                [
                    ("PostToolUse", "Edit|Write", post_cmd, 60),
                    ("Stop", "", stop_cmd, 30),
                    ("SessionStart", "", start_cmd, 30),
                ],
            )
        )
        report["files"].append(
            _merge_json_object(
                repo / ".mcp.json", ["mcpServers", "bugcorpus"], mcp_server_entry(bin)
            )
        )
        report["pointers"].append(f"CLAUDE.md: {upsert_managed(repo / 'CLAUDE.md', bin)}")
        report["notes"].append("claude: " + TRUST_NOTES["claude"])
    if "codex" in targets:
        _copy_tree(skill_src, repo / ".agents" / "skills" / "bug-corpus", report["skills"])
        report["files"].append(
            _merge_hook_commands(
                repo / ".codex" / "hooks.json",
                [
                    ("PostToolUse", "Edit|Write", post_cmd, 60),
                    ("Stop", None, stop_cmd, 30),
                    ("SessionStart", None, start_cmd, 30),
                ],
            )
        )
        report["files"].append(_merge_codex_config(repo / ".codex" / "config.toml", bin))
        report["pointers"].append(f"CODEX.md: {upsert_managed(repo / 'CODEX.md', bin)}")
        report["notes"].append("codex: " + TRUST_NOTES["codex"])
    if "omp" in targets:
        _copy_tree(skill_src, repo / ".omp" / "skills" / "bug-corpus", report["skills"])
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
        block = f"{html_begin}\n{pointer_text(bin).strip()}\n{html_end}\n"
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
def _merge_codex_config(path: Path, bin: str = "uv run bugcorpus") -> str:
    section = (
        "# Bug Corpus MCP server. Project config is trusted-only; approve on first run.\n"
        "# No secrets here: stdio transport, no auth, no network.\n" + codex_mcp_section(bin)
    )
    if path.exists():
        text = path.read_text()
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return f"{path}: left alone (unparseable TOML)"
        if "bugcorpus" in data.get("mcp_servers", {}):
            return f"{path}: unchanged"
        path.write_text(text.rstrip("\n") + "\n\n" + section)
        return f"{path}: merged"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Bug Corpus for Codex. Trusted-project surface; approve on first run.\n\n" + section
    )
    return f"{path}: created"


# trace:v1 id=impl.bugcorpus-adapters.check work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-MKCEMW39
def check(repo: str | Path, harnesses: list[str] | None = None, bin: str | None = None) -> dict:
    """Verify installed adapters match sources and merges are present."""
    repo = Path(repo)
    bin = bin or default_bin()
    problems: list[str] = []
    targets = {"claude", "codex", "omp"} if not harnesses else set(harnesses)
    payload = payload_root()
    canon = payload / CANON.parent
    src = payload / "adapters"
    post_cmd, stop_cmd = hook_post_command(bin), hook_stop_command(bin)
    start_cmd = hook_start_command(bin)
    exp_mcp = mcp_server_entry(bin)
    exp_cmd, exp_rest = split_bin(bin)
    if "claude" in targets:
        _check_tree(canon, repo / ".claude" / "skills" / "bug-corpus", problems)
        for cmd in sorted((src / "claude" / "commands").glob("*.md")):
            _check_file(cmd, repo / ".claude" / "commands" / cmd.name, problems)
        settings = _read_hooks(repo / ".claude" / "settings.json")
        if not _has_hook_command(settings, "PostToolUse", post_cmd):
            problems.append(".claude/settings.json: missing bugcorpus PostToolUse hook")
        if not _has_hook_command(settings, "Stop", stop_cmd):
            problems.append(".claude/settings.json: missing bugcorpus Stop hook")
        if not _has_hook_command(settings, "SessionStart", start_cmd):
            problems.append(".claude/settings.json: missing bugcorpus SessionStart hook")
        try:
            mcp = json.loads((repo / ".mcp.json").read_text())
            if mcp.get("mcpServers", {}).get("bugcorpus") != exp_mcp:
                problems.append(".mcp.json: bugcorpus server entry missing/drifted")
        except (OSError, ValueError):
            problems.append(".mcp.json: unreadable")
    if "codex" in targets:
        _check_tree(canon, repo / ".agents" / "skills" / "bug-corpus", problems)
        _check_hooks_json(repo / ".codex" / "hooks.json", post_cmd, stop_cmd, problems, start_cmd)
        cfg = repo / ".codex" / "config.toml"
        try:
            data = tomllib.loads(cfg.read_text())
            srv = data.get("mcp_servers", {}).get("bugcorpus", {})
            if srv.get("command") != exp_cmd or srv.get("args") != [*exp_rest, "mcp"]:
                problems.append(".codex/config.toml: mcp_servers.bugcorpus missing/drifted")
        except (OSError, tomllib.TOMLDecodeError):
            problems.append(".codex/config.toml: unreadable")
    if "omp" in targets:
        _check_tree(canon, repo / ".omp" / "skills" / "bug-corpus", problems)
        for name in ("package.json", "bug-corpus.ts"):
            _check_file(
                src / "omp" / name,
                repo / ".omp" / "extensions" / "bug-corpus" / name,
                problems,
            )
        if (repo / ".omp" / "extensions" / "bug-corpus" / "plugin.json").exists():
            problems.append(".omp/extensions/bug-corpus/plugin.json: legacy fiction still present")
    for pointer in ("CLAUDE.md", "CODEX.md", "AGENTS.md"):
        p = repo / pointer
        if p.exists() and MANAGED_BEGIN in p.read_text() and f"`{bin}`" not in p.read_text():
            problems.append(f"{pointer}: managed block references a different invocation")
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


# trace:exempt reason=internal-detail
def _check_hooks_json(
    path: Path, post_cmd: str, stop_cmd: str, problems: list[str], start_cmd: str = ""
) -> None:
    """hooks.json is a template (invocation substituted); verify structurally."""
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        problems.append(f"{path}: unreadable")
        return
    hooks = data.get("hooks", {})

    def has(event: str, command: str) -> bool:
        return any(
            h.get("command") == command for g in hooks.get(event, []) for h in g.get("hooks", [])
        )

    if not has("PostToolUse", post_cmd):
        problems.append(f"{path}: missing bugcorpus PostToolUse hook")
    if not has("Stop", stop_cmd):
        problems.append(f"{path}: missing bugcorpus Stop hook")
    if start_cmd and not has("SessionStart", start_cmd):
        problems.append(f"{path}: missing bugcorpus SessionStart hook")
