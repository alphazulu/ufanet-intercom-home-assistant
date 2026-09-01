"""Privacy tests for the standalone FCM research probe."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


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


class _FakeResponse:
    def __init__(self, status: int, payload: object) -> None:
        self.status = status
        self._text = json.dumps(payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def text(self) -> str:
        return self._text


class _FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def delete(self, url: str, **kwargs):
        self.calls.append(("DELETE", url, kwargs))
        return _FakeResponse(200, {"status": "ok"})

    def post(self, url: str, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return _FakeResponse(200, {"status": "ok"})


@pytest.mark.asyncio
async def test_verify_unregister_only_deletes_and_restores_own_device(
    capsys,
) -> None:
    session = _FakeSession()

    await probe.verify_unregister_with_ufanet(
        session,
        "access-token",
        "fcm-token",
        "private-device-id",
        "Home Assistant",
        "private.package",
        "https://example.test",
    )

    assert [call[0] for call in session.calls] == ["DELETE", "POST"]
    assert session.calls[0][1] == "https://example.test/api/v0/fcm/"
    assert session.calls[0][2]["json"] == {"device_id": "private-device-id"}
    assert session.calls[1][2]["json"] == {
        "token": "fcm-token",
        "device_id": "private-device-id",
        "title": "Home Assistant",
        "application": "private.package",
        "os": 0,
        "token_type": 0,
    }
    output = capsys.readouterr().out
    assert "private-device-id" not in output
    assert "fcm-token" not in output
    assert "contract verified" in output


@pytest.mark.asyncio
async def test_unregister_rejects_http_error_without_echoing_device(capsys) -> None:
    session = _FakeSession()

    def delete_error(url: str, **kwargs):
        session.calls.append(("DELETE", url, kwargs))
        return _FakeResponse(409, {"device_id": "private-device-id"})

    session.delete = delete_error

    with pytest.raises(RuntimeError, match="HTTP 409"):
        await probe.unregister_token_with_ufanet(
            session,
            "access-token",
            "private-device-id",
            "https://example.test",
        )

    assert "private-device-id" not in capsys.readouterr().out
