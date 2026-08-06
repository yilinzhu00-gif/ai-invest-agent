from datetime import UTC, datetime, timedelta

import pytest

from backend.app.security.file_upload import FileRejected, inspect_upload
from backend.app.security.pending_action import PendingAction, PendingActionError


def test_suspicious_uploads_never_reach_parser() -> None:
    with pytest.raises(FileRejected, match="eicar_detected"):
        inspect_upload("report.pdf.exe", b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*")


def test_pending_action_rejects_modified_or_expired_confirmation() -> None:
    action = PendingAction.create("workspace-a", "user-a", "publish", {"report": "r1"}, datetime.now(UTC) + timedelta(seconds=1))
    with pytest.raises(PendingActionError, match="payload_mismatch"):
        action.confirm("workspace-a", "user-a", {"report": "r2"}, datetime.now(UTC))
