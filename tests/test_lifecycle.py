"""Tests for integration setup, unload and event serialization lifecycle."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ufanet_intercom import (
    _call_event_data,
    async_remove_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.ufanet_intercom.api import (
    UfanetAuthError,
    UfanetConnectionError,
)
from custom_components.ufanet_intercom.const import (
    CALL_UPDATE_MODE_FCM,
    CALL_UPDATE_MODE_POLLING,
    CONF_CALL_SCAN_INTERVAL,
    CONF_CALL_UPDATE_MODE,
    CONF_FCM_CONFIG_PATH,
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
    EVENT_KEY_PASSAGE,
    FCM_FALLBACK_SCAN_INTERVAL_SECONDS,
)


def _entry(options: dict | None = None) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="AB123",
        data={CONF_USERNAME: "AB123", CONF_PASSWORD: "secret"},
        options=options or {},
        unique_id="ab123",
    )


def test_call_event_data_keeps_metadata_without_media_urls() -> None:
    result = _call_event_data(
        {
            "uuid": "u1",
            "called_at": "2026-08-28T10:00:00+10:00",
            "timezone": None,
            "camera_number": "CAM",
            "address": "Street",
            "porch": None,
            "flat": "10",
            "preview_url": "https://preview.invalid/x.mp4?token=PRIVATE",
            "archive_url": "https://archive.invalid/x.mp4?token=PRIVATE",
            "ignored": "value",
        }
    )

    assert result == {
        "type": "call",
        "has_preview": True,
        "has_archive": True,
        "uuid": "u1",
        "called_at": "2026-08-28T10:00:00+10:00",
        "camera_number": "CAM",
        "address": "Street",
        "flat": "10",
    }
    assert "preview_url" not in result
    assert "archive_url" not in result


@pytest.mark.asyncio
async def test_setup_entry_maps_auth_failure(hass) -> None:
    entry = _entry()

    with (
        patch("custom_components.ufanet_intercom.async_get_clientsession"),
        patch("custom_components.ufanet_intercom.UfanetApi") as api_cls,
    ):
        api_cls.return_value.async_login = AsyncMock(
            side_effect=UfanetAuthError("bad credentials")
        )
        with pytest.raises(ConfigEntryAuthFailed):
            await async_setup_entry(hass, entry)


@pytest.mark.asyncio
async def test_setup_entry_maps_connection_failure_to_not_ready(hass) -> None:
    entry = _entry()

    with (
        patch("custom_components.ufanet_intercom.async_get_clientsession"),
        patch("custom_components.ufanet_intercom.UfanetApi") as api_cls,
    ):
        api_cls.return_value.async_login = AsyncMock(
            side_effect=UfanetConnectionError("offline")
        )
        with pytest.raises(ConfigEntryNotReady, match="offline"):
            await async_setup_entry(hass, entry)


@pytest.mark.asyncio
async def test_setup_entry_builds_runtime_and_optional_archive(hass) -> None:
    entry = _entry()
    entry.add_to_hass(hass)

    skud = {"id": 7, "cctv_number": "CAM", "custom_name": "Door"}
    api = MagicMock()
    api.async_login = AsyncMock(return_value=None)

    coordinator = MagicMock()
    coordinator.data = {7: skud}
    coordinator.async_config_entry_first_refresh = AsyncMock(return_value=None)

    call_coordinator = MagicMock()
    call_coordinator.data = None
    call_coordinator.new_calls = []
    call_coordinator.async_refresh = AsyncMock(return_value=None)
    call_coordinator.async_add_listener.return_value = lambda: None

    key_passage_coordinator = MagicMock()
    key_passage_coordinator.data = None
    key_passage_coordinator.new_passages = {}
    key_passage_coordinator.async_initialize = AsyncMock()
    key_passage_coordinator.async_refresh = AsyncMock()
    key_passage_coordinator.async_add_listener.return_value = lambda: None

    controller = MagicMock()
    controller.async_initialize = AsyncMock(return_value=None)

    auto_manager = MagicMock()
    auto_manager.enabled = False
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
            "custom_components.ufanet_intercom.UfanetArchiveController",
            return_value=controller,
        ) as archive_cls,
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
            AsyncMock(return_value=None),
        ) as forward,
    ):
        assert await async_setup_entry(hass, entry) is True

    runtime = hass.data[DOMAIN][entry.entry_id]
    assert runtime["api"] is api
    assert runtime["coordinator"] is coordinator
    assert runtime["call_coordinator"] is call_coordinator
    assert runtime["key_passage_coordinator"] is key_passage_coordinator
    assert runtime["archive_controllers"] == {7: controller}
    assert runtime["image_status_manager"] is image_manager
    assert call_coordinator.data == {}
    assert key_passage_coordinator.data == {}
    key_passage_coordinator.async_initialize.assert_awaited_once_with()
    key_passage_coordinator.async_refresh.assert_awaited_once_with()
    controller.async_initialize.assert_awaited_once()
    archive_cls.assert_called_once()
    image_manager.async_initialize.assert_awaited_once()
    forward.assert_awaited_once()

    events = []
    hass.bus.async_listen(EVENT_KEY_PASSAGE, events.append)
    key_passage_coordinator.new_passages = {
        7: [
            {
                "key_name": "Private key name",
                "occurred_at": "2026-09-01T00:00:00+00:00",
                "external_id": "must-not-leak",
            }
        ]
    }
    passage_listener = key_passage_coordinator.async_add_listener.call_args.args[0]
    passage_listener()
    await hass.async_block_till_done()

    assert len(events) == 1
    assert events[0].data == {
        "type": "passage",
        "skud_id": 7,
        "device_name": "Door",
        "key_name": "Private key name",
        "occurred_at": "2026-09-01T00:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_fcm_setup_switches_polling_interval_with_transport_health(
    hass,
) -> None:
    entry = _entry(
        {
            CONF_CALL_UPDATE_MODE: CALL_UPDATE_MODE_FCM,
            CONF_CALL_SCAN_INTERVAL: 12,
            CONF_FCM_CONFIG_PATH: "ufanet_intercom/firebase_config.json",
        }
    )
    entry.add_to_hass(hass)

    api = MagicMock()
    api.async_login = AsyncMock()
    coordinator = MagicMock()
    coordinator.data = {7: {"id": 7, "custom_name": "Door"}}
    coordinator.async_config_entry_first_refresh = AsyncMock()
    call_coordinator = MagicMock()
    call_coordinator.data = {}
    call_coordinator.new_calls = []
    call_coordinator.async_refresh = AsyncMock()
    call_coordinator.async_request_refresh = AsyncMock()
    call_coordinator.async_add_listener.return_value = lambda: None
    key_passage_coordinator = MagicMock()
    key_passage_coordinator.data = {}
    key_passage_coordinator.new_passages = {}
    key_passage_coordinator.async_initialize = AsyncMock()
    key_passage_coordinator.async_refresh = AsyncMock()
    key_passage_coordinator.async_add_listener.return_value = lambda: None
    auto_manager = MagicMock(enabled=False)
    fcm_manager = MagicMock()
    fcm_manager.async_start = AsyncMock(return_value=False)

    with (
        patch("custom_components.ufanet_intercom.async_get_clientsession"),
        patch("custom_components.ufanet_intercom.UfanetApi", return_value=api),
        patch(
            "custom_components.ufanet_intercom.async_load_firebase_config",
            AsyncMock(return_value={"project_id": "example"}),
        ) as load_config,
        patch(
            "custom_components.ufanet_intercom.UfanetCoordinator",
            return_value=coordinator,
        ),
        patch(
            "custom_components.ufanet_intercom.UfanetCallCoordinator",
            return_value=call_coordinator,
        ) as call_cls,
        patch(
            "custom_components.ufanet_intercom.UfanetKeyPassageCoordinator",
            return_value=key_passage_coordinator,
        ),
        patch(
            "custom_components.ufanet_intercom.UfanetCallAutoSaveManager",
            return_value=auto_manager,
        ),
        patch(
            "custom_components.ufanet_intercom.UfanetFcmManager",
            return_value=fcm_manager,
        ) as fcm_cls,
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            AsyncMock(),
        ) as forward,
    ):
        assert await async_setup_entry(hass, entry) is True

    load_config.assert_awaited_once_with(
        hass,
        "ufanet_intercom/firebase_config.json",
    )
    assert call_cls.call_args.kwargs["scan_interval_seconds"] == 12
    forward.assert_awaited_once()
    fcm_cls.assert_called_once()
    fcm_manager.async_start.assert_awaited_once()
    health_callback = fcm_cls.call_args.kwargs["on_health_change"]
    health_callback(True)
    call_coordinator.async_set_scan_interval.assert_called_with(
        FCM_FALLBACK_SCAN_INTERVAL_SECONDS
    )
    health_callback(False)
    call_coordinator.async_set_scan_interval.assert_called_with(12)
    assert hass.data[DOMAIN][entry.entry_id]["fcm_manager"] is fcm_manager


@pytest.mark.asyncio
async def test_unload_removes_runtime_only_after_platform_success(hass) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"sentinel": True}

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        AsyncMock(return_value=False),
    ):
        assert await async_unload_entry(hass, entry) is False
    assert entry.entry_id in hass.data[DOMAIN]

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        AsyncMock(return_value=True),
    ):
        assert await async_unload_entry(hass, entry) is True
    assert entry.entry_id not in hass.data[DOMAIN]


@pytest.mark.asyncio
async def test_unload_stops_fcm_manager(hass) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    fcm_manager = MagicMock()
    fcm_manager.async_stop = AsyncMock()
    image_manager = MagicMock()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "fcm_manager": fcm_manager,
        "image_status_manager": image_manager,
    }

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        AsyncMock(return_value=True),
    ):
        assert await async_unload_entry(hass, entry) is True

    fcm_manager.async_stop.assert_awaited_once()
    image_manager.stop.assert_called_once_with()


@pytest.mark.asyncio
async def test_switching_from_fcm_to_polling_unregisters_after_stop(hass) -> None:
    entry = _entry({CONF_CALL_UPDATE_MODE: CALL_UPDATE_MODE_POLLING})
    entry.add_to_hass(hass)
    fcm_manager = MagicMock()
    fcm_manager.async_stop = AsyncMock()
    fcm_manager.async_unregister = AsyncMock(return_value=True)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "call_update_mode": CALL_UPDATE_MODE_FCM,
        "fcm_manager": fcm_manager,
    }

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        AsyncMock(return_value=True),
    ):
        assert await async_unload_entry(hass, entry) is True

    fcm_manager.async_stop.assert_awaited_once_with()
    fcm_manager.async_unregister.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_normal_fcm_reload_keeps_remote_registration(hass) -> None:
    entry = _entry({CONF_CALL_UPDATE_MODE: CALL_UPDATE_MODE_FCM})
    entry.add_to_hass(hass)
    fcm_manager = MagicMock()
    fcm_manager.async_stop = AsyncMock()
    fcm_manager.async_unregister = AsyncMock()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "call_update_mode": CALL_UPDATE_MODE_FCM,
        "fcm_manager": fcm_manager,
    }

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        AsyncMock(return_value=True),
    ):
        assert await async_unload_entry(hass, entry) is True

    fcm_manager.async_stop.assert_awaited_once_with()
    fcm_manager.async_unregister.assert_not_awaited()


@pytest.mark.asyncio
async def test_remove_entry_runs_best_effort_fcm_cleanup(hass) -> None:
    entry = _entry()

    with (
        patch("custom_components.ufanet_intercom.async_get_clientsession"),
        patch("custom_components.ufanet_intercom.UfanetApi") as api_cls,
        patch(
            "custom_components.ufanet_intercom.async_remove_stored_fcm_registration",
            AsyncMock(),
        ) as cleanup,
    ):
        await async_remove_entry(hass, entry)

    cleanup.assert_awaited_once_with(hass, entry, api_cls.return_value)
