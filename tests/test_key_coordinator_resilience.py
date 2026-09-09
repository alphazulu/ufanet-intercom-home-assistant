"""Tests for resilient physical-key capability and passage coordination."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.ufanet_intercom.api import UfanetResponseError
from custom_components.ufanet_intercom.key_coordinator import UfanetKeyPassageCoordinator

SKUD_ID = 154273


@pytest.mark.asyncio
async def test_passage_failure_does_not_disable_key_capability(hass) -> None:
    api = MagicMock()
    api.async_get_key_recording_intercom_ids = AsyncMock(return_value={SKUD_ID})
    api.async_get_physical_keys = AsyncMock(return_value=[])
    api.async_get_key_passage_history = AsyncMock(
        side_effect=UfanetResponseError("synthetic passage failure")
    )

    coordinator = UfanetKeyPassageCoordinator(hass, api, "entry", {SKUD_ID})
    data = await coordinator._async_update_data()

    assert coordinator.capability_known is True
    assert coordinator.supports_skud(SKUD_ID) is True
    assert coordinator.last_capability_error_type is None
    assert coordinator.last_inventory_error_type is None
    assert coordinator.last_history_error_type == "UfanetResponseError"
    assert coordinator.history_failure_count == 1
    assert data == {
        SKUD_ID: {
            "key_count": 0,
            "last_passage_at": None,
            "history_healthy": False,
        }
    }


@pytest.mark.asyncio
async def test_capability_failure_preserves_last_known_supported_set(hass) -> None:
    api = MagicMock()
    api.async_get_key_recording_intercom_ids = AsyncMock(return_value={SKUD_ID})
    api.async_get_physical_keys = AsyncMock(return_value=[])
    api.async_get_key_passage_history = AsyncMock(
        return_value={
            "count": 0,
            "current_page": 0,
            "page_count": 0,
            "page_size": 25,
            "results": [],
        }
    )

    coordinator = UfanetKeyPassageCoordinator(hass, api, "entry", {SKUD_ID})
    await coordinator._async_update_data()
    assert coordinator.supports_skud(SKUD_ID) is True

    api.async_get_key_recording_intercom_ids.side_effect = UfanetResponseError(
        "synthetic capability failure"
    )
    with pytest.raises(UpdateFailed, match="capability"):
        await coordinator._async_update_data()

    assert coordinator.capability_known is True
    assert coordinator.supports_skud(SKUD_ID) is True
    assert coordinator.last_capability_error_type == "UfanetResponseError"


@pytest.mark.asyncio
async def test_inventory_failure_keeps_capability_separate(hass) -> None:
    api = MagicMock()
    api.async_get_key_recording_intercom_ids = AsyncMock(return_value={SKUD_ID})
    api.async_get_physical_keys = AsyncMock(
        side_effect=UfanetResponseError("synthetic inventory failure")
    )

    coordinator = UfanetKeyPassageCoordinator(hass, api, "entry", {SKUD_ID})
    with pytest.raises(UpdateFailed, match="inventory"):
        await coordinator._async_update_data()

    assert coordinator.capability_known is True
    assert coordinator.supports_skud(SKUD_ID) is True
    assert coordinator.last_inventory_error_type == "UfanetResponseError"
