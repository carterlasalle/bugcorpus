# trace:exempt reason=test-fixture-intentional-detector-pattern
"""Adversarial negative: pop-clear is safe when _write plain-overwrites.

No merge function exists here, so a deletion propagates exactly as written
and pop is the correct, simplest tool. A detector scoped to merge-on-write
stores must stay silent on this file.
"""
import json


class SimpleStore:
    def _read(self, session_id):
        return json.loads(open(session_id).read())

    def _write(self, session_id, data):
        open(session_id, "w").write(json.dumps(data))

    def clear_token(self, session_id):
        data = self._read(session_id)
        if data.pop("token", None) is not None:
            self._write(session_id, data)
