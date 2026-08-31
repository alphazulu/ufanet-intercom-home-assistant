"""Tests for the optional headless FCM manager."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ufanet_intercom.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.ufanet_intercom.fcm import UfanetFcmManager


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


@pytest.mark.asyncio
async def test_fcm_start_registers_and_sip_push_refreshes(hass) -> None:
    store = MagicMock()
    store.async_load = AsyncMock(return_value=None)
    store.async_save = AsyncMock()
    client = MagicMock()
    client.checkin_or_register = AsyncMock(return_value="fcm-token")
    client.start = AsyncMock()
    client.stop = AsyncMock()
    client.run_state = SimpleNamespace(name="RUNNING")
    api = MagicMock()
    api.async_register_fcm_device = AsyncMock()
    refresh = AsyncMock()

    with (
        patch("custom_components.ufanet_intercom.fcm.Store", return_value=store),
        patch(
            "custom_components.ufanet_intercom.fcm.FcmPushClient",
            return_value=client,
        ) as client_cls,
        patch("custom_components.ufanet_intercom.fcm.FcmRegisterConfig") as config_cls,
        patch("custom_components.ufanet_intercom.fcm.async_get_clientsession"),
        patch(
            "custom_components.ufanet_intercom.fcm.SIP_REFRESH_DELAYS_SECONDS",
            (0, 0, 0),
        ),
    ):
        manager = UfanetFcmManager(
            hass,
            _entry(),
            api,
            FIREBASE_CONFIG,
            refresh,
        )
        assert await manager.async_start() is True

        callback = client_cls.call_args.args[0]
        callback(
            {
                "data": {
                    "reason": "sip",
                    "username": "must-not-appear-in-status",
                }
            },
            "persistent-1",
            None,
        )
        await hass.async_block_till_done()

        status = manager.status()
        assert status["active"] is True
        assert status["firebase_registration_succeeded"] is True
        assert status["ufanet_registration_succeeded"] is True
        assert status["listener_started"] is True
        assert status["listener_running"] is True
        assert status["fallback_polling_active"] is False
        assert status["watchdog_running"] is True
        assert status["transport_state"] == "RUNNING"
        assert status["received_push_count"] == 1
        assert status["received_sip_push_count"] == 1
        assert "must-not-appear" not in str(status)
        assert refresh.await_count == 3
        api.async_register_fcm_device.assert_awaited_once_with(
            token="fcm-token",
            device_id=manager._state["ufanet_device_id"],  # noqa: SLF001
            title="Home Assistant",
            application=FIREBASE_CONFIG["package_name"],
        )
        config_cls.assert_called_once_with(
            project_id=FIREBASE_CONFIG["project_id"],
            app_id=FIREBASE_CONFIG["app_id"],
            api_key=FIREBASE_CONFIG["api_key"],
            messaging_sender_id=FIREBASE_CONFIG["sender_id"],
            bundle_id=FIREBASE_CONFIG["package_name"],
            persistend_ids=[],
        )

        await manager.async_stop()

    client.stop.assert_awaited_once()
    assert manager.active is False
    assert manager.listener_started is False
    assert store.async_save.await_count >= 1


@pytest.mark.asyncio
async def test_fcm_start_failure_is_non_fatal(hass) -> None:
    store = MagicMock()
    store.async_load = AsyncMock(return_value=None)
    store.async_save = AsyncMock()
    client = MagicMock()
    client.checkin_or_register = AsyncMock(side_effect=RuntimeError("offline"))
    client.stop = AsyncMock()
    api = MagicMock()
    api.async_register_fcm_device = AsyncMock()

    with (
        patch("custom_components.ufanet_intercom.fcm.Store", return_value=store),
        patch(
            "custom_components.ufanet_intercom.fcm.FcmPushClient",
            return_value=client,
        ),
        patch("custom_components.ufanet_intercom.fcm.FcmRegisterConfig"),
        patch("custom_components.ufanet_intercom.fcm.async_get_clientsession"),
    ):
        manager = UfanetFcmManager(
            hass,
            _entry(),
            api,
            FIREBASE_CONFIG,
            AsyncMock(),
        )
        assert await manager.async_start() is False

        await manager.async_stop()

    status = manager.status()
    assert status["last_error_type"] == "RuntimeError"
    assert status["firebase_registration_succeeded"] is False
    assert status["ufanet_registration_succeeded"] is False
    assert status["listener_started"] is False
    assert status["listener_running"] is False
    assert manager.active is False
    client.stop.assert_awaited_once()
    api.async_register_fcm_device.assert_not_awaited()


@pytest.mark.parametrize(
    ("ufanet_error", "listener_error", "expected"),
    [
        (RuntimeError("rejected"), None, (True, False, False)),
        (None, RuntimeError("listener failed"), (True, True, False)),
    ],
)
@pytest.mark.asyncio
async def test_fcm_status_identifies_failed_startup_stage(
    hass,
    ufanet_error: Exception | None,
    listener_error: Exception | None,
    expected: tuple[bool, bool, bool],
) -> None:
    store = MagicMock()
    store.async_load = AsyncMock(return_value=None)
    store.async_save = AsyncMock()
    client = MagicMock()
    client.checkin_or_register = AsyncMock(return_value="fcm-token")
    client.start = AsyncMock(side_effect=listener_error)
    client.stop = AsyncMock()
    api = MagicMock()
    api.async_register_fcm_device = AsyncMock(side_effect=ufanet_error)

    with (
        patch("custom_components.ufanet_intercom.fcm.Store", return_value=store),
        patch(
            "custom_components.ufanet_intercom.fcm.FcmPushClient",
            return_value=client,
        ),
        patch("custom_components.ufanet_intercom.fcm.FcmRegisterConfig"),
        patch("custom_components.ufanet_intercom.fcm.async_get_clientsession"),
    ):
        manager = UfanetFcmManager(
            hass,
            _entry(),
            api,
            FIREBASE_CONFIG,
            AsyncMock(),
        )
        assert await manager.async_start() is False

        await manager.async_stop()

    status = manager.status()
    assert (
        status["firebase_registration_succeeded"],
        status["ufanet_registration_succeeded"],
        status["listener_started"],
    ) == expected
    assert status["active"] is False
    client.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_fcm_stop_cancels_pending_sip_refresh(hass) -> None:
    store = MagicMock()
    store.async_load = AsyncMock(return_value=None)
    store.async_save = AsyncMock()
    client = MagicMock()
    client.checkin_or_register = AsyncMock(return_value="token")
    client.start = AsyncMock()
    client.stop = AsyncMock()
    api = MagicMock()
    api.async_register_fcm_device = AsyncMock()
    refresh_started = asyncio.Event()

    async def refresh() -> None:
        refresh_started.set()

    with (
        patch("custom_components.ufanet_intercom.fcm.Store", return_value=store),
        patch(
            "custom_components.ufanet_intercom.fcm.FcmPushClient",
            return_value=client,
        ) as client_cls,
        patch("custom_components.ufanet_intercom.fcm.FcmRegisterConfig"),
        patch("custom_components.ufanet_intercom.fcm.async_get_clientsession"),
        patch(
            "custom_components.ufanet_intercom.fcm.SIP_REFRESH_DELAYS_SECONDS",
            (0, 60),
        ),
    ):
        manager = UfanetFcmManager(
            hass,
            _entry(),
            api,
            FIREBASE_CONFIG,
            refresh,
        )
        assert await manager.async_start() is True
        callback = client_cls.call_args.args[0]
        callback({"data": {"reason": "sip"}}, "persistent-1", None)
        await refresh_started.wait()
        await manager.async_stop()

    assert not manager._sip_tasks  # noqa: SLF001


@pytest.mark.asyncio
async def test_fcm_watchdog_tracks_transport_and_polling_fallback(hass) -> None:
    store = MagicMock()
    store.async_load = AsyncMock(return_value=None)
    store.async_save = AsyncMock()
    client = MagicMock()
    client.checkin_or_register = AsyncMock(return_value="token")
    client.start = AsyncMock()
    client.stop = AsyncMock()
    client.run_state = SimpleNamespace(name="STARTING_TASKS")
    api = MagicMock()
    api.async_register_fcm_device = AsyncMock()
    health_changes = MagicMock()

    with (
        patch("custom_components.ufanet_intercom.fcm.Store", return_value=store),
        patch(
            "custom_components.ufanet_intercom.fcm.FcmPushClient",
            return_value=client,
        ),
        patch("custom_components.ufanet_intercom.fcm.FcmRegisterConfig"),
        patch("custom_components.ufanet_intercom.fcm.async_get_clientsession"),
    ):
        manager = UfanetFcmManager(
            hass,
            _entry(),
            api,
            FIREBASE_CONFIG,
            AsyncMock(),
            on_health_change=health_changes,
        )
        assert await manager.async_start() is True
        assert manager.status()["fallback_polling_active"] is True
        health_changes.assert_not_called()

        client.run_state = SimpleNamespace(name="STARTED")
        await manager._async_watchdog_iteration()  # noqa: SLF001
        assert manager.status()["listener_running"] is True
        assert manager.status()["last_connected_at"] is not None
        health_changes.assert_called_once_with(True)

        client.run_state = SimpleNamespace(name="RESETTING")
        await manager._async_watchdog_iteration()  # noqa: SLF001
        assert manager.status()["listener_running"] is False
        assert manager.status()["fallback_polling_active"] is True
        assert manager.status()["last_disconnected_at"] is not None
        assert health_changes.call_args_list[-1].args == (False,)
        assert client.stop.await_count == 0

        await manager.async_stop()


@pytest.mark.asyncio
async def test_fcm_watchdog_restarts_terminal_client_and_counts_reconnect(hass) -> None:
    store = MagicMock()
    store.async_load = AsyncMock(return_value=None)
    store.async_save = AsyncMock()
    first = MagicMock()
    first.checkin_or_register = AsyncMock(return_value="token-1")
    first.start = AsyncMock()
    first.stop = AsyncMock()
    first.run_state = SimpleNamespace(name="STARTED")
    replacement = MagicMock()
    replacement.checkin_or_register = AsyncMock(return_value="token-2")
    replacement.start = AsyncMock()
    replacement.stop = AsyncMock()
    replacement.run_state = SimpleNamespace(name="STARTING_TASKS")
    api = MagicMock()
    api.async_register_fcm_device = AsyncMock()
    health_changes = MagicMock()

    with (
        patch("custom_components.ufanet_intercom.fcm.Store", return_value=store),
        patch(
            "custom_components.ufanet_intercom.fcm.FcmPushClient",
            side_effect=(first, replacement),
        ) as client_cls,
        patch("custom_components.ufanet_intercom.fcm.FcmRegisterConfig"),
        patch("custom_components.ufanet_intercom.fcm.async_get_clientsession"),
        patch("custom_components.ufanet_intercom.fcm.FCM_RESTART_BASE_SECONDS", 0),
    ):
        manager = UfanetFcmManager(
            hass,
            _entry(),
            api,
            FIREBASE_CONFIG,
            AsyncMock(),
            on_health_change=health_changes,
        )
        assert await manager.async_start() is True
        first.run_state = SimpleNamespace(name="STOPPED")

        await manager._async_watchdog_iteration()  # noqa: SLF001

        assert client_cls.call_count == 2
        first.stop.assert_awaited_once()
        assert manager.status()["listener_running"] is False
        replacement.run_state = SimpleNamespace(name="STARTED")
        await manager._async_watchdog_iteration()  # noqa: SLF001
        assert manager.status()["listener_running"] is True
        assert manager.status()["reconnect_count"] == 1
        assert manager.status()["consecutive_failures"] == 0
        assert [call.args for call in health_changes.call_args_list] == [
            (True,),
            (False,),
            (True,),
        ]

        await manager.async_stop()


@pytest.mark.asyncio
async def test_fcm_watchdog_opens_and_closes_repair_issue(hass) -> None:
    store = MagicMock()
    store.async_load = AsyncMock(return_value=None)
    store.async_save = AsyncMock()
    client = MagicMock()
    client.checkin_or_register = AsyncMock(return_value="token")
    client.start = AsyncMock()
    client.stop = AsyncMock()
    client.run_state = SimpleNamespace(name="STARTING_TASKS")
    api = MagicMock()
    api.async_register_fcm_device = AsyncMock()
    entry = _entry()

    with (
        patch("custom_components.ufanet_intercom.fcm.Store", return_value=store),
        patch(
            "custom_components.ufanet_intercom.fcm.FcmPushClient",
            return_value=client,
        ),
        patch("custom_components.ufanet_intercom.fcm.FcmRegisterConfig"),
        patch("custom_components.ufanet_intercom.fcm.async_get_clientsession"),
        patch("custom_components.ufanet_intercom.fcm.FCM_REPAIR_AFTER_SECONDS", 0),
    ):
        manager = UfanetFcmManager(
            hass,
            entry,
            api,
            FIREBASE_CONFIG,
            AsyncMock(),
        )
        assert await manager.async_start() is True
        await manager._async_watchdog_iteration()  # noqa: SLF001

        issue_id = f"fcm_listener_unavailable_{entry.entry_id}"
        registry = ir.async_get(hass)
        assert registry.async_get_issue(DOMAIN, issue_id) is not None

        client.run_state = SimpleNamespace(name="STARTED")
        await manager._async_watchdog_iteration()  # noqa: SLF001
        assert registry.async_get_issue(DOMAIN, issue_id) is None

        await manager.async_stop()
