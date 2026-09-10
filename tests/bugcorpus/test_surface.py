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
    assert run_cli(["show", "BC-999999"]) == 2
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
