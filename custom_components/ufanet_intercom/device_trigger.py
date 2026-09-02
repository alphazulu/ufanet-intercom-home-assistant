"""Device automation triggers for Ufanet Intercom."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.components.device_automation import (
    DEVICE_TRIGGER_BASE_SCHEMA,
    DeviceNotFound,
)
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    EVENT_INTERCOM_CALL,
    EVENT_KEY_PASSAGE,
    EVENT_MOTION_ANALYTICS,
    TRIGGER_INCOMING_CALL,
    TRIGGER_KEY_PASSAGE,
    TRIGGER_MOTION_ANALYTICS,
)

TRIGGER_TYPES = {
    TRIGGER_INCOMING_CALL,
    TRIGGER_KEY_PASSAGE,
    TRIGGER_MOTION_ANALYTICS,
}

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_DOMAIN): DOMAIN,
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
    }
)


async def async_get_triggers(
    hass: HomeAssistant,
    device_id: str,
) -> list[dict[str, str]]:
    """List visual automation triggers for a Ufanet intercom device."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise DeviceNotFound(f"Device ID {device_id} is not valid")
    if not any(identifier[0] == DOMAIN for identifier in device.identifiers):
        return []

    triggers = [
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: device_id,
            CONF_TYPE: TRIGGER_INCOMING_CALL,
        }
    ]
    skud_ids = {
        int(identifier)
        for domain, identifier in device.identifiers
        if domain == DOMAIN and str(identifier).isdigit()
    }
    passage_supported = False
    motion_supported = False
    for entry_id in device.config_entries:
        runtime = hass.data.get(DOMAIN, {}).get(entry_id)
        if not isinstance(runtime, dict):
            continue
        passage_coordinator = runtime.get("key_passage_coordinator")
        passage_data = (
            passage_coordinator.data if passage_coordinator is not None else None
        )
        if isinstance(passage_data, dict) and any(
            skud_id in passage_data for skud_id in skud_ids
        ):
            passage_supported = True

        analytics_coordinator = runtime.get("analytics_coordinator")
        analytics_data = (
            analytics_coordinator.data if analytics_coordinator is not None else None
        )
        if isinstance(analytics_data, dict) and any(
            skud_id in analytics_data for skud_id in skud_ids
        ):
            motion_supported = True

    if passage_supported:
        triggers.append(
            {
                CONF_PLATFORM: "device",
                CONF_DOMAIN: DOMAIN,
                CONF_DEVICE_ID: device_id,
                CONF_TYPE: TRIGGER_KEY_PASSAGE,
            }
        )
    if motion_supported:
        triggers.append(
            {
                CONF_PLATFORM: "device",
                CONF_DOMAIN: DOMAIN,
                CONF_DEVICE_ID: device_id,
                CONF_TYPE: TRIGGER_MOTION_ANALYTICS,
            }
        )
    return triggers


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a device trigger to the corresponding sanitized event."""
    trigger_type = config[CONF_TYPE]
    if trigger_type == TRIGGER_KEY_PASSAGE:
        event_type = EVENT_KEY_PASSAGE
    elif trigger_type == TRIGGER_MOTION_ANALYTICS:
        event_type = EVENT_MOTION_ANALYTICS
    else:
        event_type = EVENT_INTERCOM_CALL
    event_config = event_trigger.TRIGGER_SCHEMA(
        {
            event_trigger.CONF_PLATFORM: "event",
            event_trigger.CONF_EVENT_TYPE: event_type,
            event_trigger.CONF_EVENT_DATA: {
                CONF_DEVICE_ID: config[CONF_DEVICE_ID],
            },
        }
    )
    return await event_trigger.async_attach_trigger(
        hass,
        event_config,
        action,
        trigger_info,
        platform_type="device",
    )
