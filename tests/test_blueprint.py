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


def test_incoming_call_notification_blueprint_is_valid() -> None:
    data = yaml_util.load_yaml_dict(BLUEPRINT_PATH)
    blueprint = Blueprint(
        data,
        path=str(BLUEPRINT_PATH),
        expected_domain="automation",
        schema=AUTOMATION_BLUEPRINT_SCHEMA,
    )

    assert blueprint.name == "Ufanet incoming call notification"
    assert set(blueprint.inputs) == {
        "intercom_device",
        "notify_device",
        "last_call_image",
        "image_delay",
        "notification_title",
        "notification_message",
    }
    assert blueprint.metadata["homeassistant"]["min_version"] == "2026.8.0"
