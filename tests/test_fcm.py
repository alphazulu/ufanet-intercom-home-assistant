"""Tests for the optional headless FCM manager."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
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

    status = manager.status()
    assert status["last_error_type"] == "RuntimeError"
    assert status["firebase_registration_succeeded"] is False
    assert status["ufanet_registration_succeeded"] is False
    assert status["listener_started"] is False
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
