# trace:exempt reason=test-fixture-intentional-detector-pattern
"""Positive: change-base resolved inside the per-row loop."""


def _unchanged_since_base(project, path, boundary):
    from tracelayer.git.repo import GitRepo

    repo = GitRepo(project.root)
    base = repo.default_base()
    if base is None:
        return False
    proc = repo.run("show", f"{base}:{path}")
    return proc.returncode == 0


def resolve(obl):
    obl["state"] = "satisfied"

def reconcile(project, path, obligations):
    for obl in obligations:
        if _unchanged_since_base(project, path, obl):
            resolve(obl)
