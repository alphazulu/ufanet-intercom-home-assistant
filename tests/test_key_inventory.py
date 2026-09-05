"""Tests for read-only physical-key inventory parsing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ufanet_intercom.api import UfanetConnectionError, UfanetResponseError
from custom_components.ufanet_intercom.key_inventory import UfanetApi


@pytest.fixture
def api() -> UfanetApi:
    return UfanetApi(
        MagicMock(),
        "AB123",
        "secret",
        ufanet_base_url="https://ufanet.test",
        ucams_base_url="https://ucams.test",
    )


@pytest.mark.asyncio
async def test_inventory_keeps_display_fields_and_drops_external_id(api: UfanetApi) -> None:
    api._async_ufanet_json = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "data": {
                "keys": [
                    {
                        "id": 3321992,
                        "external_id": "7898795-ACCESS-SECRET",
                        "name": "Папа",
                        "create_date": 1_751_011_416,
                        "devices": ["128549", "7"],
                    }
                ]
            }
        }
    )

    result = await api.async_get_physical_keys()

    api._async_ufanet_json.assert_awaited_once_with(  # type: ignore[attr-defined]
        "POST",
        "/api/v4/key/list/",
    )
    assert result == [
        {
            "key_id": 3321992,
            "name": "Папа",
            "created_at": 1_751_011_416,
            "devices": (128549, 7),
        }
    ]
    assert api.physical_key_inventory == tuple(result)
    serialized = str(result) + str(api.physical_key_inventory)
    assert "external_id" not in serialized
    assert "7898795-ACCESS-SECRET" not in serialized


@pytest.mark.asyncio
async def test_inventory_rejects_duplicate_key_ids(api: UfanetApi) -> None:
    row = {
        "id": 10,
        "external_id": "private",
        "name": "Key",
        "create_date": 1_700_000_000,
        "devices": ["7"],
    }
    api._async_ufanet_json = AsyncMock(  # type: ignore[method-assign]
        return_value={"data": {"keys": [row, dict(row)]}}
    )

    with pytest.raises(UfanetResponseError, match="duplicate key ID"):
        await api.async_get_physical_keys()

    assert api.physical_key_inventory == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row",
    [
        {"id": True, "name": "Key", "create_date": 1, "devices": ["7"]},
        {"id": 1, "name": None, "create_date": 1, "devices": ["7"]},
        {"id": 1, "name": "Key", "create_date": True, "devices": ["7"]},
        {"id": 1, "name": "Key", "create_date": -1, "devices": ["7"]},
        {"id": 1, "name": "Key", "create_date": 1, "devices": [False]},
    ],
)
async def test_inventory_rejects_invalid_native_fields(
    api: UfanetApi,
    row: dict,
) -> None:
    api._async_ufanet_json = AsyncMock(  # type: ignore[method-assign]
        return_value={"data": {"keys": [row]}}
    )

    with pytest.raises(UfanetResponseError, match="Physical-key response"):
        await api.async_get_physical_keys()

    assert api.physical_key_inventory == ()


@pytest.mark.asyncio
async def test_failed_inventory_refresh_does_not_retain_previous_metadata(
    api: UfanetApi,
) -> None:
    api._physical_key_inventory = (  # noqa: SLF001
        {
            "key_id": 99,
            "name": "Old private name",
            "created_at": 1_700_000_000,
            "devices": (7,),
        },
    )
    api._async_ufanet_json = AsyncMock(  # type: ignore[method-assign]
        side_effect=UfanetConnectionError("offline")
    )

    with pytest.raises(UfanetConnectionError):
        await api.async_get_physical_keys()

    assert api.physical_key_inventory == ()
