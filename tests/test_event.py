"""Tests for privacy-safe physical-key EventEntity state."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from homeassistant.core import Event

from custom_components.ufanet_intercom.const import EVENT_KEY_PASSAGE
from custom_components.ufanet_intercom.event import UfanetKeyPassageEvent


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
