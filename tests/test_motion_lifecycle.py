"""Lifecycle regression tests for privacy-safe motion event publication."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ufanet_intercom import async_setup_entry
from custom_components.ufanet_intercom.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
    EVENT_MOTION_ANALYTICS,
)


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="AB123",
        data={CONF_USERNAME: "AB123", CONF_PASSWORD: "secret"},
        unique_id="motion-lifecycle-test",
    )


@pytest.mark.asyncio
async def test_motion_coordinator_publishes_only_sanitized_bus_event(hass) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    skud = {"id": 7, "cctv_number": "PRIVATE-CAMERA", "custom_name": "Door"}

    api = MagicMock()
    api.async_login = AsyncMock()

    coordinator = MagicMock()
    coordinator.data = {7: skud}
    coordinator.async_config_entry_first_refresh = AsyncMock()

    call_coordinator = MagicMock()
    call_coordinator.data = {}
    call_coordinator.new_calls = []
    call_coordinator.async_refresh = AsyncMock()
    call_coordinator.async_add_listener.return_value = lambda: None

    key_passage_coordinator = MagicMock()
    key_passage_coordinator.data = {}
    key_passage_coordinator.new_passages = {}
    key_passage_coordinator.async_initialize = AsyncMock()
    key_passage_coordinator.async_refresh = AsyncMock()
    key_passage_coordinator.async_add_listener.return_value = lambda: None

    analytics_coordinator = MagicMock()
    analytics_coordinator.data = {7: {"supported": True}}
    analytics_coordinator.new_events = {}
    analytics_coordinator.async_initialize = AsyncMock()
    analytics_coordinator.async_refresh = AsyncMock()
    analytics_coordinator.async_add_listener.return_value = lambda: None

    controller = MagicMock()
    controller.async_initialize = AsyncMock()
    auto_manager = MagicMock(enabled=False)
    image_manager = MagicMock()
    image_manager.async_initialize = AsyncMock()

    with (
        patch("custom_components.ufanet_intercom.async_get_clientsession"),
        patch("custom_components.ufanet_intercom.UfanetApi", return_value=api),
        patch("custom_components.ufanet_intercom.UfanetCoordinator", return_value=coordinator),
        patch(
            "custom_components.ufanet_intercom.UfanetCallCoordinator",
            return_value=call_coordinator,
        ),
        patch(
            "custom_components.ufanet_intercom.UfanetKeyPassageCoordinator",
            return_value=key_passage_coordinator,
        ),
        patch(
            "custom_components.ufanet_intercom.UfanetMotionAnalyticsCoordinator",
            return_value=analytics_coordinator,
        ),
        patch(
            "custom_components.ufanet_intercom.UfanetArchiveController",
            return_value=controller,
        ),
        patch(
            "custom_components.ufanet_intercom.UfanetCallAutoSaveManager",
            return_value=auto_manager,
        ),
        patch(
            "custom_components.ufanet_intercom.UfanetLastCallImageStatusManager",
            return_value=image_manager,
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            AsyncMock(),
        ),
    ):
        assert await async_setup_entry(hass, entry) is True

    events = []
    hass.bus.async_listen(EVENT_MOTION_ANALYTICS, events.append)
    analytics_coordinator.new_events = {
        7: [
            {
                "occurred_at": "2026-09-02T10:00:34.793780+00:00",
                "cursor_id": "PRIVATE-CURSOR",
                "camera_number": "PRIVATE-CAMERA",
                "media_url": "https://private.invalid/image.jpg",
            }
        ]
    }
    motion_listener = analytics_coordinator.async_add_listener.call_args.args[0]
    motion_listener()
    await hass.async_block_till_done()

    assert len(events) == 1
    assert events[0].data == {
        "type": "motion",
        "skud_id": 7,
        "device_name": "Door",
        "occurred_at": "2026-09-02T10:00:34.793780+00:00",
    }
    serialized = repr(events[0].data)
    assert "PRIVATE-CAMERA" not in serialized
    assert "PRIVATE-CURSOR" not in serialized
    assert "private.invalid" not in serialized
