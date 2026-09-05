"""Tests for privacy-safe physical-key FCM completion handling."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ufanet_intercom.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.ufanet_intercom.fcm_key import (
    EVENT_KEY_ENROLLMENT,
    UfanetFcmManager,
)


FIREBASE_CONFIG = {
    "project_id": "example-project",
    "sender_id": "123456789",
    "app_id": "1:123456789:android:abcdef012345",
    "package_name": "example.android.app",
    "api_key": "not-a-real-key",
}


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "AB123", CONF_PASSWORD: "secret"},
        unique_id="ab123",
    )


def _manager(hass, entry: MockConfigEntry) -> UfanetFcmManager:
    manager = UfanetFcmManager(
        hass,
        entry,
        MagicMock(),
        FIREBASE_CONFIG,
        AsyncMock(),
    )
    manager._state = {"persistent_ids": []}  # noqa: SLF001
    manager._queue_save = MagicMock()  # type: ignore[method-assign]  # noqa: SLF001
    return manager


@pytest.mark.asyncio
async def test_key_add_success_refreshes_inventory_and_publishes_sanitized_event(hass) -> None:
    entry = _entry()
    key_coordinator = SimpleNamespace(async_request_refresh=AsyncMock())
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "key_passage_coordinator": key_coordinator,
    }
    events = []
    unsub = hass.bus.async_listen(EVENT_KEY_ENROLLMENT, events.append)
    manager = _manager(hass, entry)

    manager._handle_push(  # noqa: SLF001
        {
            "data": {
                "reason": "key_add",
                "key_status": "0",
                "key_id": "123",
                "title": "SECRET TITLE",
                "body": "SECRET BODY",
            }
        },
        "persistent-key-1",
        None,
    )
    await hass.async_block_till_done()
    unsub()

    key_coordinator.async_request_refresh.assert_awaited_once_with()
    assert len(events) == 1
    assert events[0].event_type == EVENT_KEY_ENROLLMENT
    assert events[0].data["type"] == "key_enrollment"
    assert events[0].data["source"] == "fcm"
    assert events[0].data["result"] == "success"
    assert events[0].data["inventory_refresh_succeeded"] is True

    event_text = str(events[0].data)
    status_text = str(manager.status())
    for secret in ("123", "SECRET TITLE", "SECRET BODY", "key_id", "title", "body"):
        assert secret not in event_text
        assert secret not in status_text

    status = manager.status()
    assert status["received_push_count"] == 1
    assert status["received_key_add_push_count"] == 1
    assert status["last_key_add_push_at"] is not None
    assert status["last_key_add_result"] == "success"


@pytest.mark.parametrize(
    "data",
    [
        {"reason": "key_add", "key_status": "1", "key_id": "123"},
        {"reason": "key_add", "key_status": "0"},
        {"reason": "key_add", "key_status": "0", "key_id": "not-an-int"},
        {"reason": "key_add", "key_id": "123"},
        {"reason": "key_add", "key_status": "invalid", "key_id": "123"},
    ],
)
@pytest.mark.asyncio
async def test_key_add_matches_native_error_semantics(hass, data: dict[str, str]) -> None:
    entry = _entry()
    key_coordinator = SimpleNamespace(async_request_refresh=AsyncMock())
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "key_passage_coordinator": key_coordinator,
    }
    events = []
    unsub = hass.bus.async_listen(EVENT_KEY_ENROLLMENT, events.append)
    manager = _manager(hass, entry)

    manager._handle_push({"data": data}, "persistent-key-error", None)  # noqa: SLF001
    await hass.async_block_till_done()
    unsub()

    assert manager.status()["last_key_add_result"] == "error"
    assert len(events) == 1
    assert events[0].data["result"] == "error"
    key_coordinator.async_request_refresh.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_key_add_event_survives_missing_inventory_coordinator(hass) -> None:
    entry = _entry()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {}
    events = []
    unsub = hass.bus.async_listen(EVENT_KEY_ENROLLMENT, events.append)
    manager = _manager(hass, entry)

    manager._handle_push(  # noqa: SLF001
        {"data": {"reason": "key_add", "key_status": "0", "key_id": "7"}},
        "persistent-key-no-coordinator",
        None,
    )
    await hass.async_block_till_done()
    unsub()

    assert len(events) == 1
    assert events[0].data["result"] == "success"
    assert events[0].data["inventory_refresh_succeeded"] is False


@pytest.mark.asyncio
async def test_key_add_event_survives_inventory_refresh_failure(hass) -> None:
    entry = _entry()
    key_coordinator = SimpleNamespace(
        async_request_refresh=AsyncMock(side_effect=RuntimeError("offline"))
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "key_passage_coordinator": key_coordinator,
    }
    events = []
    unsub = hass.bus.async_listen(EVENT_KEY_ENROLLMENT, events.append)
    manager = _manager(hass, entry)

    manager._handle_push(  # noqa: SLF001
        {"data": {"reason": "key_add", "key_status": "0", "key_id": "7"}},
        "persistent-key-refresh-failed",
        None,
    )
    await hass.async_block_till_done()
    unsub()

    assert len(events) == 1
    assert events[0].data["result"] == "success"
    assert events[0].data["inventory_refresh_succeeded"] is False
    assert manager.status()["last_key_add_result"] == "success"


@pytest.mark.asyncio
async def test_unrelated_push_does_not_emit_key_enrollment_event(hass) -> None:
    entry = _entry()
    events = []
    unsub = hass.bus.async_listen(EVENT_KEY_ENROLLMENT, events.append)
    manager = _manager(hass, entry)

    manager._handle_push(  # noqa: SLF001
        {"data": {"reason": "something_else", "key_id": "SECRET"}},
        "persistent-other",
        None,
    )
    await hass.async_block_till_done()
    unsub()

    assert events == []
    assert manager.status()["received_key_add_push_count"] == 0
    assert manager.status()["last_key_add_result"] is None
