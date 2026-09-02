"""Read-only live probe for privacy-safe UCAMS camera analytics discovery."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

UFANET_BASE_URL = "https://dom.ufanet.ru"
UCAMS_BASE_URL = "https://cloud.ucams.ru"
UCAMS_TOKEN_TTL = 20_800
DEFAULT_HOURS = 24
DEFAULT_LIMIT = 5
DEFAULT_MAX_CAMERAS = 5
SAFE_EVENT_TYPES = ("motion_alarm", "perimeter_security")
CAMERA_FIELDS = ("number", "analytics", "tariff", "timezone")
EVENT_FIELD_ALLOWLIST = frozenset(
    {
        "camera_number",
        "cameraNumber",
        "duration",
        "full_screenshot_url",
        "id",
        "length",
        "protocol",
        "text",
        "time",
        "type",
    }
)
MEDIA_OR_CONTENT_FIELDS = frozenset(
    {
        "crowd_screenshot_url",
        "face_screenshot_url",
        "full_screenshot_url",
        "number",
        "plate_screenshot_url",
        "text",
    }
)


class ProbeError(RuntimeError):
    """Expected probe failure with an intentionally safe message."""


@dataclass(frozen=True)
class CameraCapability:
    """Minimal camera fields retained only for this probe run."""

    camera_number: str
    analytics: tuple[str, ...]
    tariff_present: bool


@dataclass(frozen=True)
class EventSummary:
    """Privacy-safe statistics for one analytics response."""

    returned: int
    valid_timestamps: int
    unexpected_types: int
    unknown_fields: int
    content_fields_present: bool
    schema_fields: tuple[str, ...]
    envelope: str


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
        async with session.request(
            method,
            f"{base_url}{path}",
            **kwargs,
        ) as response:
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


def parse_intercom_camera_numbers(payload: Any) -> tuple[str, ...]:
    if not isinstance(payload, list):
        raise ProbeError("intercom discovery returned an unexpected schema")

    camera_numbers: list[str] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ProbeError("intercom discovery returned an unexpected item schema")
        value = item.get("cctv_number")
        if value is None:
            continue
        if not isinstance(value, (str, int)) or isinstance(value, bool):
            raise ProbeError("intercom discovery returned an invalid camera field")
        camera_number = str(value).strip()
        if camera_number and camera_number not in camera_numbers:
            camera_numbers.append(camera_number)
    return tuple(camera_numbers)


def parse_camera_capabilities(payload: Any) -> list[CameraCapability]:
    if not isinstance(payload, dict):
        raise ProbeError("camera metadata returned an unexpected schema")
    results = payload.get("results")
    if not isinstance(results, list):
        raise ProbeError("camera metadata returned an unexpected results schema")

    cameras: list[CameraCapability] = []
    for item in results:
        if not isinstance(item, dict):
            raise ProbeError("camera metadata returned an unexpected item schema")
        camera_number = item.get("number")
        analytics = item.get("analytics")
        tariff = item.get("tariff")
        if not isinstance(camera_number, (str, int)) or isinstance(camera_number, bool):
            raise ProbeError("camera metadata returned an invalid number field")
        if analytics is None:
            analytics = []
        if not isinstance(analytics, list) or not all(
            isinstance(value, str) for value in analytics
        ):
            raise ProbeError("camera metadata returned an invalid analytics field")
        cameras.append(
            CameraCapability(
                camera_number=str(camera_number),
                analytics=tuple(dict.fromkeys(analytics)),
                tariff_present=tariff is not None,
            )
        )
    return cameras


def _extract_event_items(payload: Any) -> tuple[list[Any], str]:
    if isinstance(payload, list):
        return payload, "list"
    if not isinstance(payload, dict):
        raise ProbeError("analytics events returned an unexpected schema")

    for key in ("results", "events", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value, f"dict.{key}"
        if isinstance(value, dict):
            for nested_key in ("results", "events"):
                nested = value.get(nested_key)
                if isinstance(nested, list):
                    return nested, f"dict.{key}.{nested_key}"

    list_values = [value for value in payload.values() if isinstance(value, list)]
    if len(list_values) == 1:
        return list_values[0], "dict.single_list"
    raise ProbeError("analytics events returned an unknown envelope")


def parse_event_summary(payload: Any, expected_type: str) -> EventSummary:
    if expected_type not in SAFE_EVENT_TYPES:
        raise ProbeError("unsupported analytics event type")
    items, envelope = _extract_event_items(payload)

    valid_timestamps = 0
    unexpected_types = 0
    schema_fields: set[str] = set()
    unknown_fields: set[str] = set()
    content_fields_present = False
    for item in items:
        if not isinstance(item, dict):
            raise ProbeError("analytics events returned an unexpected item schema")
        for field in item:
            if not isinstance(field, str):
                unknown_fields.add("<non-string>")
            elif field in EVENT_FIELD_ALLOWLIST:
                schema_fields.add(field)
            else:
                unknown_fields.add(field)
            if field in MEDIA_OR_CONTENT_FIELDS:
                content_fields_present = True

        timestamp = item.get("time")
        if (
            isinstance(timestamp, (int, float))
            and not isinstance(timestamp, bool)
            and timestamp > 0
        ):
            valid_timestamps += 1

        event_type = item.get("type")
        if event_type is not None and event_type != expected_type:
            unexpected_types += 1

    return EventSummary(
        returned=len(items),
        valid_timestamps=valid_timestamps,
        unexpected_types=unexpected_types,
        unknown_fields=len(unknown_fields),
        content_fields_present=content_fields_present,
        schema_fields=tuple(sorted(schema_fields)),
        envelope=envelope,
    )


def _iso_utc(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


async def audit_ucams_analytics(
    session: aiohttp.ClientSession,
    ufanet_access: str,
    ufanet_base_url: str,
    ucams_base_url: str,
    *,
    hours: int,
    limit: int,
    max_cameras: int,
    now: datetime | None = None,
) -> None:
    intercoms_payload = await _request_json(
        session,
        "GET",
        ufanet_base_url,
        "/api/v0/skud/shared/",
        "GET /api/v0/skud/shared/",
        auth_scheme="JWT",
        auth_token=ufanet_access,
    )
    all_camera_numbers = parse_intercom_camera_numbers(intercoms_payload)
    camera_numbers = all_camera_numbers[:max_cameras]
    print(
        f"[RESULT] intercom cameras: total={len(all_camera_numbers)} "
        f"selected={len(camera_numbers)}"
    )
    if not camera_numbers:
        print("[RESULT] UCAMS analytics: skipped=no_intercom_camera")
        return

    ucams_token = await authenticate_ucams(session, ufanet_access, ucams_base_url)
    metadata_payload = await _request_json(
        session,
        "POST",
        ucams_base_url,
        "/api/v0/cameras/this/",
        "POST /api/v0/cameras/this/",
        auth_scheme="Bearer",
        auth_token=ucams_token,
        json_body={"fields": list(CAMERA_FIELDS), "numbers": list(camera_numbers)},
    )
    cameras = parse_camera_capabilities(metadata_payload)
    selected_numbers = set(camera_numbers)
    cameras = [item for item in cameras if item.camera_number in selected_numbers]
    analytics_present = sum(bool(item.analytics) for item in cameras)
    tariff_present = sum(item.tariff_present for item in cameras)
    safe_counts = {
        event_type: sum(event_type in item.analytics for item in cameras)
        for event_type in SAFE_EVENT_TYPES
    }
    other_analytics = sum(
        len([value for value in item.analytics if value not in SAFE_EVENT_TYPES])
        for item in cameras
    )
    print(
        f"[RESULT] UCAMS camera capabilities: requested={len(camera_numbers)} "
        f"returned={len(cameras)} analytics_present={analytics_present} "
        f"tariff_present={tariff_present} motion_alarm={safe_counts['motion_alarm']} "
        f"perimeter_security={safe_counts['perimeter_security']} "
        f"other_analytics={other_analytics}"
    )

    end_time = now or datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)
    event_checks = 0
    for camera_index, camera in enumerate(cameras, start=1):
        for event_type in SAFE_EVENT_TYPES:
            if event_type not in camera.analytics:
                continue
            payload = await _request_json(
                session,
                "POST",
                ucams_base_url,
                f"/api/v0/analytics/{event_type}/report/",
                f"POST UCAMS {event_type} events [{camera_index}]",
                auth_scheme="Bearer",
                auth_token=ucams_token,
                json_body={
                    "camera_number": camera.camera_number,
                    "start": _iso_utc(start_time),
                    "end": _iso_utc(end_time),
                    "limit": limit,
                    "order_by_date": "desc",
                },
            )
            summary = parse_event_summary(payload, event_type)
            schema = ",".join(summary.schema_fields) or "none"
            print(
                f"[RESULT] {event_type} events [{camera_index}]: "
                f"returned={summary.returned} "
                f"valid_timestamps={summary.valid_timestamps} "
                f"unexpected_types={summary.unexpected_types} "
                f"unknown_fields={summary.unknown_fields} "
                f"content_fields_present="
                f"{'true' if summary.content_fields_present else 'false'} "
                f"envelope={summary.envelope} schema_fields={schema}"
            )
            event_checks += 1

    if not event_checks:
        print("[RESULT] UCAMS analytics events: skipped=no_safe_type_declared")


async def run(args: argparse.Namespace) -> int:
    username = args.username or os.getenv("UFANET_USERNAME")
    if not username:
        username = input("Ufanet contract/login: ").strip()
    password = os.getenv("UFANET_PASSWORD")
    if not password:
        password = getpass.getpass("Ufanet password: ")
    if not username or not password:
        raise ProbeError("Ufanet username/password are required")

    ufanet_base_url = args.ufanet_base_url.rstrip("/")
    ucams_base_url = args.ucams_base_url.rstrip("/")
    async with aiohttp.ClientSession() as session:
        ufanet_access = await authenticate_ufanet(
            session,
            username,
            password,
            ufanet_base_url,
        )
        await audit_ucams_analytics(
            session,
            ufanet_access,
            ufanet_base_url,
            ucams_base_url,
            hours=args.hours,
            limit=args.limit,
            max_cameras=args.max_cameras,
        )
    print("[OK] Read-only UCAMS analytics audit completed")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only privacy-safe UCAMS camera analytics research probe"
    )
    parser.add_argument("--username", help="Ufanet contract/login")
    parser.add_argument(
        "--ufanet-base-url",
        default=UFANET_BASE_URL,
        help="Ufanet API base URL",
    )
    parser.add_argument(
        "--ucams-base-url",
        default=UCAMS_BASE_URL,
        help="UCAMS control API base URL",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=DEFAULT_HOURS,
        help=f"Recent analytics window in hours (default: {DEFAULT_HOURS})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Maximum rows per camera/type (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--max-cameras",
        type=int,
        default=DEFAULT_MAX_CAMERAS,
        help=f"Maximum intercom cameras checked (default: {DEFAULT_MAX_CAMERAS})",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.hours <= 168:
        print("[ERROR] --hours must be between 1 and 168", file=sys.stderr)
        return 2
    if not 1 <= args.limit <= 25:
        print("[ERROR] --limit must be between 1 and 25", file=sys.stderr)
        return 2
    if not 1 <= args.max_cameras <= 10:
        print("[ERROR] --max-cameras must be between 1 and 10", file=sys.stderr)
        return 2
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted")
        return 130
    except ProbeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
