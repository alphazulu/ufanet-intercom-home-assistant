"""UCAMS private camera inventory support."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any, TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import UfanetApi, UfanetApiError, UfanetAuthError, UfanetResponseError
from .const import DEFAULT_SCAN_INTERVAL_SECONDS, DOMAIN

_LOGGER = logging.getLogger(__name__)

PRIVATE_CAMERA_PAGE_SIZE = 50
PRIVATE_CAMERA_MAX_PAGES = 100
PRIVATE_CAMERA_FIELDS = [
    "number",
    "address",
    "title",
    "timezone",
    "analytics",
    "blocking_lvl",
    "streams_count",
    "is_public",
    "inactivity_period",
    "tariff",
    "permission",
    "is_fav",
]


class UcamsPrivateCamera(TypedDict):
    """Privacy-minimized UCAMS camera inventory item."""

    number: str
    title: str | None
    address: str | None
    timezone: str | None
    streams_count: int | None
    analytics: tuple[str, ...]
    dvr_hours: int | None
    permission: int | None
    is_fav: bool | None
    is_public: bool | None


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _optional_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def parse_private_camera_page(
    payload: Any,
) -> tuple[list[UcamsPrivateCamera], int | None]:
    """Normalize one `/api/v0/cameras/my/` page without retaining media tokens."""
    if not isinstance(payload, dict):
        raise UfanetResponseError("Unexpected UCAMS private camera response")

    results = payload.get("results")
    page = payload.get("page")
    if not isinstance(results, list) or not isinstance(page, dict):
        raise UfanetResponseError("Unexpected UCAMS private camera pagination")

    cameras: list[UcamsPrivateCamera] = []
    for item in results:
        if not isinstance(item, dict):
            raise UfanetResponseError("Invalid UCAMS private camera item")

        raw_number = item.get("number")
        if isinstance(raw_number, bool) or not isinstance(raw_number, (str, int)):
            raise UfanetResponseError("Invalid UCAMS private camera number")
        number = str(raw_number).strip()
        if not number:
            raise UfanetResponseError("Invalid UCAMS private camera number")

        raw_analytics = item.get("analytics")
        if raw_analytics is None:
            analytics: tuple[str, ...] = ()
        elif isinstance(raw_analytics, list) and all(
            isinstance(value, str) for value in raw_analytics
        ):
            analytics = tuple(dict.fromkeys(raw_analytics))
        else:
            raise UfanetResponseError("Invalid UCAMS private camera analytics")

        tariff = item.get("tariff")
        dvr_hours = (
            _optional_nonnegative_int(tariff.get("dvr_hours"))
            if isinstance(tariff, dict)
            else None
        )
        cameras.append(
            {
                "number": number,
                "title": _optional_text(item.get("title")),
                "address": _optional_text(item.get("address")),
                "timezone": _optional_text(item.get("timezone")),
                "streams_count": _optional_nonnegative_int(item.get("streams_count")),
                "analytics": analytics,
                "dvr_hours": dvr_hours,
                "permission": _optional_nonnegative_int(item.get("permission")),
                "is_fav": _optional_bool(item.get("is_fav")),
                "is_public": _optional_bool(item.get("is_public")),
            }
        )

    next_page = page.get("next")
    if next_page is None:
        return cameras, None
    if isinstance(next_page, bool) or not isinstance(next_page, int) or next_page < 1:
        raise UfanetResponseError("Invalid UCAMS private camera next page")
    return cameras, next_page


async def async_get_private_cameras(
    api: UfanetApi,
    *,
    max_pages: int = PRIVATE_CAMERA_MAX_PAGES,
) -> list[UcamsPrivateCamera]:
    """Return all private cameras exposed by the official UCAMS inventory API."""
    current_page = 1
    seen_pages: set[int] = set()
    by_number: dict[str, UcamsPrivateCamera] = {}

    while True:
        if current_page in seen_pages:
            raise UfanetResponseError("UCAMS private camera pagination loop detected")
        if len(seen_pages) >= max_pages:
            raise UfanetResponseError("UCAMS private camera pagination limit exceeded")
        seen_pages.add(current_page)

        payload = await api._async_ucams_json(  # noqa: SLF001 - package-private API boundary
            "POST",
            "/api/v0/cameras/my/",
            json_body={
                "page": current_page,
                "order_by": "addr_asc",
                "page_size": PRIVATE_CAMERA_PAGE_SIZE,
                "fields": list(PRIVATE_CAMERA_FIELDS),
            },
        )
        cameras, next_page = parse_private_camera_page(payload)
        for camera in cameras:
            by_number[camera["number"]] = camera

        if next_page is None:
            break
        current_page = next_page

    return list(by_number.values())


class UfanetPrivateCameraCoordinator(
    DataUpdateCoordinator[dict[str, UcamsPrivateCamera]]
):
    """Refresh the account-wide private UCAMS camera inventory."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: UfanetApi,
        *,
        scan_interval_seconds: int = DEFAULT_SCAN_INTERVAL_SECONDS,
    ) -> None:
        self.api = api
        self.scan_interval_seconds = int(scan_interval_seconds)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_private_cameras",
            update_interval=timedelta(seconds=self.scan_interval_seconds),
        )

    async def _async_update_data(self) -> dict[str, UcamsPrivateCamera]:
        try:
            cameras = await async_get_private_cameras(self.api)
        except UfanetAuthError as err:
            raise ConfigEntryAuthFailed from err
        except UfanetApiError as err:
            raise UpdateFailed("UCAMS private camera inventory update failed") from err
        return {camera["number"]: camera for camera in cameras}

    def diagnostic_summary(self, intercom_numbers: set[str]) -> dict[str, int]:
        """Return aggregate inventory state without camera identifiers or titles."""
        data = self.data if isinstance(self.data, dict) else {}
        cameras = list(data.values())
        return {
            "camera_count": len(cameras),
            "intercom_camera_count": sum(
                camera["number"] in intercom_numbers for camera in cameras
            ),
            "standalone_camera_count": sum(
                camera["number"] not in intercom_numbers for camera in cameras
            ),
            "archive_camera_count": sum(
                (camera.get("dvr_hours") or 0) > 0
                and (
                    camera.get("permission") is None
                    or int(camera["permission"]) <= 20
                )
                for camera in cameras
            ),
            "analytics_camera_count": sum(bool(camera.get("analytics")) for camera in cameras),
            "motion_alarm_camera_count": sum(
                "motion_alarm" in camera.get("analytics", ()) for camera in cameras
            ),
        }
