"""Pagination edge cases for UCAMS motion analytics."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from custom_components.ufanet_intercom.analytics import async_get_motion_events


@pytest.mark.asyncio
async def test_empty_report_accepts_zero_total_pages() -> None:
    api = AsyncMock()
    api._async_ucams_json.return_value = {
        "count": 0,
        "page": {
            "current": 0,
            "next": None,
            "previous": None,
            "all": 0,
            "page_size": 60,
        },
        "results": [],
    }

    report = await async_get_motion_events(
        api,
        "CAM",
        start=datetime(2026, 9, 2, 9, 0, tzinfo=timezone.utc),
        end=datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc),
    )

    assert report.complete is True
    assert report.events == ()
