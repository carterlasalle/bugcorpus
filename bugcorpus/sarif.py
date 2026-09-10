"""SARIF export (thin layer over the canonical internal finding schema)."""

from __future__ import annotations


# trace:v1 id=impl.bugcorpus-sarif.export work=WORK-BUG-ZJBDCZZ0 satisfies=REQ-BUG-8HPVNRVG
def to_sarif(scan: dict) -> dict:
    rules, results = {}, []
    for r in scan.get("detectors", []):
        for f in r.get("findings", []):
            did = f["detector_id"]
            rules.setdefault(
                did, {"id": did, "name": did, "shortDescription": {"text": f.get("message", did)}}
            )
            results.append(
                {
                    "ruleId": did,
                    # Annotations only: the scan gate (blocking state) is the
                    # single failure authority, so nothing here is error-level.
                    "level": "warning",
                    "message": {"text": f.get("message", "")},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": f.get("path", "")},
                                "region": {
                                    "startLine": f.get("start_line", 1),
                                    "endLine": f.get("end_line", 1),
                                },
                            }
                        }
                    ],
                    "properties": {
                        "fingerprint": f.get("fingerprint", ""),
                        "family": f.get("bug_family", ""),
                        "explanation": f.get("explanation", ""),
                    },
                }
            )
    return {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [
            {
                "tool": {"driver": {"name": "bugcorpus", "rules": list(rules.values())}},
                "results": results,
            }
        ],
    }
