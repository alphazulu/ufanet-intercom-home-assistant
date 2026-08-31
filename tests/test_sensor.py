"""Tests for token-free last-call sensor state."""

from __future__ import annotations

import json
from types import SimpleNamespace

from custom_components.ufanet_intercom.sensor import UfanetLastCallSensor


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
