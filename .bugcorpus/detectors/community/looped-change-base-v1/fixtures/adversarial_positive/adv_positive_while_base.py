# trace:exempt reason=test-fixture-intentional-detector-pattern
"""Adversarial positive: same fan-out through a while loop."""


def drain(project, rows):
    from tracelayer.git.repo import GitRepo

    i = 0
    while i < len(rows):
        base = GitRepo(project.root).default_base()
        if base is not None:
            rows[i]["base"] = base
        i += 1
