"""Tests for account-wide UCAMS private camera inventory support."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.ufanet_intercom.api import UfanetResponseError
from custom_components.ufanet_intercom.private_cameras import (
    PRIVATE_CAMERA_FIELDS,
    PRIVATE_CAMERA_PAGE_SIZE,
    async_get_private_cameras,
    parse_private_camera_page,
)


def _page(results: list[dict], next_page: int | None = None) -> dict:
    return {
        "results": results,
        "page": {
            "current": 1,
            "next": next_page,
            "previous": None,
        },
    }


def test_private_camera_page_drops_tokens_domains_and_unknown_fields() -> None:
    cameras, next_page = parse_private_camera_page(
        _page(
            [
                {
                    "number": "CAM-1",
                    "title": "Parking",
                    "address": "Private address",
                    "timezone": "Asia/Vladivostok",
                    "streams_count": 1,
                    "analytics": ["motion_alarm", "motion_alarm"],
                    "tariff": {"name": "Archive", "dvr_hours": 120},
                    "is_fav": False,
                    "is_public": False,
                    "token_l": "SECRET-LIVE",
                    "token_r": "SECRET-ARCHIVE",
                    "server": {"domain": "private.invalid"},
                    "unexpected_private_field": "do not retain",
                }
            ]
        )
    )

    assert next_page is None
    assert cameras == [
        {
            "number": "CAM-1",
            "title": "Parking",
            "address": "Private address",
            "timezone": "Asia/Vladivostok",
            "streams_count": 1,
            "analytics": ("motion_alarm",),
            "dvr_hours": 120,
            "is_fav": False,
            "is_public": False,
        }
    ]
    assert "token_l" not in cameras[0]
    assert "token_r" not in cameras[0]
    assert "server" not in cameras[0]


@pytest.mark.asyncio
async def test_private_camera_inventory_uses_official_pagination_and_deduplicates() -> None:
    api = AsyncMock()
    api._async_ucams_json.side_effect = [
        _page(
            [
                {
                    "number": "CAM-A",
                    "title": "A",
                    "analytics": ["motion_alarm"],
                    "streams_count": 1,
                    "tariff": {"dvr_hours": 120},
                }
            ],
            next_page=2,
        ),
        _page(
            [
                {
                    "number": "CAM-A",
                    "title": "A refreshed",
                    "analytics": ["motion_alarm"],
                    "streams_count": 1,
                    "tariff": {"dvr_hours": 120},
                },
                {
                    "number": "CAM-B",
                    "title": "B",
                    "analytics": [],
                    "streams_count": 1,
                    "tariff": {"dvr_hours": 0},
                },
            ]
        ),
    ]

    cameras = await async_get_private_cameras(api)

    assert [camera["number"] for camera in cameras] == ["CAM-A", "CAM-B"]
    assert cameras[0]["title"] == "A refreshed"
    assert api._async_ucams_json.await_count == 2
    api._async_ucams_json.assert_any_await(
        "POST",
        "/api/v0/cameras/my/",
        json_body={
            "page": 1,
            "order_by": "addr_asc",
            "page_size": PRIVATE_CAMERA_PAGE_SIZE,
            "fields": list(PRIVATE_CAMERA_FIELDS),
        },
    )
    api._async_ucams_json.assert_any_await(
        "POST",
        "/api/v0/cameras/my/",
        json_body={
            "page": 2,
            "order_by": "addr_asc",
            "page_size": PRIVATE_CAMERA_PAGE_SIZE,
            "fields": list(PRIVATE_CAMERA_FIELDS),
        },
    )


@pytest.mark.asyncio
async def test_private_camera_inventory_rejects_pagination_loop() -> None:
    api = AsyncMock()
    api._async_ucams_json.return_value = _page([], next_page=1)

    with pytest.raises(UfanetResponseError, match="pagination loop"):
        await async_get_private_cameras(api)


def test_private_camera_page_rejects_invalid_analytics_shape() -> None:
    with pytest.raises(UfanetResponseError, match="analytics"):
        parse_private_camera_page(
            _page(
                [
                    {
                        "number": "CAM-A",
                        "analytics": {"motion_alarm": True},
                    }
                ]
            )
        )
