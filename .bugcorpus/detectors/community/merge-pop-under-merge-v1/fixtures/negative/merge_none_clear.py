# trace:exempt reason=test-fixture-intentional-detector-pattern
"""Negative: None-tombstone clear survives the merge."""
import json


def _merge_session_data(on_disk, incoming):
    merged = dict(on_disk)
    for key, value in incoming.items():
        merged[key] = value
    return merged


class SessionState:
    def _read(self, session_id):
        return json.loads(open(session_id).read())

    def _write(self, session_id, data):
        data = _merge_session_data(self._read(session_id), data)
        open(session_id, "w").write(json.dumps(data))

    def clear_pending_bootstrap(self, session_id):
        data = self._read(session_id)
        if data.get("pending_bootstrap") is not None:
            data["pending_bootstrap"] = None
            self._write(session_id, data)
