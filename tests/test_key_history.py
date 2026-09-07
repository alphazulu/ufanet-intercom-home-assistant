"""Tests for privacy-safe per-key physical-key passage history."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ufanet_intercom.const import DOMAIN
from custom_components.ufanet_intercom.key_history import (
    SERVICE_GET_PHYSICAL_KEY_PASSAGES,
    _parse_filtered_passage_response,
    async_setup_key_history,
)
from custom_components.ufanet_intercom.key_management import physical_key_ref

SKUD_ID = 154273
KEY_ID = 41


def _install_runtime(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Physical key history",
        data={"username": "ACCOUNT"},
        unique_id="physical-key-history",
    )
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, str(SKUD_ID))},
        name="Door",
    )

    api = MagicMock()
    api._async_ufanet_json = AsyncMock()
    api.physical_key_inventory = (
        {
            "key_id": KEY_ID,
            "name": "Visible key name",
            "created_at": 1_700_000_000,
            "devices": (SKUD_ID,),
        },
    )
    coordinator = SimpleNamespace(
        data={SKUD_ID: {"key_count": 1, "history_healthy": False}},
        last_update_success=True,
        async_request_refresh=AsyncMock(),
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "entry": entry,
        "coordinator": SimpleNamespace(
            data={SKUD_ID: {"id": SKUD_ID, "cctv_number": "CAM"}}
        ),
        "key_passage_coordinator": coordinator,
        "options": {},
    }

    async_setup_key_history(hass)
    return entry, device, api, coordinator


def test_filtered_passage_parser_accepts_numeric_strings_and_hides_raw_fields() -> None:
    payload = {
        "count": "1",
        "current_page": "0",
        "page_count": "0",
        "page_size": "25",
        "results": [
            {
                "key": "41",
                "key_name": "PRIVATE-PASSAGE-NAME",
                "time_passage": "1700000100",
                "future_field": {"secret": "ignored"},
            }
        ],
    }

    result = _parse_filtered_passage_response(
        payload,
        expected_key_id=KEY_ID,
        requested_page=0,
    )

    assert result == {
        "page": 0,
        "page_size": 25,
        "total": 1,
        "has_more": False,
        "passages": [{"occurred_at": "2023-11-14T22:15:00+00:00"}],
    }
    serialized = json.dumps(result)
    assert "PRIVATE-PASSAGE-NAME" not in serialized
    assert "future_field" not in serialized
    assert "key_id" not in serialized


def test_filtered_passage_parser_rejects_result_for_another_key() -> None:
    with pytest.raises(ValueError, match="filter was not respected"):
        _parse_filtered_passage_response(
            {
                "count": 1,
                "current_page": 0,
                "page_count": 0,
                "page_size": 25,
                "results": [
                    {
                        "key": KEY_ID + 1,
                        "key_name": "Wrong key",
                        "time_passage": 1_700_000_100,
                    }
                ],
            },
            expected_key_id=KEY_ID,
            requested_page=0,
        )


@pytest.mark.asyncio
async def test_service_resolves_opaque_ref_and_uses_android_single_key_filter(hass) -> None:
    entry, device, api, coordinator = _install_runtime(hass)
    key_ref = physical_key_ref(entry.entry_id, SKUD_ID, KEY_ID)
    api._async_ufanet_json.return_value = {
        "count": 1,
        "current_page": 0,
        "page_count": 0,
        "page_size": 25,
        "results": [
            {
                "key": KEY_ID,
                "key_name": "PRIVATE-PASSAGE-NAME",
                "time_passage": 1_700_000_100,
            }
        ],
    }

    result = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_PHYSICAL_KEY_PASSAGES,
        {
            "device_id": device.id,
            "key_ref": key_ref,
            "page": 0,
        },
        blocking=True,
        return_response=True,
    )

    coordinator.async_request_refresh.assert_awaited_once()
    api._async_ufanet_json.assert_awaited_once_with(
        "POST",
        f"/api/v4/key/skud/{SKUD_ID}/key/pass_history/",
        json_body={
            "page": 0,
            "page_size": 25,
            "filters": {"key": str(KEY_ID)},
        },
    )
    assert result["device_id"] == device.id
    assert result["key_ref"] == key_ref
    assert result["name"] == "Visible key name"
    assert result["passages"] == [
        {"occurred_at": "2023-11-14T22:15:00+00:00"}
    ]
    serialized = json.dumps(result)
    assert "PRIVATE-PASSAGE-NAME" not in serialized
    assert '"key_id"' not in serialized
    assert '"external_id"' not in serialized


@pytest.mark.asyncio
async def test_service_fails_closed_if_provider_filter_returns_another_key(hass) -> None:
    entry, device, api, _coordinator = _install_runtime(hass)
    key_ref = physical_key_ref(entry.entry_id, SKUD_ID, KEY_ID)
    api._async_ufanet_json.return_value = {
        "count": 1,
        "current_page": 0,
        "page_count": 0,
        "page_size": 25,
        "results": [
            {
                "key": KEY_ID + 1,
                "key_name": "Another key",
                "time_passage": 1_700_000_100,
            }
        ],
    }

    with pytest.raises(HomeAssistantError, match="unexpected schema"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_PHYSICAL_KEY_PASSAGES,
            {
                "device_id": device.id,
                "key_ref": key_ref,
                "page": 0,
            },
            blocking=True,
            return_response=True,
        )
