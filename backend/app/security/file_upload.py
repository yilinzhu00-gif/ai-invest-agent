"""Quarantine validation before documents can enter parser queues."""

from dataclasses import dataclass


class FileRejected(Exception):
    pass


@dataclass(frozen=True)
class QuarantinedUpload:
    server_filename: str
    mime_type: str
    content: bytes


def inspect_upload(filename: str, content: bytes, *, max_bytes: int = 50 * 1024 * 1024) -> QuarantinedUpload:
    lowered = filename.lower()
    if len(content) > max_bytes:
        raise FileRejected("file_too_large")
    if b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" in content:
        raise FileRejected("eicar_detected")
    if lowered.endswith((".exe", ".sh", ".js")) or ".exe" in lowered:
        raise FileRejected("extension_rejected")
    if lowered.endswith(".pdf") and not content.startswith(b"%PDF"):
        raise FileRejected("mime_magic_mismatch")
    return QuarantinedUpload("quarantine-upload", "application/octet-stream", content)
