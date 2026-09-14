"""Update checker: cached-only startup, throttle, envelope, refresh."""

from __future__ import annotations

import argparse
import json
import time

from bugcorpus import updatecheck as uc

FUTURE = "99.0.0"


# trace:exempt reason=test-helper
def seed_cache(tmp_path, monkeypatch, latest=FUTURE, age_s=0.0, notified=None):
    monkeypatch.setenv("BUGCORPUS_CACHE_DIR", str(tmp_path / "cache"))
    cached = {"latest": latest, "checkedAt": time.time() - age_s}
    if notified:
        cached["lastNotifiedVersion"], cached["lastNotifiedAt"] = notified
    path = tmp_path / "cache" / "bugcorpus" / "update.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cached))
    return path


# trace:v1 id=test.bugcorpus-updatecheck.compare verifies=REQ-BUG-MKCEMW39
def test_version_compare_ignores_shape_noise():
    assert uc.is_newer("0.3.1", "0.3.0")
    assert uc.is_newer("0.10.0", "0.9.9")
    assert not uc.is_newer("0.3.1", "0.3.1")
    assert not uc.is_newer("0.3.0", "0.3.1")
    assert not uc.is_newer("", "0.3.1")
    assert not uc.is_newer("bogus", "also-bogus")


# trace:v1 id=test.bugcorpus-updatecheck.cached-only verifies=REQ-BUG-MKCEMW39
def test_empty_cache_never_notifies_but_is_stale(tmp_path, monkeypatch):
    monkeypatch.setenv("BUGCORPUS_CACHE_DIR", str(tmp_path / "cache"))
    state = uc.check()
    assert state["latest"] is None
    assert state["update_available"] is False
    assert state["should_notify"] is False
    assert state["stale"] is True
    assert uc.notice_text(state) == ""


# trace:v1 id=test.bugcorpus-updatecheck.throttle verifies=REQ-BUG-MKCEMW39
def test_notify_once_per_day_per_release(tmp_path, monkeypatch):
    seed_cache(tmp_path, monkeypatch)
    first = uc.check()
    assert first["update_available"] is True
    assert first["should_notify"] is True
    assert FUTURE in uc.notice_text(first)

    uc.mark_notified(FUTURE)
    assert uc.check()["should_notify"] is False  # same release, same day: silent

    seed_cache(tmp_path, monkeypatch, notified=(FUTURE, time.time() - 25 * 3600))
    assert uc.check()["should_notify"] is True  # next day: remind again

    seed_cache(tmp_path, monkeypatch, latest="0.0.1")
    quiet = uc.check()
    assert quiet["update_available"] is False and uc.notice_text(quiet) == ""


# trace:v1 id=test.bugcorpus-updatecheck.refresh verifies=REQ-BUG-MKCEMW39
def test_refresh_reads_registry_and_survives_failure(tmp_path, monkeypatch):
    feed = tmp_path / "pypi.json"
    feed.write_text(json.dumps({"info": {"version": "7.7.7"}}))
    monkeypatch.setenv("BUGCORPUS_PYPI_URL", feed.as_uri())
    monkeypatch.setenv("BUGCORPUS_CACHE_DIR", str(tmp_path / "cache"))
    refreshed = uc.refresh()
    assert refreshed is not None and refreshed["latest"] == "7.7.7"

    monkeypatch.setenv("BUGCORPUS_PYPI_URL", (tmp_path / "missing.json").as_uri())
    before = (tmp_path / "cache" / "bugcorpus" / "update.json").read_text()
    assert uc.refresh() is None
    assert (tmp_path / "cache" / "bugcorpus" / "update.json").read_text() == before


# trace:v1 id=test.bugcorpus-updatecheck.default-url verifies=REQ-BUG-MKCEMW39
def test_default_registry_url_resolves_without_override(monkeypatch):
    monkeypatch.delenv("BUGCORPUS_PYPI_URL", raising=False)
    assert uc.pypi_url() == "https://pypi.org/pypi/bugcorpus/json"


# trace:v1 id=test.bugcorpus-updatecheck.background verifies=REQ-BUG-MKCEMW39
def test_background_refresh_only_when_stale(tmp_path, monkeypatch):
    import subprocess

    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: calls.append((a, k)) or None)
    seed_cache(tmp_path, monkeypatch)  # fresh
    assert uc.refresh_in_background_if_stale(uc.check()) is False
    assert calls == []

    seed_cache(tmp_path, monkeypatch, age_s=13 * 3600)  # stale
    assert uc.refresh_in_background_if_stale(uc.check()) is True
    assert calls and calls[0][0][0][-2:] == ["update-check", "--refresh"]
    assert calls[0][1].get("start_new_session") is True


# trace:v1 id=test.bugcorpus-updatecheck.session-envelope verifies=REQ-BUG-MKCEMW39
def test_session_start_envelope_and_foreground_mark(tmp_path, monkeypatch, capsys):
    from bugcorpus import cli

    repo = tmp_path / "repo"
    (repo / ".bugcorpus").mkdir(parents=True)
    monkeypatch.chdir(repo)
    seed_cache(tmp_path, monkeypatch)  # fresh + newer: notice due, no spawn

    cli.cmd_hooks_start()
    out = capsys.readouterr().out
    env = json.loads(out)  # human-only envelope, not model context
    assert FUTURE in env["systemMessage"]
    assert "bugs" in env["additionalContext"]

    res = cli.cmd_update_check(argparse.Namespace(refresh=False))
    assert res["should_notify"] is False  # foreground command marked it
    cli.cmd_hooks_start()
    out2 = capsys.readouterr().out
    assert not out2.lstrip().startswith("{")  # back to plain announcement


# trace:v1 id=test.bugcorpus-updatecheck.message-flavor verifies=REQ-BUG-MKCEMW39
def test_notice_names_installer_for_tool_installs(monkeypatch):
    monkeypatch.setattr("bugcorpus.adapters._is_dev_checkout", lambda: False)
    text = uc.notice_text({"should_notify": True, "installed": "0.1", "latest": "0.2"})
    assert "uv tool install" in text
    monkeypatch.setattr("bugcorpus.adapters._is_dev_checkout", lambda: True)
    text = uc.notice_text({"should_notify": True, "installed": "0.1", "latest": "0.2"})
    assert "git pull" in text
