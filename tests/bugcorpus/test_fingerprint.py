"""Fingerprints survive line movement; distinct detectors never collide."""

from bugcorpus.fingerprint import fingerprint


# trace:v1 id=test.bugcorpus-fingerprint.stable verifies=REQ-BUG-8HPVNRVG exercises=impl.bugcorpus-fingerprint.stable
def test_fingerprint_stable_across_line_movement():
    a = fingerprint("det", "src/foo.py", "handle", "snapshot = get_snapshot()")
    b = fingerprint("det", "src/foo.py", "handle", "snapshot  =  get_snapshot()")
    assert a == b
    assert a.startswith("fp_")


def test_fingerprint_separates_detectors_and_symbols():
    base = ("src/foo.py", "handle", "x = 1")
    assert fingerprint("a", *base) != fingerprint("b", *base)
    assert fingerprint("a", *base) != fingerprint("a", "src/foo.py", "other", "x = 1")
