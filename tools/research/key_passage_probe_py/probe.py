"""Read-only live probe for Ufanet physical keys and passage history."""

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
DEFAULT_PAGE_SIZE = 5
DEFAULT_MAX_INTERCOMS = 10


class ProbeError(RuntimeError):
    """Expected probe failure with an intentionally safe message."""


@dataclass(frozen=True)
class IntercomCapability:
    """Only the non-display fields required by the probe."""

    skud_id: int
    has_key_recording_support: bool | None


@dataclass(frozen=True)
class PassageSummary:
    """Privacy-safe passage response statistics."""

    total: int
    returned: int
    valid_timestamps: int
    schema_fields: tuple[str, ...]


def _auth_headers(access_token: str) -> dict[str, str]:
    token = access_token.removeprefix("JWT ")
    return {
        "Authorization": f"JWT {token}",
        "Accept": "application/json",
    }


async def _request_json(
    session: aiohttp.ClientSession,
    method: str,
    base_url: str,
    path: str,
    label: str,
    *,
    access_token: str | None = None,
    json_body: object | None = None,
) -> Any:
    kwargs: dict[str, Any] = {
        "headers": _auth_headers(access_token)
        if access_token
        else {"Accept": "application/json"},
        "timeout": aiohttp.ClientTimeout(total=30),
    }
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


async def authenticate(
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


def parse_features(payload: Any) -> tuple[str, ...]:
    if not isinstance(payload, dict):
        raise ProbeError("features returned an unexpected schema")
    data = payload.get("data")
    features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(features, list) or not all(
        isinstance(item, str) for item in features
    ):
        raise ProbeError("features returned an unexpected schema")
    return tuple(features)


def parse_intercoms(payload: Any) -> list[IntercomCapability]:
    if not isinstance(payload, dict):
        raise ProbeError("intercom discovery returned an unexpected schema")
    result = payload.get("result")
    raw_intercoms = result.get("intercoms") if isinstance(result, dict) else None
    if not isinstance(raw_intercoms, list):
        raise ProbeError("intercom discovery returned an unexpected schema")

    intercoms: list[IntercomCapability] = []
    for item in raw_intercoms:
        if not isinstance(item, dict):
            raise ProbeError("intercom discovery returned an unexpected item schema")
        skud_id = item.get("id")
        support = item.get("has_key_recording_support")
        if not isinstance(skud_id, int) or isinstance(skud_id, bool):
            raise ProbeError("intercom discovery returned an invalid id type")
        if support is not None and not isinstance(support, bool):
            raise ProbeError("intercom discovery returned an invalid capability type")
        intercoms.append(IntercomCapability(skud_id, support))
    return intercoms


def parse_keys(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ProbeError("key list returned an unexpected schema")
    data = payload.get("data")
    raw_keys = data.get("keys") if isinstance(data, dict) else None
    if not isinstance(raw_keys, list):
        raise ProbeError("key list returned an unexpected schema")

    required = {
        "id": int,
        "external_id": str,
        "name": str,
        "create_date": int,
        "devices": list,
    }
    keys: list[dict[str, Any]] = []
    for item in raw_keys:
        if not isinstance(item, dict):
            raise ProbeError("key list returned an unexpected item schema")
        for field, expected_type in required.items():
            value = item.get(field)
            if not isinstance(value, expected_type) or (
                expected_type is int and isinstance(value, bool)
            ):
                raise ProbeError(f"key list returned an invalid {field} field")
        if not all(isinstance(device, str) for device in item["devices"]):
            raise ProbeError("key list returned an invalid devices field")
        keys.append(item)
    return keys


def parse_passages(payload: Any) -> PassageSummary:
    if not isinstance(payload, dict):
        raise ProbeError("passage history returned an unexpected schema")

    for field in ("count", "current_page", "page_count", "page_size"):
        value = payload.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ProbeError(f"passage history returned an invalid {field} field")

    results = payload.get("results")
    if not isinstance(results, list):
        raise ProbeError("passage history returned an unexpected results schema")

    expected_fields = ("key", "key_name", "time_passage")
    valid_timestamps = 0
    for item in results:
        if not isinstance(item, dict):
            raise ProbeError("passage history returned an unexpected item schema")
        key_id = item.get("key")
        key_name = item.get("key_name")
        timestamp = item.get("time_passage")
        if not isinstance(key_id, int) or isinstance(key_id, bool):
            raise ProbeError("passage history returned an invalid key field")
        if not isinstance(key_name, str):
            raise ProbeError("passage history returned an invalid key_name field")
        if not isinstance(timestamp, int) or isinstance(timestamp, bool):
            raise ProbeError("passage history returned an invalid time_passage field")
        if timestamp > 0:
            valid_timestamps += 1

    return PassageSummary(
        total=payload["count"],
        returned=len(results),
        valid_timestamps=valid_timestamps,
        schema_fields=expected_fields,
    )


def count_linked_keys(keys: list[dict[str, Any]], skud_id: int) -> int:
    target = str(skud_id)
    return sum(target in item["devices"] for item in keys)


async def audit_key_passages(
    session: aiohttp.ClientSession,
    access_token: str,
    base_url: str,
    *,
    page_size: int,
    max_intercoms: int,
) -> None:
    features_payload = await _request_json(
        session,
        "GET",
        base_url,
        "/api/v4/skud/features/",
        "GET /api/v4/skud/features/",
        access_token=access_token,
    )
    features = parse_features(features_payload)
    print(
        f"[RESULT] account features: count={len(features)} "
        f"keys_available={'true' if 'keys' in features else 'false'}"
    )

    intercoms_payload = await _request_json(
        session,
        "POST",
        base_url,
        "/api/v0/intercoms/",
        "POST /api/v0/intercoms/",
        access_token=access_token,
        json_body={"page": 0, "page_size": 100, "filters": {}},
    )
    intercoms = parse_intercoms(intercoms_payload)
    supported = [item for item in intercoms if item.has_key_recording_support is True]
    unknown = sum(item.has_key_recording_support is None for item in intercoms)
    print(
        f"[RESULT] intercom capabilities: total={len(intercoms)} "
        f"key_recording_supported={len(supported)} unknown={unknown}"
    )

    keys_payload = await _request_json(
        session,
        "POST",
        base_url,
        "/api/v4/key/list/",
        "POST /api/v4/key/list/",
        access_token=access_token,
    )
    keys = parse_keys(keys_payload)
    print(
        "[RESULT] physical keys: "
        f"count={len(keys)} schema_fields=create_date,devices,external_id,id,name"
    )

    targets = supported[:max_intercoms]
    if not targets:
        print("[RESULT] passage history: skipped=no_supported_intercom")
        return
    if len(supported) > len(targets):
        print(
            f"[INFO] Passage checks limited to {len(targets)} of {len(supported)} "
            "supported intercoms"
        )

    for index, intercom in enumerate(targets, start=1):
        passage_payload = await _request_json(
            session,
            "POST",
            base_url,
            f"/api/v4/key/skud/{intercom.skud_id}/key/pass_history/",
            f"POST passage history [{index}]",
            access_token=access_token,
            json_body={"page": 0, "page_size": page_size},
        )
        summary = parse_passages(passage_payload)
        linked_keys = count_linked_keys(keys, intercom.skud_id)
        print(
            f"[RESULT] passage history [{index}]: total={summary.total} "
            f"returned={summary.returned} valid_timestamps={summary.valid_timestamps} "
            f"linked_keys={linked_keys} "
            f"schema_fields={','.join(summary.schema_fields)}"
        )


async def run(args: argparse.Namespace) -> int:
    username = args.username or os.getenv("UFANET_USERNAME")
    if not username:
        username = input("Ufanet contract/login: ").strip()
    password = os.getenv("UFANET_PASSWORD")
    if not password:
        password = getpass.getpass("Ufanet password: ")
    if not username or not password:
        raise ProbeError("Ufanet username/password are required")

    base_url = args.ufanet_base_url.rstrip("/")
    async with aiohttp.ClientSession() as session:
        access_token = await authenticate(session, username, password, base_url)
        await audit_key_passages(
            session,
            access_token,
            base_url,
            page_size=args.page_size,
            max_intercoms=args.max_intercoms,
        )
    print("[OK] Read-only key and passage audit completed")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only Ufanet physical-key and passage-history research probe"
    )
    parser.add_argument("--username", help="Ufanet contract/login")
    parser.add_argument(
        "--ufanet-base-url",
        default=UFANET_BASE_URL,
        help="Ufanet API base URL",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help=f"Latest passage rows requested per intercom (default: {DEFAULT_PAGE_SIZE})",
    )
    parser.add_argument(
        "--max-intercoms",
        type=int,
        default=DEFAULT_MAX_INTERCOMS,
        help=(
            "Maximum supported intercoms queried for passage history "
            f"(default: {DEFAULT_MAX_INTERCOMS})"
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.page_size <= 25:
        print("[ERROR] --page-size must be between 1 and 25", file=sys.stderr)
        return 2
    if not 1 <= args.max_intercoms <= 50:
        print("[ERROR] --max-intercoms must be between 1 and 50", file=sys.stderr)
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
