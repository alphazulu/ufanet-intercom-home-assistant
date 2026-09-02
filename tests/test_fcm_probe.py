"""Privacy tests for the standalone FCM research probe."""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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


@pytest.mark.asyncio
async def test_cleanup_without_started_listener_only_closes_session() -> None:
    client = MagicMock()
    client.stop = AsyncMock(
        side_effect=AssertionError("an unstarted listener must not be stopped")
    )
    session = MagicMock()
    session.close = AsyncMock()

    await probe.cleanup_probe_resources(
        client,
        listener_started=False,
        ufanet_session=session,
    )

    client.stop.assert_not_awaited()
    session.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_cleanup_closes_session_even_when_listener_stop_fails() -> None:
    client = MagicMock()
    client.stop = AsyncMock(side_effect=RuntimeError("stop failed"))
    session = MagicMock()
    session.close = AsyncMock()

    with pytest.raises(RuntimeError, match="stop failed"):
        await probe.cleanup_probe_resources(
            client,
            listener_started=True,
            ufanet_session=session,
        )

    session.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_authorized_devices_audit_is_read_only_and_privacy_safe(capsys) -> None:
    session = _FakeSession()

    def post_audit(url: str, **kwargs):
        session.calls.append(("POST", url, kwargs))
        return _FakeResponse(
            200,
            {
                "data": {
                    "device_list": [
                        {
                            "device_id": "private-device-1",
                            "title": "Andrey private phone",
                            "last_update": "2026-09-02T12:34:56+10:00",
                            "is_call_access": True,
                        },
                        {
                            "device_id": "private-device-2",
                            "title": "Home Assistant private",
                            "last_update": "2026-09-01T01:02:03Z",
                            "is_call_access": False,
                            "provider_private_extra": "secret-value",
                        },
                    ],
                    "devices_num_permission": True,
                }
            },
        )

    session.post = post_audit
    summary = await probe.audit_authorized_devices(
        session,
        "access-token",
        "https://example.test",
        now=datetime(2026, 9, 2, 16, 0, tzinfo=timezone.utc),
    )

    assert len(session.calls) == 1
    method, url, kwargs = session.calls[0]
    assert method == "POST"
    assert url == "https://example.test/api/v4/fcm_device/authorized_devices/"
    assert "json" not in kwargs
    assert "data" not in kwargs
    assert summary == {
        "total": 2,
        "valid_objects": 2,
        "invalid_entries": 0,
        "with_device_id": 2,
        "unique_device_ids": 2,
        "duplicate_device_ids": 0,
        "with_title": 2,
        "with_last_update": 2,
        "parseable_last_update": 2,
        "last_update_age_le_24h": 1,
        "last_update_age_1_7d": 1,
        "last_update_age_7_30d": 0,
        "last_update_age_30_90d": 0,
        "last_update_age_gt_90d": 0,
        "last_update_age_future": 0,
        "with_call_access": 2,
        "call_access_true": 1,
        "call_access_false": 1,
        "call_access_invalid": 0,
        "unknown_field_count": 1,
        "unknown_field_names": ("provider_private_extra",),
        "devices_num_permission": "true",
    }
    output = capsys.readouterr().out
    for secret in (
        "private-device-1",
        "private-device-2",
        "Andrey private phone",
        "Home Assistant private",
        "2026-09-02",
        "2026-09-01",
        "secret-value",
        "access-token",
    ):
        assert secret not in output


@pytest.mark.asyncio
async def test_authorized_devices_audit_rejects_http_error_without_body_leak(capsys) -> None:
    session = _FakeSession()

    def post_error(url: str, **kwargs):
        session.calls.append(("POST", url, kwargs))
        return _FakeResponse(403, {"device_id": "private-device-id", "detail": "private"})

    session.post = post_error
    with pytest.raises(RuntimeError, match="HTTP 403"):
        await probe.audit_authorized_devices(
            session, "access-token", "https://example.test"
        )

    output = capsys.readouterr().out
    assert "private-device-id" not in output
    assert "private" not in output
    assert "access-token" not in output


def test_authorized_devices_age_buckets_do_not_expose_timestamps() -> None:
    payload = {
        "data": {
            "device_list": [
                {"last_update": "2026-09-02T15:00:00Z"},
                {"last_update": "2026-08-30T16:00:00Z"},
                {"last_update": "2026-08-15T16:00:00Z"},
                {"last_update": "2026-07-01T16:00:00Z"},
                {"last_update": "2026-01-01T00:00:00Z"},
                {"last_update": "2026-09-03T16:00:00Z"},
            ],
            "devices_num_permission": False,
        }
    }
    summary = probe.summarize_authorized_devices(
        payload,
        now=datetime(2026, 9, 2, 16, 0, tzinfo=timezone.utc),
    )

    assert summary["last_update_age_le_24h"] == 1
    assert summary["last_update_age_1_7d"] == 1
    assert summary["last_update_age_7_30d"] == 1
    assert summary["last_update_age_30_90d"] == 1
    assert summary["last_update_age_gt_90d"] == 1
    assert summary["last_update_age_future"] == 1
    assert summary["devices_num_permission"] == "false"


def test_authorized_devices_summary_rejects_unknown_envelope_without_values() -> None:
    with pytest.raises(RuntimeError, match="Unexpected authorized-devices response schema"):
        probe.summarize_authorized_devices(
            {"data": {"device_list": "private-device-id"}}
        )
