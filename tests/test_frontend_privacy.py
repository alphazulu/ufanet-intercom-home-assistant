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
