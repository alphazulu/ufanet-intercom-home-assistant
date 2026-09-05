"""Validation for the bundled incoming-call notification blueprint."""

from pathlib import Path

from homeassistant.components.automation.config import AUTOMATION_BLUEPRINT_SCHEMA
from homeassistant.components.blueprint.models import Blueprint
from homeassistant.util import yaml as yaml_util


BLUEPRINT_PATH = (
    Path(__file__).resolve().parents[1]
    / "blueprints"
    / "automation"
    / "ufanet_intercom"
    / "incoming_call_notification.yaml"
)


def _load_blueprint() -> tuple[dict, Blueprint]:
    data = yaml_util.load_yaml_dict(BLUEPRINT_PATH)
    blueprint = Blueprint(
        data,
        path=str(BLUEPRINT_PATH),
        expected_domain="automation",
        schema=AUTOMATION_BLUEPRINT_SCHEMA,
    )
    return data, blueprint


def test_incoming_call_notification_blueprint_is_valid() -> None:
    data, blueprint = _load_blueprint()

    assert blueprint.name == "Ufanet incoming call notification"
    assert set(blueprint.inputs) == {
        "intercom_device",
        "notify_device",
        "last_call_sensor",
        "last_call_image",
        "live_camera",
        "open_door_button",
        "image_delay",
        "action_timeout",
        "dashboard_uri",
        "notification_channel",
        "notification_title",
        "notification_message",
    }
    assert blueprint.metadata["homeassistant"]["min_version"] == "2026.8.0"
    assert data["mode"] == "restart"
    assert "max" not in data


def test_blueprint_uses_private_image_proxy_and_no_provider_media_urls() -> None:
    source = BLUEPRINT_PATH.read_text(encoding="utf-8")

    assert "/api/image_proxy/{{ last_call_image_entity }}" in source
    assert "access_token" not in source
    assert "preview_url" not in source
    assert "archive_url" not in source


def test_blueprint_renders_complete_privacy_safe_call_metadata() -> None:
    source = BLUEPRINT_PATH.read_text(encoding="utf-8")

    assert "device_name(intercom_device_id)" in source
    assert "notification_title_rendered" in source
    assert "Address: " in source
    assert "Porch: " in source
    assert "Flat: " in source
    assert "Time: " in source
    assert "timestamp_custom('%d.%m.%Y %H:%M:%S', true)" in source
    assert "event_data.address" in source
    assert "event_data.porch" in source
    assert "event_data.flat" in source
    assert "event_data.called_at" in source


def test_blueprint_view_camera_opens_selected_live_camera() -> None:
    source = BLUEPRINT_PATH.read_text(encoding="utf-8")

    assert "live_camera_entity: !input live_camera" in source
    assert "live_camera_entity.startswith('camera.')" in source
    assert "live_camera_entity in device_entities(intercom_device_id)" in source
    assert "more-info-entity-id=" in source
    assert 'uri: "{{ camera_uri_value }}"' in source
    assert 'uri: "{{ dashboard_uri_value }}"' not in source


def test_blueprint_notification_identifiers_use_available_run_context() -> None:
    source = BLUEPRINT_PATH.read_text(encoding="utf-8")

    assert "trigger.event.context.id" in source
    assert "context.id" not in source.replace("trigger.event.context.id", "")
    assert "{{ 'UFANET_OPEN_' ~ run_id }}" in source
    assert "ufanet_intercom_test_" in source
    assert "~ intercom_device_id" in source
    assert "call_uuid" not in source


def test_blueprint_sends_immediately_and_uses_unique_guarded_door_action() -> None:
    source = BLUEPRINT_PATH.read_text(encoding="utf-8")

    assert "UFANET_OPEN_' ~ run_id" in source
    assert "mobile_app_notification_action" in source
    assert 'authenticationRequired: "true"' in source
    assert "authenticationRequired: true" not in source
    assert "destructive:" not in source
    assert "action: button.press" in source
    assert "Manual test — door action is disabled." in source
    assert "ttl: 0" in source
    assert "priority: high" in source
    assert 'channel: "{{ notification_channel_value }}"' in source
    assert "importance: high" in source
    assert "tag: \"{{ notification_tag }}\"" in source
    assert "alert_once: true" in source
    assert "confirmation: true" in source
    assert "action: URI" in source


def test_blueprint_guards_door_button_against_selected_device() -> None:
    source = BLUEPRINT_PATH.read_text(encoding="utf-8")

    assert source.count("device_entities(intercom_device_id)") >= 4
    assert source.count("open_door_button_entity.startswith('button.')") >= 3
    assert "Revalidate the relay immediately before pressing it" in source


def test_blueprint_invalidates_old_and_expired_door_actions() -> None:
    source = BLUEPRINT_PATH.read_text(encoding="utf-8")

    assert "mode: restart" in source
    assert "Open door action expired." in source
    assert "Open door command sent." in source
    assert "Open door action is no longer available." in source
    assert "timeout: \"{{ wait.remaining }}\"" in source
    assert "id: open_door" in source
    assert "id: image_changed" in source


def test_blueprint_real_call_trigger_is_device_scoped() -> None:
    data, _blueprint = _load_blueprint()
    trigger = data["triggers"][0]

    assert trigger["trigger"] == "device"
    assert trigger["domain"] == "ufanet_intercom"
    assert trigger["type"] == "incoming_call"
