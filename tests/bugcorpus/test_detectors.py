"""Detector behavior on real fixtures: positives fire, negatives stay silent."""

from pathlib import Path

from bugcorpus import store
from bugcorpus.engines import ENGINES, load_manifest

REPO = Path(__file__).resolve().parents[2]


def run(detector: str, fixture: str):
    manifest = load_manifest(store.detector_dir(str(REPO), detector))
    engine = ENGINES[manifest["engine"]]
    res = engine.scan(
        REPO, manifest, store.detector_dir(str(REPO), detector), [str(REPO / fixture)], 60
    )
    assert res.status in ("clean", "findings"), res.detail
    return res


def bc1(*parts):
    return ".bugcorpus/corpus/BC-000001/fixtures/" + "/".join(parts)


def bc2(*parts):
    return ".bugcorpus/corpus/BC-000002/fixtures/" + "/".join(parts)


# trace:v1 id=test.bugcorpus-detectors.stale-state verifies=REQ-BUG-FESAJNS2 exercises=impl.detector-stale-state.check
def test_stale_detector_fires_on_bad_and_silent_on_fixed():
    assert run("stale-state-after-await-v1", bc1("positive", "bad.py")).status == "findings"
    assert run("stale-state-after-await-v1", bc1("negative", "fixed.py")).status == "clean"
    assert run("stale-state-after-await-v1", bc1("negative", "no_await.py")).status == "clean"


def test_stale_detector_survives_rename_and_honors_refresh():
    assert (
        run("stale-state-after-await-v1", bc1("adversarial", "adv_positive_renamed.py")).status
        == "findings"
    )
    assert (
        run("stale-state-after-await-v1", bc1("adversarial", "adv_negative_refreshed.py")).status
        == "clean"
    )


def test_lexical_detector_fires_on_eval_and_silent_on_safe():
    assert run("forbidden-dynamic-execution-v1", bc2("positive", "bad.py")).status == "findings"
    assert run("forbidden-dynamic-execution-v1", bc2("negative", "fixed.py")).status == "clean"
    assert (
        run("forbidden-dynamic-execution-v1", bc2("adversarial", "adv_negative_dispatch.py")).status
        == "clean"
    )


def test_missing_entrypoint_is_detector_error_not_clean():
    res = ENGINES["custom"].scan(
        REPO, {"id": "x", "entrypoint": "nope.py"}, REPO / ".bugcorpus", ["f.py"], 10
    )
    assert res.status == "detector-error"


def test_unavailable_engine_reports_unavailable():
    res = ENGINES["codeql"].scan(REPO, {"id": "x", "run": []}, REPO, [], 10)
    assert res.status in ("unavailable", "detector-error")
