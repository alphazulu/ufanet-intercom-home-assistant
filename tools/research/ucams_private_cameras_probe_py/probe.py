"""Read-only privacy-safe probe for UCAMS private camera inventory."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sys
from dataclasses import dataclass
from typing import Any

import aiohttp

UFANET_BASE_URL = "https://dom.ufanet.ru"
UCAMS_BASE_URL = "https://cloud.ucams.ru"
UCAMS_TOKEN_TTL = 20_800
PAGE_SIZE = 50
MAX_PAGES_DEFAULT = 100
CAMERA_FIELDS = (
    "number",
    "address",
    "title",
    "timezone",
    "analytics",
    "blocking_lvl",
    "streams_count",
    "is_public",
    "inactivity_period",
    "server",
    "tariff",
    "token_l",
    "token_r",
    "permission",
    "is_fav",
)


class ProbeError(RuntimeError):
    """Expected probe failure with an intentionally safe message."""


@dataclass(frozen=True)
class CameraSummary:
    """Privacy-safe camera capabilities retained by the probe."""

    intercom_match: bool
    title_present: bool
    address_present: bool
    timezone_present: bool
    streams_count: int | None
    analytics_count: int
    motion_alarm: bool
    perimeter_security: bool
    tariff_present: bool
    archive_hours: int | None
    server_vendor_present: bool
    permission_present: bool
    is_fav: bool | None
    is_public: bool | None
    blocking_lvl_present: bool
    inactivity_period_present: bool


def _authorization_headers(scheme: str, token: str) -> dict[str, str]:
    clean_token = token.removeprefix("JWT ").removeprefix("Bearer ")
    return {
        "Authorization": f"{scheme} {clean_token}",
        "Accept": "application/json",
    }


async def _request_json(
    session: aiohttp.ClientSession,
    method: str,
    base_url: str,
    path: str,
    label: str,
    *,
    auth_scheme: str | None = None,
    auth_token: str | None = None,
    params: dict[str, object] | None = None,
    json_body: object | None = None,
) -> Any:
    headers = {"Accept": "application/json"}
    if auth_scheme is not None or auth_token is not None:
        if not auth_scheme or not auth_token:
            raise ProbeError("request authentication parameters are incomplete")
        headers = _authorization_headers(auth_scheme, auth_token)

    kwargs: dict[str, Any] = {
        "headers": headers,
        "timeout": aiohttp.ClientTimeout(total=30),
    }
    if params is not None:
        kwargs["params"] = params
    if json_body is not None:
        kwargs["json"] = json_body

    try:
        async with session.request(method, f"{base_url}{path}", **kwargs) as response:
            text = await response.text()
            if response.status >= 400:
                raise ProbeError(f"{label} failed: HTTP {response.status}")
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ProbeError(f"{label} returned invalid JSON") from exc
            print(f"[OK] {label}: HTTP {response.status}")
            return payload
    except aiohttp.ClientError as exc:
        raise ProbeError(f"{label} request failed: {type(exc).__name__}") from exc
    except asyncio.TimeoutError as exc:
        raise ProbeError(f"{label} request timed out") from exc


async def authenticate_ufanet(
    session: aiohttp.ClientSession,
    username: str,
    password: str,
    base_url: str,
) -> str:
    payload = await _request_json(
        session,
        "POST",
        base_url,
        "/api/v1/auth/auth_by_contract/",
        "Ufanet authentication",
        json_body={"contract": username.upper(), "password": password},
    )
    if not isinstance(payload, dict):
        raise ProbeError("Ufanet authentication returned an unexpected schema")
    token = payload.get("token")
    access = token.get("access") if isinstance(token, dict) else None
    if not isinstance(access, str) or not access:
        raise ProbeError("Ufanet authentication response has no access token")
    return access


async def authenticate_ucams(
    session: aiohttp.ClientSession,
    ufanet_access: str,
    base_url: str,
) -> str:
    payload = await _request_json(
        session,
        "POST",
        base_url,
        "/api/v0/auth/",
        "UCAMS authentication",
        auth_scheme="JWT",
        auth_token=ufanet_access,
        params={"ttl": UCAMS_TOKEN_TTL},
    )
    if not isinstance(payload, dict):
        raise ProbeError("UCAMS authentication returned an unexpected schema")
    token = payload.get("token")
    if not isinstance(token, str) or not token:
        raise ProbeError("UCAMS authentication response has no token")
    return token


def parse_intercom_camera_numbers(payload: Any) -> set[str]:
    if not isinstance(payload, list):
        raise ProbeError("intercom discovery returned an unexpected schema")
    result: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            raise ProbeError("intercom discovery returned an unexpected item schema")
        value = item.get("cctv_number")
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise ProbeError("intercom discovery returned an invalid camera field")
        value_s = str(value).strip()
        if value_s:
            result.add(value_s)
    return result


def _parse_optional_nonnegative_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 0 else None


def _parse_optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def summarize_camera(item: Any, intercom_numbers: set[str]) -> tuple[str, CameraSummary]:
    if not isinstance(item, dict):
        raise ProbeError("private camera inventory returned an unexpected item schema")

    number = item.get("number")
    if isinstance(number, bool) or not isinstance(number, (str, int)):
        raise ProbeError("private camera inventory returned an invalid number field")
    number_s = str(number).strip()
    if not number_s:
        raise ProbeError("private camera inventory returned an empty number field")

    analytics = item.get("analytics")
    if analytics is None:
        analytics_list: list[str] = []
    elif isinstance(analytics, list) and all(isinstance(v, str) for v in analytics):
        analytics_list = list(dict.fromkeys(analytics))
    else:
        raise ProbeError("private camera inventory returned an invalid analytics field")

    tariff = item.get("tariff")
    tariff_dict = tariff if isinstance(tariff, dict) else None
    archive_hours = (
        _parse_optional_nonnegative_int(tariff_dict.get("dvr_hours"))
        if tariff_dict is not None
        else None
    )
    server = item.get("server")
    server_dict = server if isinstance(server, dict) else None
    vendor = server_dict.get("vendor") if server_dict is not None else None

    summary = CameraSummary(
        intercom_match=number_s in intercom_numbers,
        title_present=isinstance(item.get("title"), str) and bool(item["title"].strip()),
        address_present=isinstance(item.get("address"), str) and bool(item["address"].strip()),
        timezone_present=isinstance(item.get("timezone"), str) and bool(item["timezone"].strip()),
        streams_count=_parse_optional_nonnegative_int(item.get("streams_count")),
        analytics_count=len(analytics_list),
        motion_alarm="motion_alarm" in analytics_list,
        perimeter_security="perimeter_security" in analytics_list,
        tariff_present=tariff is not None,
        archive_hours=archive_hours,
        server_vendor_present=isinstance(vendor, str) and bool(vendor.strip()),
        permission_present=item.get("permission") is not None,
        is_fav=_parse_optional_bool(item.get("is_fav")),
        is_public=_parse_optional_bool(item.get("is_public")),
        blocking_lvl_present=item.get("blocking_lvl") is not None,
        inactivity_period_present=item.get("inactivity_period") is not None,
    )
    return number_s, summary


def parse_page(
    payload: Any,
    intercom_numbers: set[str],
) -> tuple[list[tuple[str, CameraSummary]], int | None]:
    if not isinstance(payload, dict):
        raise ProbeError("private camera inventory returned an unexpected schema")
    results = payload.get("results")
    page = payload.get("page")
    if not isinstance(results, list):
        raise ProbeError("private camera inventory has no results list")
    if not isinstance(page, dict):
        raise ProbeError("private camera inventory has no page object")

    parsed = [summarize_camera(item, intercom_numbers) for item in results]
    next_page = page.get("next")
    if next_page is None:
        return parsed, None
    if isinstance(next_page, bool) or not isinstance(next_page, int) or next_page < 1:
        raise ProbeError("private camera inventory returned an invalid page.next")
    return parsed, next_page


async def load_private_inventory(
    session: aiohttp.ClientSession,
    ucams_token: str,
    ucams_base_url: str,
    intercom_numbers: set[str],
    *,
    max_pages: int,
) -> tuple[list[CameraSummary], int]:
    current_page = 1
    seen_pages: set[int] = set()
    seen_numbers: set[str] = set()
    summaries: list[CameraSummary] = []
    pages_loaded = 0

    while True:
        if current_page in seen_pages:
            raise ProbeError("private camera pagination loop detected")
        if pages_loaded >= max_pages:
            raise ProbeError("private camera pagination exceeded max-pages")
        seen_pages.add(current_page)

        payload = await _request_json(
            session,
            "POST",
            ucams_base_url,
            "/api/v0/cameras/my/",
            f"POST /api/v0/cameras/my/ page {current_page}",
            auth_scheme="Bearer",
            auth_token=ucams_token,
            json_body={
                "page": current_page,
                "order_by": "addr_asc",
                "page_size": PAGE_SIZE,
                "fields": list(CAMERA_FIELDS),
            },
        )
        cameras, next_page = parse_page(payload, intercom_numbers)
        pages_loaded += 1
        for number, summary in cameras:
            if number in seen_numbers:
                continue
            seen_numbers.add(number)
            summaries.append(summary)

        if next_page is None:
            break
        current_page = next_page

    return summaries, pages_loaded


def print_inventory_summary(
    cameras: list[CameraSummary],
    pages_loaded: int,
    intercom_count: int,
) -> None:
    intercom_matches = sum(c.intercom_match for c in cameras)
    archive_count = sum((c.archive_hours or 0) > 0 for c in cameras)
    analytics_count = sum(c.analytics_count > 0 for c in cameras)
    fav_count = sum(c.is_fav is True for c in cameras)
    public_count = sum(c.is_public is True for c in cameras)
    print(
        f"[RESULT] private cameras: total={len(cameras)} pages={pages_loaded} "
        f"known_intercom_cameras={intercom_count} intercom_matches={intercom_matches} "
        f"non_intercom_cameras={max(0, len(cameras) - intercom_matches)} "
        f"with_archive={archive_count} with_analytics={analytics_count} "
        f"favorites={fav_count} marked_public={public_count}"
    )

    for index, camera in enumerate(cameras, start=1):
        archive_hours = "unknown" if camera.archive_hours is None else str(camera.archive_hours)
        streams_count = "unknown" if camera.streams_count is None else str(camera.streams_count)
        print(
            f"[RESULT] camera[{index}]: intercom_match={'true' if camera.intercom_match else 'false'} "
            f"title_present={'true' if camera.title_present else 'false'} "
            f"address_present={'true' if camera.address_present else 'false'} "
            f"timezone_present={'true' if camera.timezone_present else 'false'} "
            f"streams_count={streams_count} analytics_count={camera.analytics_count} "
            f"motion_alarm={'true' if camera.motion_alarm else 'false'} "
            f"perimeter_security={'true' if camera.perimeter_security else 'false'} "
            f"tariff_present={'true' if camera.tariff_present else 'false'} "
            f"archive_hours={archive_hours} "
            f"server_vendor_present={'true' if camera.server_vendor_present else 'false'} "
            f"permission_present={'true' if camera.permission_present else 'false'} "
            f"is_fav={'unknown' if camera.is_fav is None else str(camera.is_fav).lower()} "
            f"is_public={'unknown' if camera.is_public is None else str(camera.is_public).lower()} "
            f"blocking_lvl_present={'true' if camera.blocking_lvl_present else 'false'} "
            f"inactivity_period_present={'true' if camera.inactivity_period_present else 'false'}"
        )


async def run(args: argparse.Namespace) -> None:
    username = (
        args.username
        or os.getenv("UFANET_CONTRACT")
        or input("Ufanet contract/login: ").strip()
    )
    if not username:
        raise ProbeError("Ufanet contract/login is required")
    password = os.getenv("UFANET_PASSWORD") or getpass.getpass("Ufanet password: ")
    if not password:
        raise ProbeError("Ufanet password is required")

    async with aiohttp.ClientSession() as session:
        ufanet_access = await authenticate_ufanet(
            session,
            username,
            password,
            args.ufanet_base_url,
        )
        intercom_payload = await _request_json(
            session,
            "GET",
            args.ufanet_base_url,
            "/api/v0/skud/shared/",
            "GET /api/v0/skud/shared/",
            auth_scheme="JWT",
            auth_token=ufanet_access,
        )
        intercom_numbers = parse_intercom_camera_numbers(intercom_payload)
        print(f"[RESULT] known intercom cameras: total={len(intercom_numbers)}")

        ucams_token = await authenticate_ucams(
            session,
            ufanet_access,
            args.ucams_base_url,
        )
        cameras, pages_loaded = await load_private_inventory(
            session,
            ucams_token,
            args.ucams_base_url,
            intercom_numbers,
            max_pages=args.max_pages,
        )
        print_inventory_summary(cameras, pages_loaded, len(intercom_numbers))
        print("[OK] Read-only UCAMS private camera inventory audit completed")
        print(
            "[PRIVACY] Camera numbers, titles, addresses, tokens and server domains "
            "were not printed"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only privacy-safe probe for the UCAMS private camera inventory "
            "used by the official app."
        ),
    )
    parser.add_argument(
        "--username",
        help="Ufanet contract/login; password is never accepted as a CLI argument",
    )
    parser.add_argument("--ufanet-base-url", default=UFANET_BASE_URL)
    parser.add_argument("--ucams-base-url", default=UCAMS_BASE_URL)
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES_DEFAULT)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.max_pages < 1:
        parser.error("--max-pages must be >= 1")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\n[ERROR] interrupted", file=sys.stderr)
        return 130
    except ProbeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
