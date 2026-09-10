"""Engine output-parsing contracts, proven with fake binaries on PATH.

Rationale: the parsing code is where subprocess integrations rot. A stub
executable emitting canned output exercises the real adapter end to end
(discovery, invocation, parsing, finding normalization) without the tool.
"""

from pathlib import Path

import pytest

from bugcorpus.engines import ENGINES

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture()
def fakes(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "ast-grep").write_text(
        "#!/bin/sh\n"
        'echo \'[{"path":"x.py","range":{"start":{"line":3},"end":{"line":3}},'
        '"message":"m","text":"t"}]\''
    )
    (bindir / "semgrep").write_text(
        "#!/bin/sh\n"
        'echo \'{"results":[{"path":"y.py","start":{"line":2},"end":{"line":2},'
        '"extra":{"message":"m","lines":"l"}}],"errors":[]}\''
    )
    (bindir / "codeql").write_text("#!/bin/sh\necho '[]'")
    (bindir / "pyre").write_text(
        '#!/bin/sh\necho \'[{"path":"z.py","line":1,"description":"pyre-id hit","name":"n"}]\''
    )
    for f in bindir.iterdir():
        f.chmod(0o755)
    import os

    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + "/usr/bin:/bin")
    import shutil

    for tool in ("ast-grep", "semgrep", "codeql", "pyre"):
        assert shutil.which(tool) == str(bindir / tool)
    return bindir


def _detector(tmp_path, engine, **extra):
    ddir = tmp_path / "d"
    ddir.mkdir(exist_ok=True)
    manifest = {"id": "t", "engine": engine, **extra}
    return manifest, ddir


# trace:v1 id=test.bugcorpus-engines.parsing verifies=REQ-BUG-8HPVNRVG exercises=impl.bugcorpus-engines.protocol
def test_ast_grep_parses_findings(fakes, tmp_path):
    rule = tmp_path / "rule.yaml"
    rule.write_text("id: t\n")
    manifest, ddir = _detector(tmp_path, "ast-grep", rule_file=rule.name)
    (ddir / rule.name).write_text("id: t\n")
    res = ENGINES["ast-grep"].scan(tmp_path, manifest, ddir, ["x.py"], 10)
    assert res.status == "findings"
    assert res.findings[0]["start_line"] == 3


def test_ast_grep_missing_rule_is_error(fakes, tmp_path):
    manifest, ddir = _detector(tmp_path, "ast-grep", rule_file="nope.yaml")
    res = ENGINES["ast-grep"].scan(tmp_path, manifest, ddir, [], 10)
    assert res.status == "detector-error"


def test_ast_grep_bad_exit_is_error(tmp_path, monkeypatch, fakes):
    (Path(str(fakes)) / "ast-grep").write_text("#!/bin/sh\nexit 3\n")
    import os

    monkeypatch.setenv("PATH", str(fakes) + os.pathsep + "/usr/bin:/bin")
    rule = tmp_path / "rule.yaml"
    rule.write_text("id: t\n")
    manifest, ddir = _detector(tmp_path, "ast-grep", rule_file=rule.name)
    (ddir / rule.name).write_text("id: t\n")
    res = ENGINES["ast-grep"].scan(tmp_path, manifest, ddir, [], 10)
    assert res.status == "detector-error"


def test_semgrep_parses_findings(fakes, tmp_path):
    manifest, ddir = _detector(tmp_path, "semgrep", config="r.yaml")
    (ddir / "r.yaml").write_text("rules: []\n")
    res = ENGINES["semgrep"].scan(tmp_path, manifest, ddir, ["y.py"], 10)
    assert res.status == "findings"
    assert res.findings[0]["path"] == "y.py"


def test_semgrep_missing_config_is_error(fakes, tmp_path):
    manifest, ddir = _detector(tmp_path, "semgrep", config="nope.yaml")
    res = ENGINES["semgrep"].scan(tmp_path, manifest, ddir, [], 10)
    assert res.status == "detector-error"


def test_codeql_runs_manifest_command(fakes, tmp_path):
    manifest, ddir = _detector(tmp_path, "codeql", run=["codeql"])
    res = ENGINES["codeql"].scan(tmp_path, manifest, ddir, [], 10)
    assert res.status == "clean"
    manifest2, _ = _detector(tmp_path, "codeql")
    res2 = ENGINES["codeql"].scan(tmp_path, manifest2, ddir, [], 10)
    assert res2.status == "detector-error"  # no run command configured


def test_pysa_filters_to_detector(fakes, tmp_path):
    manifest, ddir = _detector(tmp_path, "pysa")
    manifest["id"] = "pyre-id"
    res = ENGINES["pysa"].scan(tmp_path, manifest, ddir, [], 10)
    assert res.status == "findings"
    assert res.findings[0]["path"] == "z.py"


def test_mcp_dispatch_show_related_scan():
    from bugcorpus.mcp_server import dispatch

    assert dispatch("bugcorpus_show", {"id": "BC-000001"})["family_id"] == "stale-state-after-await"
    assert any(h["id"] == "BC-000002" for h in dispatch("bugcorpus_related", {"id": "BC-000001"}))
    scan = dispatch("bugcorpus_scan", {"profile": "fast"})
    assert scan["counts"]["detector-error"] == 0
