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
from custom_components.ufanet_intercom.fcm import (
    UfanetFcmManager,
    async_remove_stored_fcm_registration,
    async_retry_pending_fcm_unregister,
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


@pytest.mark.asyncio
async def test_fcm_recovers_invalid_private_state_and_reports_reason(hass) -> None:
    store = MagicMock()
    store.async_load = AsyncMock(return_value={"ufanet_device_id": 12345})
    store.async_save = AsyncMock()
    client = MagicMock()
    client.checkin_or_register = AsyncMock(return_value="token")
    client.start = AsyncMock()
    client.stop = AsyncMock()
    client.run_state = SimpleNamespace(name="STARTED")
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
    ):
        manager = UfanetFcmManager(
            hass,
            entry,
            api,
            FIREBASE_CONFIG,
            AsyncMock(),
        )
        assert await manager.async_start() is True

        status = manager.status()
        assert status["state_recovered"] is True
        assert status["state_recovery_reason"] == "invalid_schema"
        assert isinstance(manager._state["ufanet_device_id"], str)  # noqa: SLF001
        assert manager._state["ufanet_device_id"] != "12345"  # noqa: SLF001
        issue_id = f"fcm_state_recovered_{entry.entry_id}"
        assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None
        assert "12345" not in str(status)

        await manager.async_stop()


@pytest.mark.asyncio
async def test_fcm_clean_state_clears_previous_recovery_issue(hass) -> None:
    entry = _entry()
    issue_id = f"fcm_state_recovered_{entry.entry_id}"
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="fcm_state_recovered",
        translation_placeholders={"entry_title": "test"},
    )
    store = MagicMock()
    store.async_load = AsyncMock(
        return_value={
            "fcm_credentials": None,
            "persistent_ids": [],
            "ufanet_device_id": "Home Assistant_00000000-0000-4000-8000-000000000001",
            "ufanet_device_title": "Home Assistant",
            "firebase_config_fingerprint": None,
        }
    )
    store.async_save = AsyncMock()
    client = MagicMock()
    client.checkin_or_register = AsyncMock(return_value="token")
    client.start = AsyncMock()
    client.stop = AsyncMock()
    client.run_state = SimpleNamespace(name="STARTED")
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
            entry,
            api,
            FIREBASE_CONFIG,
            AsyncMock(),
        )
        assert await manager.async_start() is True
        assert manager.status()["state_recovered"] is False
        assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None

        await manager.async_stop()


@pytest.mark.asyncio
async def test_fcm_unregister_removes_only_owned_state(hass) -> None:
    store = MagicMock()
    store.async_save = AsyncMock()
    store.async_remove = AsyncMock()
    api = MagicMock()
    api.async_unregister_fcm_device = AsyncMock()
    entry = _entry()

    with patch("custom_components.ufanet_intercom.fcm.Store", return_value=store):
        manager = UfanetFcmManager(
            hass,
            entry,
            api,
            FIREBASE_CONFIG,
            AsyncMock(),
        )
        manager._state = {  # noqa: SLF001
            "ufanet_device_id": (
                "Home Assistant_00000000-0000-4000-8000-000000000002"
            ),
            "unregister_pending": False,
        }

        assert await manager.async_unregister() is True

    api.async_unregister_fcm_device.assert_awaited_once_with(
        device_id="Home Assistant_00000000-0000-4000-8000-000000000002"
    )
    store.async_remove.assert_awaited_once_with()
    assert manager.status()["unregister_pending"] is False
    assert manager.status()["last_unregistration_succeeded"] is True


@pytest.mark.asyncio
async def test_fcm_unregister_failure_keeps_state_for_retry_and_opens_repair(
    hass,
) -> None:
    store = MagicMock()
    store.async_save = AsyncMock()
    store.async_remove = AsyncMock()
    api = MagicMock()
    api.async_unregister_fcm_device = AsyncMock(side_effect=RuntimeError("offline"))
    entry = _entry()

    with patch("custom_components.ufanet_intercom.fcm.Store", return_value=store):
        manager = UfanetFcmManager(
            hass,
            entry,
            api,
            FIREBASE_CONFIG,
            AsyncMock(),
        )
        manager._state = {  # noqa: SLF001
            "ufanet_device_id": (
                "Home Assistant_00000000-0000-4000-8000-000000000003"
            ),
            "unregister_pending": False,
        }

        assert await manager.async_unregister() is False

    store.async_remove.assert_not_awaited()
    assert manager.status()["unregister_pending"] is True
    assert manager.status()["last_unregistration_succeeded"] is False
    assert manager.status()["last_unregistration_error_type"] == "RuntimeError"
    issue_id = f"fcm_unregister_failed_{entry.entry_id}"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None


@pytest.mark.asyncio
async def test_pending_fcm_unregister_is_retried_and_local_state_removed(hass) -> None:
    store = MagicMock()
    store.async_load = AsyncMock(
        return_value={
            "ufanet_device_id": (
                "Home Assistant_00000000-0000-4000-8000-000000000004"
            ),
            "unregister_pending": True,
        }
    )
    store.async_remove = AsyncMock()
    api = MagicMock()
    api.async_unregister_fcm_device = AsyncMock()
    entry = _entry()

    with patch("custom_components.ufanet_intercom.fcm.Store", return_value=store):
        assert await async_retry_pending_fcm_unregister(hass, entry, api) is False

    api.async_unregister_fcm_device.assert_awaited_once_with(
        device_id="Home Assistant_00000000-0000-4000-8000-000000000004"
    )
    store.async_remove.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_entry_removal_never_unregisters_unowned_device_id(hass) -> None:
    store = MagicMock()
    store.async_load = AsyncMock(
        return_value={
            "ufanet_device_id": "untrusted-device-id",
            "unregister_pending": True,
        }
    )
    store.async_remove = AsyncMock()
    api = MagicMock()
    api.async_unregister_fcm_device = AsyncMock()
    entry = _entry()

    with patch("custom_components.ufanet_intercom.fcm.Store", return_value=store):
        await async_remove_stored_fcm_registration(hass, entry, api)

    api.async_unregister_fcm_device.assert_not_awaited()
    store.async_remove.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_entry_removal_unregisters_owned_device_before_local_cleanup(hass) -> None:
    store = MagicMock()
    store.async_load = AsyncMock(
        return_value={
            "ufanet_device_id": (
                "Home Assistant_00000000-0000-4000-8000-000000000005"
            )
        }
    )
    store.async_remove = AsyncMock()
    api = MagicMock()
    api.async_unregister_fcm_device = AsyncMock()
    entry = _entry()

    with patch("custom_components.ufanet_intercom.fcm.Store", return_value=store):
        await async_remove_stored_fcm_registration(hass, entry, api)

    api.async_unregister_fcm_device.assert_awaited_once_with(
        device_id="Home Assistant_00000000-0000-4000-8000-000000000005"
    )
    store.async_remove.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_firebase_identity_change_reuses_owned_ufanet_device_id(hass) -> None:
    owned_device_id = "Home Assistant_00000000-0000-4000-8000-000000000006"
    store = MagicMock()
    store.async_load = AsyncMock(
        return_value={
            "fcm_credentials": {"private": "credential"},
            "persistent_ids": ["persistent"],
            "ufanet_device_id": owned_device_id,
            "ufanet_device_title": "Home Assistant",
            "firebase_config_fingerprint": "different-fingerprint",
            "unregister_pending": False,
        }
    )
    store.async_save = AsyncMock()
    client = MagicMock()
    client.checkin_or_register = AsyncMock(return_value="new-token")
    client.start = AsyncMock()
    client.stop = AsyncMock()
    client.run_state = SimpleNamespace(name="STARTED")
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
        assert await manager.async_start() is True

        api.async_register_fcm_device.assert_awaited_once_with(
            token="new-token",
            device_id=owned_device_id,
            title="Home Assistant",
            application=FIREBASE_CONFIG["package_name"],
        )
        assert manager.status()["state_recovery_reason"] == (
            "firebase_identity_changed"
        )

        await manager.async_stop()


@pytest.mark.asyncio
async def test_fcm_authorized_device_verification_is_privacy_safe(hass) -> None:
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
    api.async_get_fcm_authorization_status = AsyncMock(
        return_value={
            "call_access": True,
            "last_update": "2000-01-01T00:00:00Z",
        }
    )

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
        assert await manager.async_start() is True

        status = manager.status()
        owned_device_id = manager._state["ufanet_device_id"]  # noqa: SLF001
        assert status["authorized_device_check_succeeded"] is True
        assert status["authorized_device_registered"] is True
        assert status["authorized_device_call_access"] is True
        assert status["authorized_device_last_update_age"] == "gt_90d"
        assert status["authorized_device_check_error_type"] is None
        assert owned_device_id not in str(status)
        assert "2000-01-01T00:00:00Z" not in str(status)
        api.async_get_fcm_authorization_status.assert_awaited_once_with(
            device_id=owned_device_id
        )

        await manager.async_stop()


@pytest.mark.asyncio
async def test_fcm_authorized_device_verification_failure_is_non_fatal(hass) -> None:
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
    api.async_get_fcm_authorization_status = AsyncMock(
        side_effect=RuntimeError("private provider response")
    )

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
        assert await manager.async_start() is True
        status = manager.status()
        assert status["active"] is True
        assert status["authorized_device_check_succeeded"] is False
        assert status["authorized_device_registered"] is None
        assert status["authorized_device_call_access"] is None
        assert status["authorized_device_last_update_age"] is None
        assert status["authorized_device_check_error_type"] == "RuntimeError"
        assert "private provider response" not in str(status)
        await manager.async_stop()


@pytest.mark.asyncio
async def test_fcm_authorization_check_runs_after_listener_start(hass) -> None:
    order: list[str] = []
    store = MagicMock()
    store.async_load = AsyncMock(return_value=None)
    store.async_save = AsyncMock()
    client = MagicMock()
    client.checkin_or_register = AsyncMock(return_value="fcm-token")

    async def start_listener() -> None:
        order.append("listener_start")

    async def verify_registration(**_kwargs) -> dict[str, object]:
        order.append("authorization_check")
        return {
            "call_access": True,
            "last_update": "2026-09-02T12:34:56Z",
        }

    client.start = AsyncMock(side_effect=start_listener)
    client.stop = AsyncMock()
    client.run_state = SimpleNamespace(name="RUNNING")
    api = MagicMock()
    api.async_register_fcm_device = AsyncMock()
    api.async_get_fcm_authorization_status = AsyncMock(
        side_effect=verify_registration
    )

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
        assert await manager.async_start() is True
        assert order == ["listener_start", "authorization_check"]
        await manager.async_stop()
