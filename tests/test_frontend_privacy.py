"""Static regression checks for private media handling in the custom card."""

from pathlib import Path

CARD_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "ufanet_intercom"
    / "frontend"
    / "ufanet-archive-card.js"
)


def test_last_call_button_uses_ha_image_proxy_not_ufanet_state_url() -> None:
    source = CARD_PATH.read_text(encoding="utf-8")

    assert "/api/image_proxy/" in source
    assert '"get_last_call_preview_url"' in source
    assert "_lastCallImageEntityId" in source
    assert "attrs.preview_url" not in source
    assert "attributes?.preview_url" not in source
    assert "previewButton.dataset.url" not in source
    assert "image.last_error_code" in source
    assert "invalid_url" in source
    assert "size_limit" in source
    assert "image.preview_https_upgraded" in source
    assert "image.preview_payload_kind" in source
    assert "image.retry_suppressed" in source
    assert "embedded_credentials" in source



def test_fcm_session_ui_uses_safe_refs_and_protection_guards() -> None:
    source = CARD_PATH.read_text(encoding="utf-8")

    assert 'id="tab-sessions"' in source
    assert '"list_fcm_sessions"' in source
    assert '"revoke_fcm_session"' in source
    assert '"revoke_other_fcm_sessions"' in source
    assert "session_ref: session.session_ref" in source
    assert "expected_count: count" in source
    assert "confirm: true" in source
    assert "session.protected === true" in source
    assert "Home Assistant • защищено" in source
    assert "Отозвать все остальные" in source

    render = source.split("  _renderFcmSessions() {", 1)[1].split(
        "  async _revokeFcmSession", 1
    )[0]
    assert "session_ref" not in render
    assert "device_id" not in render
    assert "textContent = String(session.title" in render
