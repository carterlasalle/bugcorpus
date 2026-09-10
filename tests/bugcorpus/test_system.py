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


def test_blocking_gate_ignores_warning_findings():
    assert blocking_failed(run_scan(str(REPO), profile="pr")) is False


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
