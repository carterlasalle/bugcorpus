"""Coverage matrix: bugs × engines plus family rollups from live verification."""

import json
from pathlib import Path

from bugcorpus.coverage import build_matrix, render_human, write_matrix
from bugcorpus.models import ENGINES

REPO = Path(__file__).resolve().parents[2]


# trace:v1 id=test.bugcorpus-coverage.matrix verifies=REQ-BUG-FESAJNS2 exercises=impl.bugcorpus-coverage.build
def test_matrix_structure():
    matrix = build_matrix(REPO)
    assert matrix["version"] == 2
    assert matrix["engines"] == list(ENGINES)
    bugs = matrix["bugs"]
    assert {"BC-000001", "BC-000002"} <= set(bugs)  # corpus grows; pin presence, not size
    stale = bugs["BC-000001"]
    assert stale["engines"]["custom"] is True
    assert stale["engines"]["lexical"] is False
    assert stale["detectors"] == ["stale-state-after-await-v1"]
    assert bugs["BC-000002"]["engines"]["lexical"] is True
    assert bugs["BC-000002"]["engines"]["custom"] is False
    fam = matrix["families"]["stale-state-after-await"]
    assert fam["members"]["BC-000001"]["caught"] is True
    (det,) = [d for d in fam["detectors"] if d["id"] == "stale-state-after-await-v1"]
    assert det["known_recall"] == 1.0
    assert det["adv_recall"] == 1.0
    assert det["neg_fp_rate"] == 0.0
    assert det["state"] == "blocking"
    assert det["blocking_eligible"] is True
    lex = matrix["families"]["unsafe-dynamic-execution"]["detectors"][0]
    assert lex["adv_recall"] < 1.0
    assert lex["blocking_eligible"] is False


def test_matrix_written_to_generated():
    matrix, out = write_matrix(REPO)
    assert out.name == "coverage-matrix.json"
    back = json.loads(out.read_text())
    assert back["version"] == 2
    assert back["bugs"] == matrix["bugs"]
    assert back["families"].keys() == matrix["families"].keys()


def test_human_rendering():
    text = render_human(build_matrix(REPO))
    assert "Bug Corpus coverage" in text
    assert "FAM stale-state-after-await" in text
    assert "BC-000001 ✓" in text
    assert "known recall:" in text and "state:" in text


def test_coverage_cli():
    from bugcorpus.cli import main as cli_main

    assert cli_main(["coverage", "--json"]) == 0
