"""Static regression checks for the authorized-device frontend extension."""

from pathlib import Path

CARD_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "ufanet_intercom"
    / "frontend"
    / "ufanet-authorized-devices-card.js"
)
BACKEND_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "ufanet_intercom"
    / "authorized_devices.py"
)


def test_standard_device_ui_uses_canonical_authorization_services() -> None:
    source = CARD_PATH.read_text(encoding="utf-8")

    assert '"list_authorized_devices"' in source
    assert '"revoke_authorized_device"' in source
    assert '"revoke_other_authorized_devices"' in source
    assert "response.authorizations" in source
    assert "authorization_ref: authorization.authorization_ref" in source
    assert "Отозвать авторизацию" in source
    assert "Активность:" in source
    assert "Home Assistant • защищено" in source

    # The canonical standard UI must not fall back to the historical aliases.
    assert '"list_fcm_sessions"' not in source
    assert '"revoke_fcm_session"' not in source
    assert '"revoke_other_fcm_sessions"' not in source


def test_advanced_fcm_ui_is_separate_and_warns_about_refresh_revocation() -> None:
    source = CARD_PATH.read_text(encoding="utf-8")

    assert "Расширенное управление FCM" in source
    assert '"list_fcm_registrations"' in source
    assert '"unregister_fcm_registration"' in source
    assert '"unregister_other_fcm_registrations"' in source
    assert "fcm_ref: registration.fcm_ref" in source
    assert "DELETE /api/v0/fcm/" in source
    assert "refresh JWT" in source
    assert "logout_device" in source
    assert "registration.protected === true" in source


def test_frontend_extension_is_served_only_after_static_path_registration() -> None:
    source = BACKEND_PATH.read_text(encoding="utf-8")

    assert '"ufanet-authorized-devices-card.js"' in source
    static_position = source.index("async_register_static_paths")
    inject_position = source.index("frontend.add_extra_js_url")
    assert static_position < inject_position
    assert "customElements.whenDefined" in CARD_PATH.read_text(encoding="utf-8")
