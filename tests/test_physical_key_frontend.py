"""Static regression checks for the physical-key Lovelace extension."""

from pathlib import Path

EXTENSION_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "ufanet_intercom"
    / "frontend"
    / "ufanet-physical-keys-card.js"
)


def test_physical_key_tab_uses_privacy_safe_response_services() -> None:
    """Keep provider identifiers out of the browser-facing key workflow."""
    source = EXTENSION_PATH.read_text(encoding="utf-8")

    assert 'const KEY_TAB = "keys"' in source
    assert 'tab.id = "tab-keys"' in source
    assert 'panel.id = "panel-keys"' in source
    assert '"list_physical_keys"' in source
    assert '"rename_physical_key"' in source
    assert "key_ref: item.key_ref" in source
    assert "provider key ID" in source
    assert "key_id" not in source
    assert "external_id" not in source


def test_physical_key_tab_has_enrollment_but_no_delete_path() -> None:
    """Enrollment is explicit and destructive key deletion stays absent."""
    source = EXTENSION_PATH.read_text(encoding="utf-8")

    assert 'endsWith("_add_physical_key")' in source
    assert 'domain: "button"' in source
    assert 'service: "press"' in source
    assert "ENROLLMENT_SECONDS = 60" in source
    assert "window.confirm" in source
    assert "delete_physical_key" not in source
    assert "/delete/key/" not in source


def test_physical_key_tab_verifies_rename_and_refreshes_after_enrollment() -> None:
    """Do not claim rename success without backend verification."""
    source = EXTENSION_PATH.read_text(encoding="utf-8")

    assert "response?.verified !== true" in source
    assert "response?.name !== newName" in source
    assert "await this._refreshPhysicalKeys(true)" in source
    assert "Окно регистрации завершилось. Проверяю список ключей" in source
