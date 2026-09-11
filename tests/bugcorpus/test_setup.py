"""Setup correctness: nested discovery, finding aliases, language-aware init, doctor health."""

from pathlib import Path

from bugcorpus import store

REPO = Path(__file__).resolve().parents[2]


def _seed_nested_detector(root: Path) -> Path:
    d = root / ".bugcorpus" / "detectors" / "custom" / "nested-v1"
    d.mkdir(parents=True)
    (d / "detector.yaml").write_text(
        "id: nested-v1\nengine: lexical\nstate: warning\nfamily: f\n"
        "patterns:\n- regex: 'zzz_no_match_xyz'\n  message: never\n"
    )
    return d


# trace:v1 id=test.bugcorpus-setup.nested-discovery verifies=REQ-BUG-0VGE5410 exercises=impl.bugcorpus-store.load-detector
def test_nested_detector_discovery(tmp_path):
    (tmp_path / ".bugcorpus").mkdir()
    _seed_nested_detector(tmp_path)
    assert store.list_detectors(str(tmp_path)) == ["nested-v1"]
    assert store.detector_dir(str(tmp_path), "nested-v1").name == "nested-v1"
    det, _ = store.load_detector(str(tmp_path), "nested-v1")
    assert det.engine == "lexical"


def test_legacy_manifest_bug_key_normalizes(tmp_path):
    (tmp_path / ".bugcorpus").mkdir()
    d = tmp_path / ".bugcorpus" / "detectors" / "old-v1"
    d.mkdir(parents=True)
    (d / "detector.yaml").write_text("id: old-v1\nengine: lexical\nbug: BC-000007\n")
    det, _ = store.load_detector(str(tmp_path), "old-v1")
    assert det.catches == ["BC-000007"]
    from bugcorpus.engines import load_manifest

    assert load_manifest(d)["catches"] == ["BC-000007"]


def test_enrich_accepts_file_line_aliases():
    from bugcorpus.scanner import enrich

    f = enrich(REPO, {"id": "d", "family": "f"}, {"file": "src/a.ts", "line": 5, "message": "m"})
    assert (f.path, f.start_line, f.end_line) == ("src/a.ts", 5, 5)


def test_detect_scan_includes_per_language(tmp_path):
    from bugcorpus.cli import detect_scan_includes

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.ts").write_text("x")
    (tmp_path / "main.go").write_text("x")
    (tmp_path / "node_modules" / "dep").mkdir(parents=True)
    (tmp_path / "node_modules" / "dep" / "x.js").write_text("x")
    inc = detect_scan_includes(tmp_path)
    assert "**/*.ts" in inc and "**/*.go" in inc
    assert not any("node_modules" in p or ".js" in p for p in inc)
    assert ".bugcorpus/detectors/**/*.py" in inc


def test_init_writes_detected_scope(tmp_path, monkeypatch):
    from bugcorpus.cli import main as cli_main

    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.rs").write_text("x")
    monkeypatch.chdir(tmp_path)
    assert cli_main(["init", "."]) == 0
    text = (tmp_path / ".bugcorpus" / "config.toml").read_text()
    assert "**/*.rs" in text
    assert "node_modules/**" in text


def test_doctor_flags_setup_problems(tmp_path):
    from bugcorpus.doctor import corpus_health

    (tmp_path / ".bugcorpus" / "detectors" / "custom").mkdir(parents=True)
    (tmp_path / ".bugcorpus" / "corpus" / "BC-000001").mkdir(parents=True)
    (tmp_path / ".bugcorpus" / "corpus" / "BC-000001" / "bug.yaml").write_text(
        "id: BC-000001\ntitle: t\nsymptom: s\nroot_cause: r\nviolated_invariant: i\n"
    )
    (tmp_path / "only.txt").write_text("x")
    issues = corpus_health(str(tmp_path))
    by_msg = " | ".join(i["message"] for i in issues)
    assert any(i["level"] == "error" for i in issues)  # nothing discovered/scanned
    assert "family" in by_msg


# trace:v1 id=test.bugcorpus-unenrolled.clean-errors verifies=REQ-BUG-8HPVNRVG
def test_bug_commands_report_enrollment_not_errno(tmp_path, monkeypatch):
    import argparse as _ap

    from bugcorpus.cli import cmd_related, cmd_show, cmd_synthesize

    monkeypatch.chdir(tmp_path)
    for fn, args in (
        (cmd_show, {"id": "BC-000001"}),
        (cmd_related, {"id": "BC-000001"}),
        (cmd_synthesize, {"id": "BC-000001", "family": "", "engine": None}),
    ):
        res = fn(_ap.Namespace(**args))
        assert isinstance(res, dict), (fn, res)
        assert res["ok"] is False and "not enrolled" in res["error"], (fn, res)


# trace:v1 id=test.bugcorpus-unenrolled.unknown-id verifies=REQ-BUG-8HPVNRVG
def test_show_unknown_id_names_the_bug(tmp_path, monkeypatch):
    import argparse as _ap

    from bugcorpus.cli import cmd_show

    (tmp_path / ".bugcorpus").mkdir()
    monkeypatch.chdir(tmp_path)
    res = cmd_show(_ap.Namespace(id="BC-999999"))
    assert res["ok"] is False and "BC-999999" in res["error"]


# trace:v1 id=test.bugcorpus-hooks.no-tty-block verifies=REQ-BUG-8HPVNRVG
def test_hooks_never_read_a_terminal(monkeypatch, capsys):
    import argparse as _ap
    import sys as _sys

    from bugcorpus.cli import cmd_hooks, cmd_hooks_stop

    # trace:exempt reason=test-helper
    class _Tty:
        def isatty(self):
            return True

        def read(self, *a):
            raise AssertionError("hooks must not read a TTY")

    monkeypatch.setattr(_sys, "stdin", _Tty())
    cmd_hooks_stop()
    assert cmd_hooks(_ap.Namespace(hcmd="post-tool-use")) is None
    assert capsys.readouterr().out == ""


# trace:v1 id=test.bugcorpus-unenrolled.no-glob verifies=REQ-BUG-8HPVNRVG
def test_unenrolled_roots_never_glob(tmp_path):
    from bugcorpus.doctor import corpus_health
    from bugcorpus.scanner import collect_files

    (tmp_path / "big" / "nested").mkdir(parents=True)
    (tmp_path / "big" / "nested" / "a.py").write_text("x = 1\n")
    assert collect_files(tmp_path, {}) == []  # no .bugcorpus: never walk the tree
    issues = corpus_health(str(tmp_path))
    assert any("not enrolled" in i["message"] for i in issues)


def test_doctor_clean_on_healthy_repo():
    from bugcorpus.doctor import corpus_health

    assert corpus_health(str(REPO)) == []


def test_detector_model_accepts_engine_keys():
    from bugcorpus.models import Detector

    d = Detector(
        id="x-v1",
        engine="lexical",
        family="f",
        severity="high",
        patterns=[{"regex": "a", "message": "b"}],
    )
    assert d.validate() == []
    assert d.severity == "high"
