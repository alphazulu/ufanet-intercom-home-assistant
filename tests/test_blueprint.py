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
    _data, blueprint = _load_blueprint()

    assert blueprint.name == "Ufanet incoming call notification"
    assert set(blueprint.inputs) == {
        "intercom_device",
        "notify_device",
        "last_call_sensor",
        "last_call_image",
        "open_door_button",
        "image_delay",
        "action_timeout",
        "dashboard_uri",
        "notification_title",
        "notification_message",
    }
    assert blueprint.metadata["homeassistant"]["min_version"] == "2026.8.0"


def test_blueprint_uses_private_image_proxy_and_no_provider_media_urls() -> None:
    source = BLUEPRINT_PATH.read_text(encoding="utf-8")

    assert "/api/image_proxy/{{ last_call_image_entity }}" in source
    assert "access_token" not in source
    assert "preview_url" not in source
    assert "archive_url" not in source


def test_blueprint_notification_identifiers_use_available_run_context() -> None:
    source = BLUEPRINT_PATH.read_text(encoding="utf-8")

    assert "trigger.event.context.id" in source
    assert "context.id" not in source.replace("trigger.event.context.id", "")
    assert "{{ 'ufanet_intercom_' ~ run_id }}" in source
    assert "{{ 'UFANET_OPEN_' ~ run_id }}" in source
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
    assert "tag: \"{{ notification_tag }}\"" in source
    assert "alert_once: true" in source
    assert "confirmation: true" in source


def test_blueprint_real_call_trigger_is_device_scoped() -> None:
    data, _blueprint = _load_blueprint()
    trigger = data["triggers"][0]

    assert trigger["trigger"] == "device"
    assert trigger["domain"] == "ufanet_intercom"
    assert trigger["type"] == "incoming_call"
