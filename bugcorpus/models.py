"""Core data models with strict validation (no external deps beyond yaml)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

BUG_ID_RE = re.compile(r"^BC-\d{6}$$")
DETECTOR_ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]{2,80}$")
STATES = ("draft", "candidate", "shadow", "warning", "blocking", "retired")
ENGINES = (
    "existing",
    "lexical",
    "ast-grep",
    "semgrep",
    "semgrep-taint",
    "codeql",
    "pysa",
    "custom",
)
COSTS = ("cheap", "medium", "expensive")
SEVERITIES = ("low", "medium", "high", "critical")
BUG_STATUS = ("proposed", "confirmed", "fixed", "invalid")


# trace:v1 id=impl.bugcorpus-models.bugcase work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-0VGE5410
@dataclass
class BugCase:
    id: str
    title: str
    status: str = "confirmed"
    created_at: str = ""
    language: str = "python"
    subsystem: str = ""
    severity: str = "medium"
    confidence: str = "medium"
    source: str = ""
    source_reference: str = ""
    bad_commit: str = ""
    good_commit: str = ""
    symptom: str = ""
    user_impact: str = ""
    root_cause: str = ""
    violated_invariant: str = ""
    required_preconditions: list = field(default_factory=list)
    triggering_operation: str = ""
    incorrect_behavior: str = ""
    correct_behavior: str = ""
    semantic_signature: dict = field(default_factory=dict)
    relevant_symbols: list = field(default_factory=list)
    relevant_types: list = field(default_factory=list)
    relevant_calls: list = field(default_factory=list)
    relevant_modules: list = field(default_factory=list)
    control_flow_properties: list = field(default_factory=list)
    data_flow_properties: list = field(default_factory=list)
    state_transition_properties: list = field(default_factory=list)
    ordering_properties: list = field(default_factory=list)
    known_positive_examples: list = field(default_factory=list)
    known_negative_examples: list = field(default_factory=list)
    detector_status: str = "none"
    detector_ids: list = field(default_factory=list)
    related_bug_cases: list = field(default_factory=list)
    family_id: str = ""

    # trace:inherit impl.bugcorpus-models.bugcase reason=method-of-traced-contract
    def validate(self) -> list[str]:
        errs = []
        if not BUG_ID_RE.match(self.id):
            errs.append(f"bad id {self.id!r}")
        for req in ("title", "symptom", "root_cause", "violated_invariant"):
            if not getattr(self, req):
                errs.append(f"missing {req}")
        if self.symptom == self.root_cause:
            errs.append("symptom must differ from root_cause")
        if self.root_cause == self.violated_invariant:
            errs.append("root_cause must differ from violated_invariant")
        if self.status not in BUG_STATUS:
            errs.append(f"bad status {self.status!r}")
        if self.severity not in SEVERITIES:
            errs.append(f"bad severity {self.severity!r}")
        if self.family_id and not re.match(r"^[a-z0-9][a-z0-9\-]{2,60}$", self.family_id):
            errs.append(f"bad family_id {self.family_id!r}")
        return errs


# trace:v1 id=impl.bugcorpus-models.detector work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-0VGE5410
@dataclass
class Detector:
    id: str
    version: int = 1
    family: str = ""
    engine: str = "custom"
    entrypoint: str = ""
    languages: list = field(default_factory=list)
    scope: str = ""
    cost: str = "cheap"
    state: str = "shadow"
    catches: list = field(default_factory=list)
    supersedes: list = field(default_factory=list)
    requires_full_scan: bool = False
    description: str = ""
    severity: str = "medium"
    confidence: str = "medium"
    remediation: str = ""
    patterns: list = field(default_factory=list)
    rule_file: str = ""
    config: str = ""
    existing: dict = field(default_factory=dict)
    run: list = field(default_factory=list)

    # trace:inherit impl.bugcorpus-models.detector reason=method-of-traced-contract
    def validate(self) -> list[str]:
        errs = []
        if not DETECTOR_ID_RE.match(self.id):
            errs.append(f"bad detector id {self.id!r}")
        if self.engine not in ENGINES:
            errs.append(f"bad engine {self.engine!r}")
        if self.state not in STATES:
            errs.append(f"bad state {self.state!r}")
        if self.cost not in COSTS:
            errs.append(f"bad cost {self.cost!r}")
        if self.engine not in ("existing", "lexical") and not self.entrypoint:
            errs.append("missing entrypoint")
        return errs


# trace:v1 id=impl.bugcorpus-models.finding work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-0VGE5410
@dataclass
class Finding:
    detector_id: str
    path: str
    start_line: int
    start_column: int = 1
    end_line: int = 0
    end_column: int = 1
    severity: str = "medium"
    confidence: str = "medium"
    message: str = ""
    explanation: str = ""
    evidence: str = ""
    fingerprint: str = ""
    remediation: str = ""
    bug_family: str = ""
    bug_cases: list = field(default_factory=list)

    # trace:inherit impl.bugcorpus-models.finding reason=method-of-traced-contract
    def to_dict(self) -> dict:
        return {
            k: getattr(self, k)
            for k in (
                "detector_id",
                "bug_family",
                "bug_cases",
                "path",
                "start_line",
                "start_column",
                "end_line",
                "end_column",
                "severity",
                "confidence",
                "message",
                "explanation",
                "evidence",
                "fingerprint",
                "remediation",
            )
        }
