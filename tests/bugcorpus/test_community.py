"""Community exchange: export/import/install contracts."""

import json
import subprocess
from pathlib import Path

from bugcorpus import community, store

MANIFEST = """\
id: demo-no-eval
version: 1
family: unsafe-dynamic-execution
engine: lexical
languages: [python]
cost: cheap
state: warning
catches: []
severity: high
confidence: medium
description: Demo community detector.
remediation: Do not use eval.
patterns:
- regex: '(?<![\\w.])eval\\s*\\('
  message: "no eval"
"""

BAD = "x = eval(user_input)\n"
GOOD = "import ast\nx = ast.literal_eval(user_input)\n"


# trace:exempt reason=test-helper
def _git(repo: Path, *args: str):
    r = subprocess.run(
        ["git", *args], capture_output=True, text=True, cwd=repo, check=False, timeout=60
    )
    assert r.returncode == 0, r.stderr
    return r


# trace:exempt reason=test-helper
def _mkrepo(base: Path, name: str) -> Path:
    repo = base / name
    (repo / ".bugcorpus" / "detectors" / "demo-no-eval" / "fixtures" / "positive").mkdir(
        parents=True
    )
    (repo / ".bugcorpus" / "detectors" / "demo-no-eval" / "fixtures" / "negative").mkdir(
        parents=True
    )
    (repo / ".bugcorpus" / "detectors" / "demo-no-eval" / "detector.yaml").write_text(MANIFEST)
    (
        repo / ".bugcorpus" / "detectors" / "demo-no-eval" / "fixtures" / "positive" / "bad.py"
    ).write_text(BAD)
    (
        repo / ".bugcorpus" / "detectors" / "demo-no-eval" / "fixtures" / "negative" / "good.py"
    ).write_text(GOOD)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed")
    return repo


# trace:v1 id=test.bugcorpus-community.roundtrip verifies=REQ-BUG-MKCEMW39 exercises=impl.bugcorpus-community.export
def test_export_import_roundtrip_lands_shadow(tmp_path):
    src = _mkrepo(tmp_path, "src")
    out = tmp_path / "bundle"
    exp = community.export_detector(src, "demo-no-eval", out)
    assert exp["ok"] and exp["fixtures"] == 2
    assert (out / "demo-no-eval" / "provenance.json").exists()

    dst = tmp_path / "dst"
    dst.mkdir()
    imp = community.import_bundle(dst, out / "demo-no-eval")
    assert imp["ok"] and imp["verify_ok"] and imp["state"] == "shadow"
    installed = store.cdir(str(dst)) / "detectors" / "community" / "demo-no-eval"
    assert (installed / "detector.yaml").exists()
    again = community.import_bundle(dst, out / "demo-no-eval")
    assert again["ok"] and again["updated"] is False


# trace:v1 id=test.bugcorpus-community.collision verifies=REQ-BUG-MKCEMW39 exercises=impl.bugcorpus-community.import
def test_import_collision_refused_without_force(tmp_path):
    src = _mkrepo(tmp_path, "src")
    out = tmp_path / "bundle"
    out.mkdir()
    community.export_detector(src, "demo-no-eval", out)
    dst = tmp_path / "dst"
    dst.mkdir()
    assert community.import_bundle(dst, out / "demo-no-eval")["ok"]
    (out / "demo-no-eval" / "fixtures" / "positive" / "evil.py").write_text("eval(1)\n")
    refused = community.import_bundle(dst, out / "demo-no-eval")
    assert refused["ok"] is False and "force" in refused["error"]
    forced = community.import_bundle(dst, out / "demo-no-eval", force=True)
    assert forced["ok"] and forced["updated"] is True


# trace:v1 id=test.bugcorpus-community.draft verifies=REQ-BUG-MKCEMW39 exercises=impl.bugcorpus-community.import
def test_import_without_negatives_lands_draft(tmp_path):
    src = _mkrepo(tmp_path, "src")
    (
        src / ".bugcorpus" / "detectors" / "demo-no-eval" / "fixtures" / "negative" / "good.py"
    ).unlink()
    out = tmp_path / "bundle"
    out.mkdir()
    community.export_detector(src, "demo-no-eval", out)
    dst = tmp_path / "dst"
    dst.mkdir()
    imp = community.import_bundle(dst, out / "demo-no-eval")
    assert imp["ok"] and imp["state"] == "draft" and imp["verify_ok"] is False


# trace:v1 id=test.bugcorpus-community.sync verifies=REQ-BUG-MKCEMW39 exercises=impl.bugcorpus-community.sync
def test_list_and_install_from_ref(tmp_path):
    upstream = _mkrepo(tmp_path, "up")
    _git(upstream, "checkout", "-qb", "community")
    community_dir = upstream / ".bugcorpus" / "detectors" / "community"
    (community_dir / "demo-no-eval" / "fixtures" / "positive").mkdir(parents=True)
    (community_dir / "demo-no-eval" / "fixtures" / "negative").mkdir(parents=True)
    (community_dir / "demo-no-eval" / "detector.yaml").write_text(MANIFEST)
    (community_dir / "demo-no-eval" / "fixtures" / "positive" / "bad.py").write_text(BAD)
    (community_dir / "demo-no-eval" / "fixtures" / "negative" / "good.py").write_text(GOOD)
    _git(upstream, "add", "-A")
    _git(upstream, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "share")

    local = tmp_path / "local"
    local.mkdir()
    _git(local, "init", "-q", "-b", "main")
    _git(local, "remote", "add", "origin", str(upstream))
    listed = community.list_community(local, ref="community")
    assert listed["ok"] and listed["detectors"] == ["demo-no-eval"]
    installed = community.install_from_ref(local, ref="community")
    assert installed == {
        "ok": True,
        "installed": ["demo-no-eval"],
        "up_to_date": [],
        "failed": [],
    }
    repeat = community.install_from_ref(local, ref="community")
    assert repeat["up_to_date"] == ["demo-no-eval"] and repeat["installed"] == []
    manifest = (
        local / ".bugcorpus" / "detectors" / "community" / "demo-no-eval" / "detector.yaml"
    ).read_text()
    assert "\nstate: shadow\n" in manifest


# trace:v1 id=test.bugcorpus-community.publish-guards verifies=REQ-BUG-MKCEMW39 exercises=impl.bugcorpus-community.publish
def test_publish_guards_base_branch(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "community")
    res = community.publish(repo, base="community")
    assert res["ok"] is False and "feature branch" in res["error"]


# trace:v1 id=test.bugcorpus-community.provenance verifies=REQ-BUG-MKCEMW39 exercises=impl.bugcorpus-community.export
def test_export_provenance_records_origin(tmp_path):
    src = _mkrepo(tmp_path, "src")
    _git(src, "remote", "add", "origin", "git@example.com:me/repo.git")
    out = tmp_path / "bundle"
    out.mkdir()
    community.export_detector(src, "demo-no-eval", out)
    prov = json.loads((out / "demo-no-eval" / "provenance.json").read_text())
    assert prov["source_repo"] == "git@example.com:me/repo.git"
    assert prov["license"] == "MIT" and prov["id"] == "demo-no-eval"
