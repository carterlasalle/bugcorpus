"""Community exchange: share detectors across repos with PR-gated trust.

Detectors are executable code, so nothing installs above shadow without
local verification, and contributions flow through pull requests the owner
reviews — like Dolt's branch/push/pull model applied to a detector corpus.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tarfile
from io import BytesIO
from pathlib import Path

from . import store

COMMUNITY_BRANCH = "community"
COMMUNITY_PREFIX = Path("detectors") / "community"
PROVENANCE = "provenance.json"


# trace:exempt reason=internal-detail
def _git(repo: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, cwd=repo, check=False, timeout=timeout
    )


# trace:exempt reason=internal-detail
def _provenance(repo: Path, did: str, det) -> dict:
    remote = _git(repo, "config", "--get", "remote.origin.url").stdout.strip()
    author = _git(repo, "config", "user.name").stdout.strip()
    email = _git(repo, "config", "user.email").stdout.strip()
    from . import __version__

    return {
        "id": did,
        "version": det.version,
        "engine": det.engine,
        "family": det.family,
        "catches": sorted(set(det.catches)),
        "source_repo": remote,
        "author": author,
        "author_email": email,
        "license": "MIT",
        "exported_at": store.utcnow(),
        "bugcorpus_version": __version__,
    }


# trace:v1 id=impl.bugcorpus-community.export work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-MKCEMW39
def export_detector(repo: Path, did: str, output: Path) -> dict:
    """Bundle a detector (manifest, code, fixtures, provenance) for sharing."""
    det, ddir = store.load_detector(str(repo), did)
    dest = output / did
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(ddir, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
    from .verifier import fixture_files

    manifest = store.normalize_manifest(store.load_yaml(dest / "detector.yaml"))
    subdir = {
        "positive": "positive",
        "negative": "negative",
        "adv_positive": "adversarial_positive",
        "adv_negative": "adversarial_negative",
    }
    bundled = 0
    for key, files in fixture_files(ddir, manifest, repo).items():
        for f in files:
            target = dest / "fixtures" / subdir.get(key, key) / f.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
            bundled += 1
    (dest / PROVENANCE).write_text(json.dumps(_provenance(repo, did, det), indent=2) + "\n")
    return {"ok": True, "id": did, "path": str(dest), "fixtures": bundled}


# trace:exempt reason=internal-detail
def _same_tree(a: Path, b: Path) -> bool:
    import hashlib as _hashlib

    def digest(root: Path) -> str:
        h = _hashlib.sha256()
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.name != PROVENANCE and "__pycache__" not in p.parts:
                h.update(str(p.relative_to(root)).encode())
                content = p.read_bytes()
                if p.name == "detector.yaml":
                    import yaml as _yaml

                    data = _yaml.safe_load(content) or {}
                    data.pop("state", None)  # local promotion state is not bundle identity
                    content = _yaml.safe_dump(data, sort_keys=True).encode()
                h.update(content)
        return h.hexdigest()

    return digest(a) == digest(b)


# trace:v1 id=impl.bugcorpus-community.import work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-MKCEMW39
def import_bundle(repo: Path, path: Path, force: bool = False) -> dict:
    """Install a detector bundle as shadow (or draft if fixtures fail).

    Never installs above shadow: promotion thresholds still decide. Refuses
    on id collision with differing content unless forced.
    """
    import yaml as _yaml

    from .verifier import verify_detector

    path = Path(path)
    manifest_file = path / "detector.yaml"
    if not manifest_file.exists():
        return {"ok": False, "error": f"no detector.yaml in {path}"}
    try:
        manifest = store.normalize_manifest(store.load_yaml(manifest_file))
        did = manifest.get("id") or path.name
    except ValueError as e:
        return {"ok": False, "error": f"unreadable manifest: {e}"}
    if manifest.get("entrypoint") and not (path / manifest["entrypoint"]).exists():
        return {"ok": False, "error": "bundle entrypoint missing"}
    dest = store.cdir(str(repo)) / COMMUNITY_PREFIX / did
    if dest.exists() and _same_tree(path, dest):
        return {"ok": True, "id": did, "updated": False, "reason": "identical already installed"}
    if dest.exists() and not force:
        return {
            "ok": False,
            "error": f"{did} exists with different content; re-run with force to overwrite",
        }
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(path, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
    (dest / PROVENANCE).write_text(
        json.dumps(
            {
                "imported_at": store.utcnow(),
                "imported_from": str(path),
                "license": "MIT",
                "forced_state": "shadow",
            },
            indent=2,
        )
        + "\n"
    )
    v = verify_detector(repo, did)
    state = "shadow" if v["ok"] else "draft"
    mp = dest / "detector.yaml"
    data = _yaml.safe_load(mp.read_text()) or {}
    data["state"] = state
    mp.write_text(_yaml.safe_dump(data, sort_keys=False))
    store.write_index(str(repo))
    return {
        "ok": True,
        "id": did,
        "updated": True,
        "state": state,
        "verify_ok": v["ok"],
        "metrics": v["metrics"],
        "error": v["error"],
    }


# trace:exempt reason=internal-detail
def _ensure_ref(repo: Path, ref: str) -> dict | None:
    """Sync ref from origin; fall back to the cached ref when offline."""
    if _git(repo, "fetch", "origin", f"+{ref}:{ref}").returncode == 0:
        return None
    if _git(repo, "rev-parse", "--verify", ref).returncode == 0:
        return None  # offline: fall back to the cached ref
    return {"ok": False, "error": f"ref {ref!r} not found locally and fetch failed"}


# trace:v1 id=impl.bugcorpus-community.sync work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-MKCEMW39
def list_community(repo: Path, ref: str = COMMUNITY_BRANCH) -> dict:
    """List detector ids available on a community ref (fetching if needed)."""
    if (err := _ensure_ref(repo, ref)) is not None:
        return err
    out = _git(repo, "ls-tree", "-r", "--name-only", ref, "--", ".bugcorpus/detectors/community/")
    if out.returncode != 0:
        return {"ok": False, "error": f"cannot list {ref}"}
    ids = sorted({Path(line).parts[3] for line in out.stdout.splitlines() if line.count("/") >= 4})
    return {"ok": True, "ref": ref, "detectors": ids}


# trace:exempt reason=internal-detail
def install_from_ref(
    repo: Path, ref: str = COMMUNITY_BRANCH, did: str | None = None, force: bool = False
) -> dict:
    """Fetch a community ref and import its detectors (or one) as shadow."""
    import tempfile as _tempfile

    if (err := _ensure_ref(repo, ref)) is not None:
        return err
    arc = _git(repo, "archive", ref, "--", ".bugcorpus/detectors/community/")
    if arc.returncode != 0 or not arc.stdout:
        return {"ok": False, "error": f"nothing to install from {ref!r}"}
    results = []
    with _tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(fileobj=BytesIO(arc.stdout.encode("latin1")), mode="r|*") as tf:
            tf.extractall(tmp)
        base = Path(tmp) / ".bugcorpus" / "detectors" / "community"
        if not base.is_dir():
            return {"ok": False, "error": f"no community detectors on {ref!r}"}
        for cand in sorted(p for p in base.iterdir() if p.is_dir()):
            if did and cand.name != did:
                continue
            results.append(import_bundle(repo, cand, force=force))
    installed = [r["id"] for r in results if r.get("ok") and r.get("updated")]
    up_to_date = [r["id"] for r in results if r.get("ok") and not r.get("updated")]
    failed = [r for r in results if not r.get("ok")]
    return {"ok": not failed, "installed": installed, "up_to_date": up_to_date, "failed": failed}


# trace:v1 id=impl.bugcorpus-community.publish work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-MKCEMW39
def publish(repo: Path, base: str = COMMUNITY_BRANCH, title: str = "", body: str = "") -> dict:
    """Push the current branch and open a PR against the community branch.

    Requires gh authed; fails with actionable errors otherwise. The PR — not
    this command — is the security review gate.
    """
    branch = _git(repo, "branch", "--show-current").stdout.strip()
    if not branch:
        return {"ok": False, "error": "detached HEAD: checkout a branch first"}
    if branch == base:
        return {"ok": False, "error": f"already on {base!r}; create a feature branch first"}
    gh = subprocess.run(
        ["gh", "auth", "status"], capture_output=True, text=True, cwd=repo, check=False, timeout=30
    )
    if gh.returncode != 0:
        return {
            "ok": False,
            "error": "GitHub not authed here; run `gh auth login`, then push and open a PR manually",
        }
    push = _git(repo, "push", "-u", "origin", branch, timeout=120)
    if push.returncode != 0:
        return {"ok": False, "error": f"push failed: {(push.stderr or push.stdout)[-500:]}"}
    pr = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--base",
            base,
            "--title",
            title or f"Community detector from {branch}",
            "--body",
            body
            or "Community detector contribution. Reviewer: check fixtures, scope, and code before merging.",
        ],
        capture_output=True,
        text=True,
        cwd=repo,
        check=False,
        timeout=120,
    )
    if pr.returncode != 0:
        return {"ok": False, "error": f"PR creation failed: {(pr.stderr or pr.stdout)[-500:]}"}
    return {"ok": True, "url": pr.stdout.strip().splitlines()[-1] if pr.stdout.strip() else ""}
