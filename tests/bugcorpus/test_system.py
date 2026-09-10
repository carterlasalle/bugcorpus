"""Store, search, scan, verify, sarif, adapters: observable contracts."""

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
    repo = tmp_path / "r"
    (repo / "skills" / "bug-corpus").mkdir(parents=True)
    (repo / "skills" / "bug-corpus" / "SKILL.md").write_text("canon")

    (repo / "AGENTS.md").write_text("# Agents\n")
    first = install(repo)
    assert first["ok"]
    agents_after_first = (repo / "AGENTS.md").read_text()
    second = install(repo)
    assert second["ok"]
    assert (repo / "AGENTS.md").read_text() == agents_after_first
    assert "use the repository's bug-corpus skill" in agents_after_first


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
