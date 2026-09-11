"""Store, search, scan, verify, sarif, adapters: observable contracts."""

import shutil
from pathlib import Path

from bugcorpus import store
from bugcorpus.adapters import install
from bugcorpus.sarif import to_sarif
from bugcorpus.scanner import blocking_failed, run_scan
from bugcorpus.searcher import related, search
from bugcorpus.verifier import validate_corpus, verify_detector

REPO = Path(__file__).resolve().parents[2]


# trace:v1 id=test.bugcorpus-verify.fixtures verifies=REQ-BUG-FESAJNS2 exercises=impl.bugcorpus-verifier.fixture-eval
def test_verify_reports_metrics_and_lineage():
    v = verify_detector(REPO, "stale-state-after-await-v1")
    assert v["ok"] and v["metrics"]["recall"] == 1.0
    assert v["metrics"]["adv_recall"] == 1.0
    assert v["blocking_eligible"] is True


def test_verify_flags_sub_adv_recall_as_not_blocking_eligible():
    v = verify_detector(REPO, "forbidden-dynamic-execution-v1")
    assert v["ok"]  # known fixtures pass; aliasing is a documented limit
    assert v["blocking_eligible"] is False
    assert v["metrics"]["adv_recall"] < 1.0


def test_corpus_validates_clean():
    assert validate_corpus(REPO) == []


def test_scan_finds_only_known_positives():
    res = run_scan(str(REPO), profile="full")
    assert res["counts"]["detector-error"] == 0
    assert res["counts"]["unavailable"] == 0
    for f in res["findings"]:
        assert "fixtures/" in f["path"]


# trace:v1 id=test.bugcorpus-ci.blocking-gate verifies=REQ-BUG-WSZJ7M37 exercises=impl.bugcorpus-scanner.ci-gate
def test_blocking_gate_ignores_warning_findings():
    assert blocking_failed(run_scan(str(REPO), profile="pr")) is False
    blocking = {
        "repo": str(REPO),
        "new_findings": [
            {"detector_id": "d", "fingerprint": "fp_1", "path": "a.py", "start_line": 1}
        ],
        "detectors": [
            {
                "detector": "d",
                "status": "findings",
                "findings": [
                    {
                        "detector_id": "d",
                        "fingerprint": "fp_1",
                        "path": "a.py",
                        "start_line": 1,
                    }
                ],
            }
        ],
    }
    assert blocking_failed(blocking) is False  # d is not a blocking detector


def test_search_and_related_find_sample_bug():
    assert any(h["id"] == "BC-000001" for h in search(str(REPO), "snapshot await stale"))
    assert any(h["id"] == "BC-000002" for h in related(str(REPO), "BC-000001"))


def test_sarif_export_shape():
    sarif = to_sarif(run_scan(str(REPO), profile="fast"))
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["results"]


def test_next_id_and_index(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".bugcorpus").mkdir()
    assert store.next_bug_id(str(tmp_path)) == "BC-000001"
    idx = store.write_index(str(tmp_path))
    det_index = (tmp_path / ".bugcorpus" / "generated" / "detector-index.json").read_text()
    assert idx["bugs"] == [] and "detectors" in det_index


def test_adapters_install_idempotent(tmp_path):
    import json as _json

    from bugcorpus.adapters import check

    repo = tmp_path / "r"
    (repo / "skills" / "bug-corpus").mkdir(parents=True)
    shutil.copy(
        REPO / "skills" / "bug-corpus" / "SKILL.md", repo / "skills" / "bug-corpus" / "SKILL.md"
    )
    shutil.copytree(REPO / "adapters", repo / "adapters")
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.json").write_text(
        _json.dumps(
            {
                "hooks": {
                    "Stop": [{"matcher": "", "hooks": [{"type": "command", "command": "echo bye"}]}]
                }
            }
        )
    )
    (repo / "AGENTS.md").write_text("# Agents\n")
    first = install(repo)
    assert first["ok"]
    settings = _json.loads((repo / ".claude" / "settings.json").read_text())
    assert "Stop" in settings["hooks"]  # pre-existing hooks preserved
    assert any(
        "bugcorpus" in h.get("command", "")
        for g in settings["hooks"]["PostToolUse"]
        for h in g["hooks"]
    )
    stop_cmds = [h.get("command", "") for g in settings["hooks"]["Stop"] for h in g["hooks"]]
    assert "echo bye" in stop_cmds  # pre-existing Stop hook preserved
    assert any("session-stop" in c for c in stop_cmds)
    start_cmds = [
        h.get("command", "") for g in settings["hooks"]["SessionStart"] for h in g["hooks"]
    ]
    assert any("session-start" in c for c in start_cmds)
    assert (repo / ".omp" / "extensions" / "bug-corpus" / "bug-corpus.ts").exists()
    assert (repo / ".claude" / "commands" / "bug-learn.md").exists()
    assert (repo / ".codex" / "hooks.json").exists()
    tree_after_first = sorted(str(p) for p in repo.rglob("*") if p.is_file())
    second = install(repo)
    assert second["ok"]
    assert sorted(str(p) for p in repo.rglob("*") if p.is_file()) == tree_after_first
    assert all(
        "unchanged" in s or "updated" in s or "created" in s or "merged" in s or "ok" in s
        for s in second["skills"] + second["files"]
    )
    assert check(repo)["ok"]
    # tampering is detected
    (repo / ".claude" / "commands" / "bug-learn.md").write_text("tampered")
    assert check(repo)["ok"] is False


# trace:v1 id=test.bugcorpus-adapters.in-sync verifies=REQ-BUG-MKCEMW39 exercises=impl.bugcorpus-adapters.check
def test_installed_adapters_match_sources():
    from bugcorpus.adapters import check as check_adapters

    result = check_adapters(str(REPO))
    assert result["ok"], result["problems"]


# trace:exempt reason=thin-contract-assertion
def test_skill_frontmatter_valid():
    import re as _re

    text = (REPO / "skills" / "bug-corpus" / "SKILL.md").read_text()
    m = _re.match(r"---\n(.*?)\n---\n", text, _re.DOTALL)
    assert m, "canonical skill needs agentskills.io frontmatter"
    front = m.group(1)
    assert "name: bug-corpus" in front
    dm = _re.search(r"description: (.*)", front)
    assert dm and 10 < len(dm.group(1)) <= 1024


def test_detector_suite_merges_lineage_fixtures():
    from bugcorpus.engines import load_manifest
    from bugcorpus.verifier import fixture_files

    manifest = load_manifest(store.detector_dir(str(REPO), "stale-state-after-await-v1"))
    fx = fixture_files(store.detector_dir(str(REPO), "stale-state-after-await-v1"), manifest, REPO)
    # detector ships no fixtures of its own; everything comes via caught BugCases
    assert fx["positive"] and fx["negative"]
    assert any("adv_positive_renamed" in str(p) for p in fx["adv_positive"])


def test_learn_creates_bugcase_skeleton(tmp_path, monkeypatch):
    from bugcorpus.cli import main as cli_main

    monkeypatch.chdir(tmp_path)
    assert cli_main(["learn", "--title", "sample bug"]) == 0
    bug = tmp_path / ".bugcorpus" / "corpus" / "BC-000001" / "bug.yaml"
    assert bug.exists() and "sample bug" in bug.read_text()


# trace:v1 id=test.bugcorpus-adapters.bin-update verifies=REQ-BUG-MKCEMW39 exercises=impl.bugcorpus-adapters.install
def test_payload_and_bin_resolution():
    from bugcorpus.adapters import default_bin, payload_root, split_bin

    root = payload_root()
    assert (root / "skills" / "bug-corpus" / "SKILL.md").exists()
    assert (root / "adapters" / "omp" / "bug-corpus.ts").exists()
    assert (root / "adapters" / "claude" / "commands" / "bug-learn.md").exists()
    # dev checkout resolves the uv form even though .venv/bin is on PATH here
    assert default_bin() == "uv run bugcorpus"
    assert split_bin("bugcorpus") == ("bugcorpus", [])
    assert split_bin("uv run bugcorpus") == ("uv", ["run", "bugcorpus"])


def test_install_bin_override(tmp_path):
    import json as _json
    import tomllib

    from bugcorpus.adapters import check

    repo = tmp_path / "r"
    repo.mkdir()
    assert install(repo, bin="bugcorpus")["ok"]
    settings = _json.loads((repo / ".claude" / "settings.json").read_text())
    post = [h.get("command", "") for g in settings["hooks"]["PostToolUse"] for h in g["hooks"]]
    assert "bugcorpus hooks post-tool-use" in post
    assert not any(c.startswith("uv run") for c in post)
    hooks = _json.loads((repo / ".codex" / "hooks.json").read_text())
    flat = _json.dumps(hooks)
    assert "bugcorpus hooks session-stop" in flat and "uv run" not in flat
    cfg = tomllib.loads((repo / ".codex" / "config.toml").read_text())
    srv = cfg["mcp_servers"]["bugcorpus"]
    assert srv == {"command": "bugcorpus", "args": ["mcp"]}
    assert check(repo, bin="bugcorpus")["ok"]
    # default-bin check flags the drift honestly
    assert check(repo)["ok"] is False


def test_update_refreshes_repo(tmp_path, monkeypatch):
    from bugcorpus.cli import main as cli_main

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".bugcorpus").mkdir()
    assert cli_main(["update"]) == 0
    assert (tmp_path / ".claude" / "skills" / "bug-corpus" / "SKILL.md").exists()
    assert (tmp_path / ".bugcorpus" / "generated" / "corpus-index.json").exists()
    from bugcorpus import __version__
    from bugcorpus.cli import cmd_update

    class _A:
        pass

    res = cmd_update(_A())
    assert res["ok"] and res["version"] == __version__ and res["bin"] == "uv run bugcorpus"
    import tomllib

    meta = tomllib.loads((REPO / "pyproject.toml").read_text())
    assert meta["project"]["version"] == __version__  # single source of truth


# trace:v1 id=test.bugcorpus-init.human-output verifies=REQ-BUG-MKCEMW39
def test_init_reports_adapters_and_next_steps(tmp_path, monkeypatch, capsys):
    from bugcorpus.cli import cmd_init, print_human

    monkeypatch.chdir(tmp_path)

    class _A:
        path = "."
        force = False

    res = cmd_init(_A())
    assert res["ok"] and res["files"] > 0 and isinstance(res["notes"], list)
    print_human(res)
    out = capsys.readouterr().out
    assert "initialized" in out and "bugcorpus learn" in out and "bugcorpus verify" in out


# trace:v1 id=test.bugcorpus-cli.human-coverage verifies=REQ-BUG-MKCEMW39
def test_human_output_never_dumps_json_for_known_shapes(capsys):
    from bugcorpus.cli import print_human

    shapes = [
        ({"ok": True, "problems": []}, "adapters: OK"),
        ({"ok": True, "problems": ["x"]}, "problem: x"),
        ([{"id": "BC-1", "title": "t", "family": "f", "score": 3}], "BC-1"),
        ([{"sha": "abc", "subject": "s", "score": 1, "reasons": ["r"]}], "abc"),
        (["fam-a"], "fam-a"),
        ({"plan": "/tmp/p.yaml"}, "Wrote detector plan"),
        ({"family": "f", "plans": ["/tmp/p.yaml"]}, "/tmp/p.yaml"),
        ({"ok": True, "recorded": 2, "path": "/tmp/b.json"}, "Recorded 2"),
        ({"findings": 2, "fingerprints": ["a"]}, "baseline --record"),
        ({"ok": True, "entry": {"detector": "d", "reason": "r"}}, "Suppressed d"),
        ({"ok": True, "id": "BC-9", "created": True, "diff_sha": "x"}, "BC-9"),
        ({"ok": False, "reason": "clean worktree"}, "clean worktree"),
        ({"ok": True, "url": "http://pr/1"}, "http://pr/1"),
        ({"ok": False, "error": "boom"}, "boom"),
        ({"ok": True, "promoted": ["d"], "skipped": {}}, "Promoted"),
        ({"ok": True, "detector": "d", "from": "shadow", "to": "blocking"}, "blocking"),
        (
            {"status": "findings", "detail": "", "findings": []},
            "detector run: findings",
        ),
        (
            {"id": "m", "engine": "lexical", "state": "s", "family": "f", "catches": []},
            "m [s, lexical]",
        ),
        (
            {"id": "f", "title": "t", "invariant": "i", "semantic_signature": {}},
            "f — t",
        ),
    ]
    for payload, needle in shapes:
        print_human(payload)
        out = capsys.readouterr().out
        assert not out.lstrip().startswith("{"), payload
        assert needle in out, (payload, out)


def test_suppression_hides_matching_finding():
    from bugcorpus.scanner import suppressed_dict

    finding = {"detector_id": "d", "path": "a.py", "fingerprint": "fp_123"}
    assert suppressed_dict(finding, []) is False
    assert (
        suppressed_dict(
            finding, [{"detector": "d", "fingerprint": "fp_123", "reason": "t", "created_at": "x"}]
        )
        is True
    )
    assert (
        suppressed_dict(finding, [{"detector": "other", "reason": "t", "created_at": "x"}]) is False
    )


# trace:v1 id=test.bugcorpus-adapters.no-clobber verifies=REQ-BUG-MKCEMW39 exercises=impl.bugcorpus-adapters.install
def test_install_preserves_foreign_hooks(tmp_path):
    import json as _json

    repo = tmp_path / "r"
    repo.mkdir()
    foreign = {
        "hooks": {
            "PostCompact": [
                {"matcher": "manual|auto", "hooks": [{"type": "command", "command": "bd hook"}]}
            ],
            "PostToolUse": [
                {"matcher": "Write", "hooks": [{"type": "command", "command": "other-tool"}]}
            ],
        }
    }
    (repo / ".codex").mkdir()
    (repo / ".codex" / "hooks.json").write_text(_json.dumps(foreign))
    assert install(repo, bin="bugcorpus")["ok"]
    merged = _json.loads((repo / ".codex" / "hooks.json").read_text())
    flat = _json.dumps(merged)
    assert "bd hook" in flat and "other-tool" in flat  # foreign entries survive
    assert "bugcorpus hooks post-tool-use" in flat
    assert "bugcorpus hooks session-start" in flat
    # second run is stable: no duplicates appended
    assert install(repo, bin="bugcorpus")["ok"]
    again = _json.loads((repo / ".codex" / "hooks.json").read_text())
    assert _json.dumps(again, sort_keys=True) == _json.dumps(merged, sort_keys=True)
    # unparseable files are left alone, never overwritten
    (repo / ".codex" / "hooks.json").write_text("{oops")
    assert install(repo, bin="bugcorpus")["ok"]
    assert (repo / ".codex" / "hooks.json").read_text() == "{oops"
