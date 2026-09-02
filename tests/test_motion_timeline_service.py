"""Tests for privacy-safe archive motion timeline service."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ufanet_intercom.api import UfanetResponseError
from custom_components.ufanet_intercom.const import DOMAIN, SERVICE_GET_MOTION_EVENTS
from custom_components.ufanet_intercom.services import async_setup_services


def _install_runtime(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Motion timeline test",
        data={},
        unique_id="motion-timeline-test",
    )
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "7")},
        name="Door",
    )
    api = MagicMock()
    coordinator = SimpleNamespace(
        data={7: {"id": 7, "cctv_number": "PRIVATE-CAMERA"}},
    )
    analytics = SimpleNamespace(
        data={7: {"supported": True}},
        last_update_success=True,
    )
    controller = SimpleNamespace(timezone_name="UTC")
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "analytics_coordinator": analytics,
        "archive_controllers": {7: controller},
        "options": {},
    }
    async_setup_services(hass, MagicMock())
    return device, analytics


@pytest.mark.asyncio
async def test_motion_timeline_service_returns_only_normalized_times(hass) -> None:
    device, _analytics = _install_runtime(hass)
    first = datetime(2026, 9, 2, 10, 0, 34, 793780, tzinfo=timezone.utc)
    second = datetime(2026, 9, 2, 10, 1, tzinfo=timezone.utc)

    with patch(
        "custom_components.ufanet_intercom.services.async_get_motion_timeline_events",
        AsyncMock(return_value=[first, second]),
    ) as loader:
        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_MOTION_EVENTS,
            {"device_id": device.id, "date": "2026-09-02"},
            blocking=True,
            return_response=True,
        )

    loader.assert_awaited_once()
    assert response["supported"] is True
    assert response["count"] == 2
    assert response["events"][0]["local_time"] == "10:00:34.79378"
    assert response["events"][0]["second_of_day"] == pytest.approx(36034.79378)
    serialized = json.dumps(response, default=str)
    assert "PRIVATE-CAMERA" not in serialized
    assert "cursor" not in serialized.lower()
    assert "event_id" not in serialized.lower()


@pytest.mark.asyncio
async def test_motion_timeline_service_recovers_capability_when_snapshot_unavailable(hass) -> None:
    device, analytics = _install_runtime(hass)
    analytics.data = None
    analytics.last_update_success = False
    event_time = datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)

    with (
        patch(
            "custom_components.ufanet_intercom.services.async_get_motion_capabilities",
            AsyncMock(return_value={"PRIVATE-CAMERA"}),
        ) as capabilities,
        patch(
            "custom_components.ufanet_intercom.services.async_get_motion_timeline_events",
            AsyncMock(return_value=[event_time]),
        ) as loader,
    ):
        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_MOTION_EVENTS,
            {"device_id": device.id, "date": "2026-09-02"},
            blocking=True,
            return_response=True,
        )

    capabilities.assert_awaited_once()
    loader.assert_awaited_once()
    assert response["supported"] is True
    assert response["count"] == 1


@pytest.mark.asyncio
async def test_motion_timeline_service_skips_unsupported_camera(hass) -> None:
    device, analytics = _install_runtime(hass)
    analytics.data = {}
    analytics.last_update_success = True

    with (
        patch(
            "custom_components.ufanet_intercom.services.async_get_motion_capabilities",
            AsyncMock(),
        ) as capabilities,
        patch(
            "custom_components.ufanet_intercom.services.async_get_motion_timeline_events",
            AsyncMock(),
        ) as loader,
    ):
        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_MOTION_EVENTS,
            {"device_id": device.id, "date": "2026-09-02"},
            blocking=True,
            return_response=True,
        )

    assert response["supported"] is False
    assert response["events"] == []
    capabilities.assert_not_awaited()
    loader.assert_not_awaited()


@pytest.mark.asyncio
async def test_motion_timeline_service_sanitizes_ucams_error(hass) -> None:
    device, _analytics = _install_runtime(hass)

    with patch(
        "custom_components.ufanet_intercom.services.async_get_motion_timeline_events",
        AsyncMock(side_effect=UfanetResponseError("PRIVATE-CAMERA secret body")),
    ):
        with pytest.raises(HomeAssistantError) as err:
            await hass.services.async_call(
                DOMAIN,
                SERVICE_GET_MOTION_EVENTS,
                {"device_id": device.id, "date": "2026-09-02"},
                blocking=True,
                return_response=True,
            )

    assert str(err.value) == "Unable to load motion timeline events"
    assert "PRIVATE-CAMERA" not in str(err.value)
