"""Privacy tests for the standalone FCM research probe."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).parents[1]
    / "tools"
    / "research"
    / "fcm_probe_py"
    / "probe.py"
)
SPEC = importlib.util.spec_from_file_location("ufanet_fcm_probe", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def test_sanitize_redacts_sender_ids_and_activity_time() -> None:
    payload = {
        "from": "firebase-sender-id",
        "fcmMessageId": "fcm-message-id",
        "data": {
            "reason": "sip",
            "uuid": "push-uuid",
            "time": "2026-08-29T12:58:57+05:00",
            "transport": "UDP",
        },
    }

    sanitized = probe.sanitize(payload)
    serialized = str(sanitized)

    assert sanitized["data"]["reason"] == "sip"
    assert sanitized["data"]["transport"] == "UDP"
    assert "firebase-sender-id" not in serialized
    assert "fcm-message-id" not in serialized
    assert "push-uuid" not in serialized
    assert "2026-08-29" not in serialized
    assert "sha256" not in serialized
