"""An immutable pending request, not a replay of the agent's previous turn.

RetryController and physical-call evidence deliberately live outside this
object. No credentials, response contents or physical clock are snapshotted.
"""
import hashlib

POLICY_ID = "call-checkpoint-v1"


class RequestCheckpoint:
    def __init__(self, body: bytes, *, event=lambda value: None):
        if not isinstance(body, bytes):
            raise TypeError("checkpoint requires immutable request bytes")
        self._body = body
        self.sha256 = hashlib.sha256(body).hexdigest()
        self.event = event
        self.discarded = 0
        self.committed = False
        self.event({"action": "checkpoint", "request_sha256": self.sha256, "policy": POLICY_ID})

    @property
    def body(self):
        return self._body

    def discard(self, reason):
        if self.committed:
            raise RuntimeError("cannot restore a committed external call")
        self.discarded += 1
        self.event({"action": "rollback", "reason": reason, "rollback": self.discarded,
                    "request_sha256": self.sha256, "policy": POLICY_ID})

    def commit(self):
        if self.committed:
            raise RuntimeError("external call already committed")
        self.committed = True
        self.event({"action": "commit", "rollbacks": self.discarded,
                    "request_sha256": self.sha256, "policy": POLICY_ID})
