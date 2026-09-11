# trace:exempt reason=test-fixture-intentional-detector-pattern
"""Adversarial negative: a single base call outside any loop.

Looks similar (same API, same file shape) but performs one subprocess
batch total. A loop-scoped detector must stay silent here.
"""
from tracelayer.git.repo import GitRepo


def change_base(project):
    try:
        return GitRepo(project.root).default_base()
    except Exception:
        return None
