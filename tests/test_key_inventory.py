"""Tests for private physical-key inventory and live passage parsing."""

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
async def test_inventory_keeps_external_id_private_for_android_history_filter(api: UfanetApi) -> None:
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
            "external_id": "7898795-ACCESS-SECRET",
            "name": "Папа",
            "created_at": 1_751_011_416,
            "devices": (128549, 7),
        }
    ]
    assert api.physical_key_inventory == tuple(result)


@pytest.mark.asyncio
async def test_live_passage_parser_accepts_numeric_string_key_like_android_gson(api: UfanetApi) -> None:
    api._async_ufanet_json = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "count": 2,
            "current_page": 0,
            "page_count": 0,
            "page_size": 25,
            "results": [
                {"key": "7898795", "key_name": "Key", "time_passage": 1_700_000_100},
                {"key": 7898796, "key_name": "Key 2", "time_passage": 1_700_000_200},
            ],
        }
    )

    result = await api.async_get_key_passage_history(154273)

    api._async_ufanet_json.assert_awaited_once_with(  # type: ignore[attr-defined]
        "POST",
        "/api/v4/key/skud/154273/key/pass_history/",
        json_body={"page": 0, "page_size": 25},
    )
    assert [item["key_id"] for item in result["results"]] == [7898795, 7898796]


@pytest.mark.asyncio
async def test_live_passage_parser_rejects_non_numeric_string_key(api: UfanetApi) -> None:
    api._async_ufanet_json = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "count": 1,
            "current_page": 0,
            "page_count": 0,
            "page_size": 25,
            "results": [
                {"key": "not-numeric", "key_name": "Key", "time_passage": 1_700_000_100}
            ],
        }
    )

    with pytest.raises(UfanetResponseError, match="invalid fields"):
        await api.async_get_key_passage_history(154273)


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
        {"id": True, "external_id": "x", "name": "Key", "create_date": 1, "devices": ["7"]},
        {"id": 1, "external_id": None, "name": "Key", "create_date": 1, "devices": ["7"]},
        {"id": 1, "external_id": "", "name": "Key", "create_date": 1, "devices": ["7"]},
        {"id": 1, "external_id": "x", "name": None, "create_date": 1, "devices": ["7"]},
        {"id": 1, "external_id": "x", "name": "Key", "create_date": True, "devices": ["7"]},
        {"id": 1, "external_id": "x", "name": "Key", "create_date": -1, "devices": ["7"]},
        {"id": 1, "external_id": "x", "name": "Key", "create_date": 1, "devices": [False]},
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
            "external_id": "private-old-external",
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
