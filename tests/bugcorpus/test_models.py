"""Corpus model validation: contracts that keep symptom-cause-invariant distinct."""

from bugcorpus.models import BugCase, Detector


# trace:v1 id=test.bugcorpus-models.bugcase-contract verifies=REQ-BUG-0VGE5410 exercises=impl.bugcorpus-models.bugcase
def test_bugcase_rejects_collapsed_fields():
    b = BugCase(id="BC-000001", title="t", symptom="s", root_cause="s", violated_invariant="i")
    assert any("symptom" in e for e in b.validate())


def test_bugcase_rejects_bad_id():
    b = BugCase(id="nope", title="t", symptom="s", root_cause="r", violated_invariant="i")
    assert any("bad id" in e for e in b.validate())


def test_detector_allows_inline_pattern_engines():
    assert Detector(id="eval-v1", engine="lexical", family="f").validate() == []
    assert Detector(id="eval-v1", engine="existing", family="f").validate() == []


def test_detector_requires_entrypoint_for_custom():
    assert any(
        "entrypoint" in e for e in Detector(id="eval-v1", engine="custom", family="f").validate()
    )


def test_detector_rejects_unknown_engine_and_state():
    errs = Detector(id="eval-v1", engine="nope", family="f", state="nope").validate()
    assert any("engine" in e for e in errs) and any("state" in e for e in errs)
