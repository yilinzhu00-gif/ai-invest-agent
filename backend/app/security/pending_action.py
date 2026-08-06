import hashlib
import json
from dataclasses import dataclass
from datetime import datetime


class PendingActionError(Exception):
    pass


@dataclass(frozen=True)
class PendingAction:
    workspace_id: str
    requested_by: str
    action_type: str
    payload_hash: str
    expires_at: datetime

    @classmethod
    def create(cls, workspace_id: str, requested_by: str, action_type: str, payload: dict[str, object], expires_at: datetime) -> "PendingAction":
        return cls(workspace_id, requested_by, action_type, _hash(payload), expires_at)

    def confirm(self, workspace_id: str, requested_by: str, payload: dict[str, object], now: datetime) -> None:
        if workspace_id != self.workspace_id or requested_by != self.requested_by:
            raise PendingActionError("principal_mismatch")
        if now >= self.expires_at:
            raise PendingActionError("action_expired")
        if _hash(payload) != self.payload_hash:
            raise PendingActionError("payload_mismatch")


def _hash(payload: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
