"""Tests for standalone UCAMS runtime identity and capability handling."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.ufanet_intercom.private_entities import (
    UfanetStandaloneMotionEvent,
)
from custom_components.ufanet_intercom.private_runtime import (
    UfanetPrivateCameraRuntime,
    private_camera_ref,
    private_camera_supports_archive,
    private_camera_supports_motion,
)


def _camera(
    number: str,
    *,
    dvr_hours: int = 120,
    motion: bool = True,
    permission: int | None = 10,
) -> dict:
    return {
        "number": number,
        "title": "Parking",
        "address": "Private address",
        "timezone": "Asia/Vladivostok",
        "streams_count": 1,
        "analytics": ("motion_alarm",) if motion else (),
        "dvr_hours": dvr_hours,
        "permission": permission,
        "is_fav": False,
        "is_public": False,
    }


def test_private_camera_ref_is_stable_and_does_not_expose_provider_number() -> None:
    first = private_camera_ref("1765960069FWI918")
    second = private_camera_ref("1765960069FWI918")

    assert first == second
    assert first.startswith("ucams_camera_")
    assert "1765960069FWI918" not in first


def test_private_camera_inventory_capabilities_are_minimal() -> None:
    assert private_camera_supports_archive(_camera("A", dvr_hours=120)) is True
    assert private_camera_supports_archive(_camera("A", dvr_hours=0)) is False
    assert private_camera_supports_archive(_camera("A", permission=30)) is False
    assert private_camera_supports_archive(_camera("A", permission=None)) is True
    assert private_camera_supports_motion(_camera("A", motion=True)) is True
    assert private_camera_supports_motion(_camera("A", motion=False)) is False


def test_standalone_inventory_recalculates_intercom_exclusion() -> None:
    manager = object.__new__(UfanetPrivateCameraRuntime)
    manager.coordinator = SimpleNamespace(
        data={
            "CAM-A": _camera("CAM-A"),
            "CAM-B": _camera("CAM-B"),
        }
    )
    manager.skud_coordinator = SimpleNamespace(
        data={7: {"id": 7, "cctv_number": "CAM-A"}}
    )

    standalone = manager.standalone_cameras()
    assert [camera["number"] for camera in standalone.values()] == ["CAM-B"]

    manager.skud_coordinator.data = {7: {"id": 7, "cctv_number": "CAM-B"}}
    standalone = manager.standalone_cameras()
    assert [camera["number"] for camera in standalone.values()] == ["CAM-A"]


def test_standalone_motion_event_does_not_publish_provider_fields() -> None:
    target_ref = private_camera_ref("PRIVATE-CAMERA")
    coordinator = SimpleNamespace(
        data={target_ref: {"supported": True}},
        new_events={
            target_ref: [
                {
                    "occurred_at": "2026-09-09T10:00:00+00:00",
                    "camera_number": "PRIVATE-CAMERA",
                    "cursor_id": 123,
                    "media_url": "https://private.invalid/secret",
                }
            ]
        },
        last_update_success=True,
    )
    manager = SimpleNamespace(
        analytics_coordinator=coordinator,
        motion_available=lambda ref: ref == target_ref,
    )
    entity = UfanetStandaloneMotionEvent(
        manager,
        target_ref,
        _camera("PRIVATE-CAMERA"),
    )
    entity.async_write_ha_state = MagicMock()

    entity._handle_motion_update()  # noqa: SLF001

    assert entity.state_attributes == {
        "event_type": "motion",
        "occurred_at": "2026-09-09T10:00:00+00:00",
    }
    entity.async_write_ha_state.assert_called_once_with()
