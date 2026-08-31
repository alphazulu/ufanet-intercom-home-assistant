"""Tests for privacy-preserving diagnostics."""

from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ufanet_intercom.const import (
    CALL_UPDATE_MODE_FCM,
    CONF_CALL_UPDATE_MODE,
    CONF_FCM_CONFIG_PATH,
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.ufanet_intercom.diagnostics import (
    _coordinator_state,
    _export_stats,
    _hash_identifier,
    _safe_camera,
    _safe_skud,
    async_get_config_entry_diagnostics,
    async_get_device_diagnostics,
)


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="AB123",
        data={CONF_USERNAME: "AB123", CONF_PASSWORD: "top-secret"},
        options={
            CONF_CALL_UPDATE_MODE: CALL_UPDATE_MODE_FCM,
            CONF_FCM_CONFIG_PATH: "private/secret-firebase-config.json",
        },
        unique_id="ab123",
    )


def _skud() -> dict:
    return {
        "id": 7,
        "role": "Домофон",
        "model": 39,
        "scope": "owner",
        "private_status": 1,
        "open_type": "http",
        "open_in_talk": True,
        "is_blocked": False,
        "_is_shared": False,
        "relays": [{"id": 1}],
        "cctv_number": "CAMERA-SECRET-123",
        "address": "Private street 1",
        "custom_name": "Private name",
    }


def test_hash_identifier_is_stable_and_non_reversible_reference() -> None:
    assert _hash_identifier(None) is None
    assert _hash_identifier("") is None
    value = _hash_identifier("camera-123")
    assert value == _hash_identifier("camera-123")
    assert value != "camera-123"
    assert len(value) == 12


def test_safe_skud_removes_address_and_raw_camera_identifier() -> None:
    safe = _safe_skud(_skud())
    serialized = json.dumps(safe, ensure_ascii=False)

    assert safe["skud_id"] == 7
    assert safe["relay_count"] == 1
    assert safe["has_camera"] is True
    assert safe["camera_reference"] != "CAMERA-SECRET-123"
    assert "CAMERA-SECRET-123" not in serialized
    assert "Private street" not in serialized
    assert "Private name" not in serialized


def test_safe_camera_reports_capabilities_without_tokens() -> None:
    camera = {
        "timezone": "Asia/Vladivostok",
        "is_llhls_enabled": True,
        "streams_count": 2,
        "token_l": "LIVE-SECRET",
        "token_r": "ARCHIVE-SECRET",
        "server": {
            "vendor_name": "UMS",
            "domain": "media.example",
            "screenshot_domain": "screen.example",
        },
        "tariff": {"name": "Archive", "dvr_hours": 120},
    }

    safe = _safe_camera(camera)
    serialized = json.dumps(safe)

    assert safe["live_token_present"] is True
    assert safe["archive_token_present"] is True
    assert "LIVE-SECRET" not in serialized
    assert "ARCHIVE-SECRET" not in serialized
    assert _safe_camera(None) is None


def test_coordinator_state_exposes_error_type_only() -> None:
    coordinator = SimpleNamespace(
        update_interval=timedelta(seconds=30),
        last_exception=RuntimeError("sensitive cloud text"),
        last_update_success=False,
    )

    state = _coordinator_state(coordinator)

    assert state == {
        "present": True,
        "last_update_success": False,
        "last_exception_type": "RuntimeError",
        "update_interval_seconds": 30.0,
    }
    assert "sensitive" not in json.dumps(state)
    assert _coordinator_state(None) == {"present": False}


def test_export_stats_returns_counts_only(tmp_path: Path) -> None:
    hass = MagicMock()
    hass.config.media_dirs = {"local": str(tmp_path)}
    export_dir = tmp_path / "ufanet_intercom"
    export_dir.mkdir()
    (export_dir / "ufanet_CAM_2026-08-28_10-00-00_60s.mp4").write_bytes(b"1234")
    (export_dir / "ufanet_OTHER_2026-08-28_10-00-00_60s.mp4").write_bytes(b"123456")
    (export_dir / ".ufanet_CAM_partial.mp4").write_bytes(b"x")

    assert _export_stats(hass, "CAM") == {"count": 1, "total_bytes": 4}


@pytest.mark.asyncio
async def test_config_entry_diagnostics_redacts_credentials_and_private_fields(hass) -> None:
    entry = _entry()
    entry.add_to_hass(hass)

    coordinator = SimpleNamespace(
        data={7: _skud()},
        update_interval=timedelta(seconds=300),
        last_exception=None,
        last_update_success=True,
    )
    call_coordinator = SimpleNamespace(
        data={"CAMERA-SECRET-123": {"uuid": "call-secret"}},
        new_calls=[{"uuid": "new-secret"}],
        update_interval=timedelta(seconds=10),
        last_exception=None,
        last_update_success=True,
    )
    api = MagicMock()
    api.diagnostic_auth_state.return_value = {
        "ufanet_access_present": True,
        "ucams_access_present": True,
    }
    auto_save = MagicMock()
    auto_save.status.return_value = {
        "enabled": True,
        "pending_count": 1,
        "last_error_type": None,
    }
    image_status = MagicMock()
    image_status.summary.return_value = {
        "configured": True,
        "ffmpeg_available": True,
        "camera_count": 1,
        "ready_count": 1,
        "last_error_code": None,
        "last_error_type": None,
    }

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "call_coordinator": call_coordinator,
        "archive_controllers": {},
        "auto_save_manager": auto_save,
        "image_status_manager": image_status,
        "call_update_mode": CALL_UPDATE_MODE_FCM,
        "fcm_config_error_type": "UfanetFirebaseConfigError",
    }

    result = await async_get_config_entry_diagnostics(hass, entry)
    serialized = json.dumps(result, ensure_ascii=False)

    assert "top-secret" not in serialized
    assert '"AB123"' not in serialized
    assert "CAMERA-SECRET-123" not in serialized
    assert "Private street" not in serialized
    assert "call-secret" not in serialized
    assert "secret-firebase-config" not in serialized
    assert result["config_entry"]["options"]["fcm_config_path_set"] is True
    assert result["call_updates"]["fcm"]["configured"] is False
    assert (
        result["call_updates"]["fcm"]["firebase_registration_succeeded"]
        is False
    )
    assert result["call_updates"]["fcm"]["ufanet_registration_succeeded"] is False
    assert result["call_updates"]["fcm"]["listener_started"] is False
    assert result["call_updates"]["fcm"]["listener_running"] is False
    assert result["call_updates"]["fcm"]["fallback_polling_active"] is True
    assert result["call_updates"]["fcm"]["watchdog_running"] is False
    assert result["call_updates"]["fcm"]["last_error_type"] == (
        "UfanetFirebaseConfigError"
    )
    assert result["coordinator"]["intercom_count"] == 1
    assert result["call_coordinator"]["camera_with_latest_call_count"] == 1
    assert result["last_call_image"]["ffmpeg_available"] is True
    assert result["last_call_image"]["ready_count"] == 1
    image_status.summary.assert_called_once_with()
    auto_save.status.assert_called_once_with(include_details=False)


@pytest.mark.asyncio
async def test_device_diagnostics_survives_camera_failure_and_hides_details(
    hass,
    tmp_path: Path,
) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    hass.config.media_dirs = {"local": str(tmp_path)}

    coordinator = SimpleNamespace(
        data={7: _skud()},
        update_interval=timedelta(seconds=300),
        last_exception=None,
        last_update_success=True,
    )
    call_coordinator = SimpleNamespace(
        data={"CAMERA-SECRET-123": {"uuid": "hidden-call"}},
        new_calls=[],
        update_interval=timedelta(seconds=10),
        last_exception=None,
        last_update_success=True,
    )
    api = MagicMock()
    api.async_get_camera = AsyncMock(side_effect=RuntimeError("token=VERY-SECRET"))
    api.diagnostic_auth_state.return_value = {"ufanet_access_present": True}
    auto_save = MagicMock()
    auto_save.status.return_value = {"enabled": True, "pending_count": 0}
    controller = SimpleNamespace(
        ready=True,
        timezone_name="Asia/Vladivostok",
        archive_name="Archive",
        dvr_hours=120,
        duration=300,
        step=60,
        last_archive={"url": "https://secret.invalid/?token=SECRET"},
    )
    image_status = MagicMock()
    image_status.status.return_value = {
        "configured": True,
        "ffmpeg_available": True,
        "ready": False,
        "last_error_code": "decode_error",
        "last_error_type": "UfanetPreviewFrameError",
    }

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "call_coordinator": call_coordinator,
        "archive_controllers": {7: controller},
        "auto_save_manager": auto_save,
        "image_status_manager": image_status,
        "call_update_mode": CALL_UPDATE_MODE_FCM,
    }

    device = SimpleNamespace(identifiers={(DOMAIN, "7")})
    result = await async_get_device_diagnostics(hass, entry, device)
    serialized = json.dumps(result, ensure_ascii=False)

    assert result["loaded"] is True
    assert result["camera"] is None
    assert result["camera_fetch_error_type"] == "RuntimeError"
    assert result["archive_controller"]["last_archive_loaded"] is True
    assert result["call_coordinator"]["latest_call_present"] is True
    assert result["last_call_image"]["last_error_type"] == (
        "UfanetPreviewFrameError"
    )
    assert result["last_call_image"]["last_error_code"] == "decode_error"
    assert "VERY-SECRET" not in serialized
    assert "secret.invalid" not in serialized
    assert "CAMERA-SECRET-123" not in serialized
    assert "top-secret" not in serialized
    assert "secret-firebase-config" not in serialized
    image_status.status.assert_called_once_with(7)
    auto_save.status.assert_called_once_with(include_details=False)


@pytest.mark.asyncio
async def test_device_diagnostics_reports_missing_runtime_or_device(hass) -> None:
    entry = _entry()
    device = SimpleNamespace(identifiers={(DOMAIN, "7")})

    assert await async_get_device_diagnostics(hass, entry, device) == {"loaded": False}

    entry.add_to_hass(hass)
    coordinator = SimpleNamespace(
        data={},
        update_interval=None,
        last_exception=None,
        last_update_success=False,
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"coordinator": coordinator}

    result = await async_get_device_diagnostics(hass, entry, device)
    assert result["loaded"] is True
    assert result["device_found_in_coordinator"] is False
