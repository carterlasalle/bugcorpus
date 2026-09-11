# trace:exempt reason=test-fixture-intentional-detector-pattern
"""Negative: base hoisted out of the loop, threaded as a parameter."""


def _base_fps(project, path, base):
    from tracelayer.git.repo import GitRepo

    if base is None:
        return {}
    proc = GitRepo(project.root).run("show", f"{base}:{path}")
    if proc.returncode != 0:
        return {}
    return {}


def resolve_many(session_id, keys):
    return len(keys)


def reconcile(project, path, obligations, base):
    to_resolve = set()
    for obl in obligations:
        if obl in _base_fps(project, path, base):
            to_resolve.add(obl)
    return resolve_many("s", to_resolve)
