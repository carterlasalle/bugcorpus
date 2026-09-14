"""Shared tool-update checker: stale-while-revalidate, never blocks startup.

Every harness adapter (Claude/Codex SessionStart hooks, the OMP extension,
future pi/OpenCode shims) funnels through one interface:

    bugcorpus update-check --json     # cached only, ~instant, marks notice
    bugcorpus update-check --refresh  # network fetch, run detached

On the startup path only the cached read runs: compare the running
distribution's version against the last PyPI version seen in
~/.cache/bugcorpus/update.json. If the cache is older than STALE_AFTER, a
detached refresh is kicked off and the *stale* answer is still returned
immediately. Notices are throttled to at most one per NOTIFY_EVERY per
released version, so ten session starts do not mean ten warnings.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PACKAGE = "bugcorpus"
PYPI_URL = "https://pypi.org/pypi/bugcorpus/json"
STALE_AFTER = 12 * 3600  # refresh the cached latest version at most this often
NOTIFY_EVERY = 24 * 3600  # remind about the same release at most this often
REFRESH_TIMEOUT = 10  # seconds; refresh runs detached, never on startup


# trace:exempt reason=internal-detail
def cache_file() -> Path:
    override = os.environ.get("BUGCORPUS_CACHE_DIR")
    base = (
        Path(override)
        if override
        else Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    )
    return base / PACKAGE / "update.json"


# trace:exempt reason=internal-detail
def pypi_url() -> str:
    return os.environ.get("BUGCORPUS_PYPI_URL") or PYPI_URL


# trace:exempt reason=internal-detail
def parse_version(s: str) -> tuple:
    parts = []
    for piece in str(s).strip().split("."):
        digits = "".join(c for c in piece if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


# trace:exempt reason=internal-detail
def is_newer(latest: str, installed: str) -> bool:
    try:
        return parse_version(latest) > parse_version(installed)
    except (TypeError, ValueError):
        return False


# trace:exempt reason=internal-detail
def installed_version() -> str:
    from . import __version__

    return __version__


# trace:exempt reason=internal-detail
def read_cache() -> dict:
    try:
        data = json.loads(cache_file().read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


# trace:exempt reason=internal-detail
def write_cache(data: dict) -> None:
    path = cache_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


# trace:v1 id=impl.bugcorpus-updatecheck.check work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-MKCEMW39
def check() -> dict:
    """Cached-only update state. Pure read: no network, no spawn, no raise."""
    installed = installed_version()
    now = time.time()
    cached = read_cache()
    latest = cached.get("latest") if isinstance(cached.get("latest"), str) else None
    checked_at = cached.get("checkedAt") or 0
    age = max(0.0, now - float(checked_at or 0))
    available = bool(latest and is_newer(latest, installed))
    last_ver = cached.get("lastNotifiedVersion")
    last_at = float(cached.get("lastNotifiedAt") or 0)
    should_notify = bool(available and (last_ver != latest or now - last_at >= NOTIFY_EVERY))
    return {
        "installed": installed,
        "latest": latest,
        "checked_age_s": round(age, 1),
        "stale": age >= STALE_AFTER,
        "update_available": available,
        "should_notify": should_notify,
    }


# trace:v1 id=impl.bugcorpus-updatecheck.notice work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-MKCEMW39
def notice_text(state: dict) -> str:
    """Human-only warning line. Empty unless the caller should notify now."""
    if not state.get("should_notify"):
        return ""
    from .adapters import _is_dev_checkout

    if _is_dev_checkout():
        how = "git pull the bugcorpus checkout"
    else:
        how = "uv tool install --force bugcorpus (or your installer equivalent)"
    return (
        f"Bug Corpus {state['installed']} is outdated "
        f"({state['latest']} available). Run: {how}, "
        f"then `bugcorpus update` in enrolled repos."
    )


# trace:v1 id=impl.bugcorpus-updatecheck.notify work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-MKCEMW39
def mark_notified(latest: str) -> None:
    """Record that this release was surfaced, for the 24h throttle."""
    cached = read_cache()
    cached["lastNotifiedVersion"] = latest
    cached["lastNotifiedAt"] = time.time()
    write_cache(cached)


# trace:exempt reason=internal-detail
def fetch_latest() -> str | None:
    """One PyPI read. Returns the version string, or None on any failure."""
    try:
        with urllib.request.urlopen(pypi_url(), timeout=REFRESH_TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        ver = (data.get("info") or {}).get("version")
        return ver if isinstance(ver, str) and ver else None
    except Exception:  # noqa: BLE001 -- refresh is best-effort by design
        return None


# trace:v1 id=impl.bugcorpus-updatecheck.refresh work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-MKCEMW39
def refresh() -> dict | None:
    """Fetch PyPI now and rewrite the cache, preserving throttle fields."""
    latest = fetch_latest()
    if not latest:
        return None
    cached = read_cache()
    cached["latest"] = latest
    cached["checkedAt"] = time.time()
    write_cache(cached)
    return check()


# trace:exempt reason=internal-detail
def refresh_in_background_if_stale(state: dict | None = None) -> bool:
    """Detached `update-check --refresh`; never waits, never raises."""
    try:
        if (state or check()).get("stale", True) is False:
            return False
        subprocess.Popen(
            [sys.argv[0], "update-check", "--refresh"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except (OSError, ValueError):
        return False
