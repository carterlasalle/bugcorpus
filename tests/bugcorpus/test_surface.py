"""User-facing CLI surface and engine edge behavior (all real, no mocks)."""

import json
import subprocess
from pathlib import Path

import pytest

from bugcorpus.cli import main as cli_main

REPO = Path(__file__).resolve().parents[2]


def run_cli(args, cwd=REPO):
    import os

    old = os.getcwd()
    os.chdir(cwd)
    try:
        return cli_main(args)
    finally:
        os.chdir(old)


# trace:v1 id=test.bugcorpus-cli.surface verifies=REQ-BUG-0VGE5410 exercises=impl.bugcorpus-cli.dispatch
def test_read_commands_succeed(capsys):
    assert run_cli(["show", "BC-000001"]) == 0
    assert run_cli(["related", "BC-000001"]) == 0
    assert run_cli(["search", "snapshot"]) == 0
    assert run_cli(["family", "list"]) == 0
    assert run_cli(["family", "show", "stale-state-after-await"]) == 0
    assert run_cli(["synthesize", "BC-000002"]) == 0
    assert run_cli(["doctor"]) == 0
    assert run_cli(["detector", "list"]) == 0
    assert run_cli(["detector", "show", "stale-state-after-await-v1"]) == 0
    assert run_cli(["suppress", "--list"]) == 0
    out = capsys.readouterr().out
    assert "BC-000001" in out or "stale" in out


def test_detector_run_and_export(capsys):
    assert (
        run_cli(
            [
                "detector",
                "run",
                "stale-state-after-await-v1",
                ".bugcorpus/corpus/BC-000001/fixtures/positive/bad.py",
            ]
        )
        == 0
    )
    assert run_cli(["export", "sarif", "--profile", "fast"]) == 0
    out = capsys.readouterr().out
    assert "2.1.0" in out or "findings" in out


def test_sarif_results_are_warning_level():
    from bugcorpus.sarif import to_sarif
    from bugcorpus.scanner import run_scan

    sarif = to_sarif(run_scan(str(REPO), profile="fast"))
    results = sarif["runs"][0]["results"]
    assert results
    # annotations only: the scan gate is the single failure authority
    assert {r["level"] for r in results} == {"warning"}
    assert all(r["locations"][0]["physicalLocation"]["region"]["startLine"] >= 1 for r in results)


def test_scan_profiles_and_detector_filter():
    from bugcorpus.scanner import run_scan

    fast = run_scan(str(REPO), profile="fast")
    full = run_scan(str(REPO), profile="full")
    assert fast["counts"]["detector-error"] == 0
    assert full["counts"]["detector-error"] == 0
    only = run_scan(str(REPO), detectors=["stale-state-after-await-v1"])
    assert [d["detector"] for d in only["detectors"]] == ["stale-state-after-await-v1"]
    changed = run_scan(str(REPO), scope="changed")
    assert changed["counts"]["detector-error"] == 0


def test_run_helper_timeout_and_missing_tool():
    from bugcorpus.engines import ENGINES, _run

    code, _, err = _run(["sleep", "30"], timeout=1)
    assert code == 124 and err == "timeout"
    res = ENGINES["existing"].scan(
        REPO, {"id": "x", "existing": {"tool": "no-such-tool-xyz"}}, REPO, [], 10
    )
    assert res.status == "unavailable"
    res = ENGINES["existing"].scan(REPO, {"id": "x", "existing": {"tool": "true"}}, REPO, [], 10)
    assert res.status == "clean"


def test_missing_rule_files_are_errors():
    from bugcorpus.engines import ENGINES

    ddir = REPO / ".bugcorpus" / "detectors" / "stale-state-after-await-v1"
    assert ENGINES["ast-grep"].scan(
        REPO, {"id": "a", "rule_file": "missing.yaml"}, ddir, [], 10
    ).status in ("unavailable", "detector-error")
    assert ENGINES["semgrep"].scan(
        REPO, {"id": "s", "config": "missing.yaml"}, ddir, [], 10
    ).status in ("unavailable", "detector-error")


def test_mcp_serve_protocol(monkeypatch, capsys):
    import io as _io

    from bugcorpus.mcp_server import serve

    monkeypatch.chdir(REPO)
    monkeypatch.setattr(
        "sys.stdin",
        _io.StringIO(
            '{"jsonrpc": "2.0", "id": 1, "method": "initialize", '
            '"params": {"protocolVersion": "2024-11-05"}}\n'
            '{"jsonrpc": "2.0", "method": "notifications/initialized"}\n'
            '{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}\n'
            '{"jsonrpc": "2.0", "id": 3, "method": "tools/call", '
            '"params": {"name": "bugcorpus_search", "arguments": {"query": "eval"}}}\n'
            '{"jsonrpc": "2.0", "id": 4, "method": "tools/call", '
            '"params": {"name": "nope", "arguments": {}}}\n'
            '{"jsonrpc": "2.0", "id": 5, "method": "ping"}\n'
            "not json at all\n"
        ),
    )
    serve()
    out = capsys.readouterr().out.splitlines()
    # notification + garbage line produce no response: 5 requests, 5 replies
    assert len(out) == 5
    lines = [json.loads(line) for line in out]
    assert all(line["jsonrpc"] == "2.0" for line in lines)
    init, tools, search, unknown, pong = lines
    assert init["result"]["capabilities"] == {"tools": {}}
    assert init["result"]["serverInfo"]["name"] == "bugcorpus"
    names = [t["name"] for t in tools["result"]["tools"]]
    assert "bugcorpus_scan" in names
    assert all(t["inputSchema"]["type"] == "object" for t in tools["result"]["tools"])
    hits = json.loads(search["result"]["content"][0]["text"])
    assert any(h["id"] == "BC-000002" for h in hits)
    assert unknown["error"]["code"] == -32602
    assert pong["result"] == {}


def test_verify_single_case_and_detector():
    assert run_cli(["verify", "BC-000001"]) == 0
    assert run_cli(["verify", "--detector", "stale-state-after-await-v1"]) == 0
    assert run_cli(["scan", "--profile", "fast"]) == 0


def test_cli_surfaces_errors_loudly():
    import argparse as _ap

    from bugcorpus.cli import cmd_show

    assert run_cli(["show", "BC-999999"]) != 0  # handled error: loud, non-zero
    res = cmd_show(_ap.Namespace(id="BC-999999"))
    assert res["ok"] is False and "BC-999999" in res["error"]  # clean, no Errno leak
    r = subprocess.run(
        ["uv", "run", "bugcorpus", "bogus-cmd"],
        capture_output=True,
        text=True,
        cwd=REPO,
        check=False,
    )
    assert r.returncode != 0


@pytest.mark.skipif(__import__("shutil").which("git") is None, reason="needs git")
def test_scan_diff_scope():
    from bugcorpus.scanner import changed_files

    files, _ = changed_files(REPO, "HEAD...HEAD")
    assert files == []


# trace:v1 id=test.bugcorpus-scanner.changed-exclude verifies=REQ-BUG-8HPVNRVG exercises=impl.bugcorpus-scanner.run
def test_scan_changed_applies_scan_exclude(tmp_path):
    import subprocess as _sp

    from bugcorpus.scanner import run_scan

    _sp.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    _sp.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    _sp.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / ".bugcorpus").mkdir()
    (tmp_path / ".bugcorpus" / "config.toml").write_text(
        '[scan]\ninclude = ["**/*.json"]\n'
        'exclude = [".bugcorpus/generated/**"]\ntimeout_seconds = 120\n'
    )
    d = tmp_path / ".bugcorpus" / "detectors" / "lex-excl-v1"
    d.mkdir(parents=True)
    (d / "detector.yaml").write_text(
        "id: lex-excl-v1\nengine: lexical\nstate: blocking\nfamily: f\n"
        "patterns:\n- regex: 'no-acl'\n  message: bad\n"
    )
    g = tmp_path / ".bugcorpus" / "generated"
    g.mkdir(parents=True)
    (g / "corpus-index.json").write_text('{"note": "--no-acl"}\n')
    _sp.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    _sp.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    with open(g / "corpus-index.json", "a") as fh:
        fh.write('{"more": "--no-acl"}\n')
    res = run_scan(str(tmp_path), scope="changed")
    assert all("generated" not in f["path"] for f in res["findings"])
