"""Static regression checks for archive motion timeline UI."""

from pathlib import Path


def test_frontend_motion_timeline_uses_privacy_safe_service_and_point_markers() -> None:
    text = Path(
        "custom_components/ufanet_intercom/frontend/ufanet-archive-card.js"
    ).read_text(encoding="utf-8")
    assert 'const MOTION_EVENT_LEAD_SECONDS = 18;' in text
    assert 'this._callResponseService("get_motion_events"' in text
    assert 'marker.className = "motion-marker"' in text
    assert 'void this._loadMotionEvent(event);' in text

    start = text.index("async _refreshMotionEvents")
    end = text.index("_callAddress(event)", start)
    boundary = text[start:end]
    for private_name in ("cursor_id", "camera_number", "length", "recognition", "media_url"):
        assert private_name not in boundary
