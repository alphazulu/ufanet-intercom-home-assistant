"""Static contract tests for the standalone-camera Lovelace extension."""

from __future__ import annotations

from pathlib import Path


FRONTEND = (
    Path(__file__).parents[1]
    / "custom_components"
    / "ufanet_intercom"
    / "frontend"
    / "ufanet-private-camera-card.js"
)


def test_private_camera_extension_routes_only_archive_and_motion_services() -> None:
    source = FRONTEND.read_text(encoding="utf-8")
    assert 'get_archive_ranges: "get_private_archive_ranges"' in source
    assert 'get_archive_url: "get_private_archive_url"' in source
    assert 'get_archive_download_url: "get_private_archive_download_url"' in source
    assert 'get_motion_events: "get_private_motion_events"' in source
    assert 'get_call_events: "get_private_call_events"' in source
    assert "open_door: \"" not in source
    assert "guest_access: \"" not in source
    assert "fcm_session" not in source.lower()


def test_private_camera_extension_hides_intercom_only_controls() -> None:
    source = FRONTEND.read_text(encoding="utf-8")
    for tab in ("guests", "sessions", "diagnostics", "keys"):
        assert f'"{tab}"' in source
    for element_id in (
        "live-door-state",
        "live-open-door",
        "live-last-call",
        "live-open-call-archive",
        "live-open-call-preview",
    ):
        assert f'"{element_id}"' in source
    assert 'header.textContent = "Камера Ufanet"' in source


def test_private_camera_extension_detects_only_opaque_entity_identifiers() -> None:
    source = FRONTEND.read_text(encoding="utf-8")
    assert 'uniqueId.startsWith("ucams_private_camera_")' in source
    assert 'uniqueId.startsWith("ucams_private_archive_camera_")' in source
    assert "camera_number" not in source
