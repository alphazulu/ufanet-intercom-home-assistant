"""Permission tests for guest and shared-access services."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.auth.const import GROUP_ID_ADMIN, GROUP_ID_USER
from homeassistant.core import Context
from homeassistant.exceptions import Unauthorized

from custom_components.ufanet_intercom.const import (
    DOMAIN,
    SERVICE_CREATE_GUEST_INVITE,
    SERVICE_CREATE_TEMPORARY_GUEST_LINK,
    SERVICE_FORGET_GUEST_INVITE,
    SERVICE_GET_GUEST_ACCESS,
    SERVICE_REVOKE_SHARED_ACCESS,
    SERVICE_REVOKE_TEMPORARY_GUEST_LINK,
)
from custom_components.ufanet_intercom.services import async_setup_services


_GUEST_SERVICE_CALLS = (
    (SERVICE_GET_GUEST_ACCESS, {"device_id": "test-device"}),
    (
        SERVICE_CREATE_TEMPORARY_GUEST_LINK,
        {"device_id": "test-device", "duration_minutes": 60},
    ),
    (
        SERVICE_REVOKE_TEMPORARY_GUEST_LINK,
        {"device_id": "test-device", "token": "test-token"},
    ),
    (SERVICE_CREATE_GUEST_INVITE, {"device_id": "test-device"}),
    (
        SERVICE_FORGET_GUEST_INVITE,
        {"device_id": "test-device", "invite_id": "test-invite"},
    ),
    (
        SERVICE_REVOKE_SHARED_ACCESS,
        {"device_id": "test-device", "access_id": 1},
    ),
)


@pytest.mark.asyncio
@pytest.mark.parametrize(("service", "service_data"), _GUEST_SERVICE_CALLS)
async def test_guest_services_reject_non_admin_users(
    hass,
    service: str,
    service_data: dict[str, object],
) -> None:
    """A regular HA user must not read or mutate guest access credentials."""
    await hass.auth.async_create_user("Admin", group_ids=[GROUP_ID_ADMIN])
    user = await hass.auth.async_create_user(
        "Regular user",
        group_ids=[GROUP_ID_USER],
    )
    assert not user.is_admin
    async_setup_services(hass, MagicMock())

    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            service,
            service_data,
            blocking=True,
            return_response=True,
            context=Context(user_id=user.id),
        )
