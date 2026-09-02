"""Tests for privacy-safe Ufanet EventEntity state."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from homeassistant.core import Event
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ufanet_intercom.const import (
    DOMAIN,
    EVENT_KEY_PASSAGE,
    EVENT_MOTION_ANALYTICS,
)
from custom_components.ufanet_intercom.event import (
    UfanetKeyPassageEvent,
    UfanetMotionAnalyticsEvent,
    async_setup_entry,
)


def _skud() -> dict:
    return {
        "id": 7,
        "custom_name": "Front door",
        "role": {"name": "Intercom"},
        "model": 39,
    }


def test_key_passage_event_keeps_only_documented_attributes() -> None:
    coordinator = SimpleNamespace(last_update_success=True, data={7: {}})
    entity = UfanetKeyPassageEvent(coordinator, _skud())
    entity.async_write_ha_state = MagicMock()

    entity._async_handle_passage(  # noqa: SLF001
        Event(
            EVENT_KEY_PASSAGE,
            {
                "skud_id": 7,
                "device_id": "private-device-id",
                "key_name": "Family key",
                "occurred_at": "2026-09-01T00:00:00+00:00",
                "key_id": 77,
                "external_id": "must-not-be-published",
            },
        )
    )

    assert entity.available is True
    assert entity.state_attributes == {
        "event_type": "passage",
        "key_name": "Family key",
        "occurred_at": "2026-09-01T00:00:00+00:00",
    }
    entity.async_write_ha_state.assert_called_once_with()


def test_key_passage_event_ignores_other_intercoms() -> None:
    coordinator = SimpleNamespace(last_update_success=True, data={7: {}})
    entity = UfanetKeyPassageEvent(coordinator, _skud())
    entity.async_write_ha_state = MagicMock()

    entity._async_handle_passage(  # noqa: SLF001
        Event(EVENT_KEY_PASSAGE, {"skud_id": 8, "key_name": "Other"})
    )

    assert entity.state is None
    entity.async_write_ha_state.assert_not_called()


def test_motion_event_keeps_only_coarse_timestamp() -> None:
    coordinator = SimpleNamespace(last_update_success=True, data={7: {}})
    entity = UfanetMotionAnalyticsEvent(coordinator, _skud())
    entity.async_write_ha_state = MagicMock()

    entity._async_handle_motion(  # noqa: SLF001
        Event(
            EVENT_MOTION_ANALYTICS,
            {
                "skud_id": 7,
                "device_id": "ha-device-id",
                "device_name": "Front door",
                "occurred_at": "2026-09-02T10:00:34.793780+00:00",
                "camera_number": "PRIVATE-CAMERA",
                "cursor_id": 918273,
                "media_url": "https://private.invalid/image.jpg",
                "recognition": {"private": True},
            },
        )
    )

    assert entity.available is True
    assert entity.state_attributes == {
        "event_type": "motion",
        "occurred_at": "2026-09-02T10:00:34.793780+00:00",
    }
    entity.async_write_ha_state.assert_called_once_with()


def test_motion_event_ignores_other_intercoms() -> None:
    coordinator = SimpleNamespace(last_update_success=True, data={7: {}})
    entity = UfanetMotionAnalyticsEvent(coordinator, _skud())
    entity.async_write_ha_state = MagicMock()

    entity._async_handle_motion(  # noqa: SLF001
        Event(EVENT_MOTION_ANALYTICS, {"skud_id": 8, "occurred_at": "private"})
    )

    assert entity.state is None
    entity.async_write_ha_state.assert_not_called()


@pytest.mark.asyncio
async def test_motion_entity_is_added_after_coordinator_recovers(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Motion event recovery test",
        data={},
        unique_id="motion-event-recovery-test",
    )
    entry.add_to_hass(hass)

    class AnalyticsCoordinator:
        data = {}
        last_update_success = False
        listener = None

        def async_add_listener(self, listener):
            self.listener = listener
            return lambda: None

    analytics = AnalyticsCoordinator()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": SimpleNamespace(data={7: _skud()}),
        "key_passage_coordinator": SimpleNamespace(data={}),
        "analytics_coordinator": analytics,
    }
    batches = []

    def add_entities(entities) -> None:
        batches.append(list(entities))

    await async_setup_entry(hass, entry, add_entities)

    assert sum(len(batch) for batch in batches) == 0
    assert analytics.listener is not None

    analytics.data = {7: {"supported": True}}
    analytics.last_update_success = True
    analytics.listener()

    motion_entities = [
        entity
        for batch in batches
        for entity in batch
        if isinstance(entity, UfanetMotionAnalyticsEvent)
    ]
    assert len(motion_entities) == 1
    assert motion_entities[0].skud_id == 7

    analytics.listener()
    motion_entities = [
        entity
        for batch in batches
        for entity in batch
        if isinstance(entity, UfanetMotionAnalyticsEvent)
    ]
    assert len(motion_entities) == 1
