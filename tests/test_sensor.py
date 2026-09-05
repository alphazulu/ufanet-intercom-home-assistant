"""Tests for token-free last-call and physical-key sensor state."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from custom_components.ufanet_intercom.sensor import (
    UfanetLastCallSensor,
    UfanetLastKeyPassageSensor,
    UfanetPhysicalKeyCountSensor,
)


def _skud() -> dict:
    return {
        "id": 7,
        "cctv_number": "CAM-7",
        "custom_name": "Front door",
        "role": {"name": "Intercom"},
        "model": 39,
    }


def test_last_call_attributes_publish_capabilities_without_media_urls() -> None:
    coordinator = SimpleNamespace(
        last_update_success=True,
        data={
            "CAM-7": {
                "uuid": "call-1",
                "camera_number": "CAM-7",
                "called_at": "2026-08-31T11:22:33+10:00",
                "timezone": "Asia/Vladivostok",
                "address": "Street",
                "porch": "1",
                "flat": "2",
                "preview_url": "https://media.invalid/p.mp4?token=PREVIEW-SECRET",
                "archive_url": "https://media.invalid/a.mp4?token=ARCHIVE-SECRET",
            }
        },
    )
    entity = UfanetLastCallSensor(coordinator, _skud())

    attributes = entity.extra_state_attributes
    serialized = json.dumps(attributes)

    assert attributes["has_preview"] is True
    assert attributes["has_archive"] is True
    assert "preview_url" not in attributes
    assert "archive_url" not in attributes
    assert "PREVIEW-SECRET" not in serialized
    assert "ARCHIVE-SECRET" not in serialized


def test_physical_key_sensor_exposes_sanitized_read_only_inventory() -> None:
    created = 1_751_011_416
    coordinator = SimpleNamespace(
        last_update_success=True,
        data={
            7: {
                "key_count": 2,
                "last_passage_at": 1_788_220_800,
            }
        },
        api=SimpleNamespace(
            physical_key_inventory=(
                {
                    "key_id": 3321992,
                    "name": "Папа",
                    "created_at": created,
                    "devices": (7, 8),
                },
                {
                    "key_id": 3321993,
                    "name": "Other intercom",
                    "created_at": created + 10,
                    "devices": (8,),
                },
            )
        ),
    )

    count = UfanetPhysicalKeyCountSensor(coordinator, _skud())
    latest = UfanetLastKeyPassageSensor(coordinator, _skud())

    assert count.available is True
    assert count.native_value == 2
    assert latest.native_value == datetime(
        2026,
        9,
        1,
        tzinfo=timezone.utc,
    )
    assert count.extra_state_attributes == {
        "keys": [
            {
                "name": "Папа",
                "created_at": datetime.fromtimestamp(
                    created,
                    tz=timezone.utc,
                ).isoformat(),
            }
        ]
    }
    assert latest.extra_state_attributes is None

    serialized = json.dumps(count.extra_state_attributes, ensure_ascii=False)
    assert "3321992" not in serialized
    assert "key_id" not in serialized
    assert "external_id" not in serialized
    assert "Other intercom" not in serialized
