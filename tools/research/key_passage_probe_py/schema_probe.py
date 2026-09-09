"""Privacy-safe schema probe for Ufanet physical-key passage history.

This probe intentionally never prints provider key IDs, external IDs, key names,
passage times, raw response bodies, access tokens or credentials. It compares the
unfiltered history request with the official Android client's single-key filter,
which uses SkudKey.external_id rather than the internal key id.
"""

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
PAGE_SIZE = 5


class ProbeError(RuntimeError):
    """Expected probe failure with a privacy-safe message."""


@dataclass(frozen=True)
class SafeResponse:
    status: int
    payload: Any | None
    content_type: str | None
    body_length: int


def _headers(token: str) -> dict[str, str]:
    raw = token.removeprefix("JWT ")
    return {"Authorization": f"JWT {raw}", "Accept": "application/json"}


async def _request(
    session: aiohttp.ClientSession,
    method: str,
    base_url: str,
    path: str,
    *,
    token: str | None = None,
    json_body: Any = None,
) -> SafeResponse:
    headers = _headers(token) if token else {"Accept": "application/json"}
    try:
        async with session.request(
            method,
            f"{base_url}{path}",
            headers=headers,
            json=json_body,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            text = await response.text()
            payload: Any | None = None
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                pass
            return SafeResponse(
                status=response.status,
                payload=payload,
                content_type=response.headers.get("Content-Type"),
                body_length=len(text.encode("utf-8", errors="replace")),
            )
    except aiohttp.ClientError as exc:
        raise ProbeError(f"request failed: {type(exc).__name__}") from exc
    except asyncio.TimeoutError as exc:
        raise ProbeError("request timed out") from exc


async def _authenticate(
    session: aiohttp.ClientSession,
    base_url: str,
    username: str,
    password: str,
) -> str:
    response = await _request(
        session,
        "POST",
        base_url,
        "/api/v1/auth/auth_by_contract/",
        json_body={"contract": username.upper(), "password": password},
    )
    if response.status >= 400:
        raise ProbeError(f"authentication failed: HTTP {response.status}")
    payload = response.payload
    token = payload.get("token") if isinstance(payload, dict) else None
    access = token.get("access") if isinstance(token, dict) else None
    if not isinstance(access, str) or not access:
        raise ProbeError("authentication response has no access token")
    print(f"[OK] Ufanet authentication: HTTP {response.status}")
    return access


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def _safe_envelope_summary(response: SafeResponse) -> str:
    payload = response.payload
    if not isinstance(payload, dict):
        return (
            f"http={response.status} envelope={_type_name(payload)} "
            f"content_type_present={'true' if response.content_type else 'false'} "
            f"body_bytes={response.body_length}"
        )

    fields = sorted(str(key) for key in payload)
    field_types = ",".join(
        f"{field}:{_type_name(payload.get(field))}" for field in fields
    )
    results = payload.get("results")
    results_len = len(results) if isinstance(results, list) else -1
    first_fields = ""
    first_types = ""
    if isinstance(results, list) and results and isinstance(results[0], dict):
        first_fields_list = sorted(str(key) for key in results[0])
        first_fields = ",".join(first_fields_list)
        first_types = ",".join(
            f"{field}:{_type_name(results[0].get(field))}"
            for field in first_fields_list
        )
    return (
        f"http={response.status} envelope=dict top_fields={','.join(fields)} "
        f"field_types={field_types} results_len={results_len} "
        f"first_item_fields={first_fields or '-'} "
        f"first_item_types={first_types or '-'} body_bytes={response.body_length}"
    )


def _android_compatible_contract(response: SafeResponse) -> str:
    """Validate the shape using Gson-compatible numeric-string coercion."""
    payload = response.payload
    if response.status >= 400:
        return f"http_error_{response.status}"
    if not isinstance(payload, dict):
        return "envelope_not_dict"
    for field in ("count", "current_page", "page_count", "page_size"):
        value = payload.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return f"invalid_{field}_{_type_name(value)}"
    results = payload.get("results")
    if not isinstance(results, list):
        return "results_not_list"
    for item in results:
        if not isinstance(item, dict):
            return "item_not_dict"
        key_value = item.get("key")
        if isinstance(key_value, bool):
            return "invalid_key_bool"
        if isinstance(key_value, int):
            pass
        elif isinstance(key_value, str) and key_value.strip().isdigit():
            pass
        else:
            return f"invalid_key_{_type_name(key_value)}"
        if not isinstance(item.get("key_name"), str):
            return f"invalid_key_name_{_type_name(item.get('key_name'))}"
        timestamp = item.get("time_passage")
        if not isinstance(timestamp, int) or isinstance(timestamp, bool) or timestamp <= 0:
            return f"invalid_time_passage_{_type_name(timestamp)}"
    return "ok"


def _extract_supported_skuds(payload: Any) -> list[int]:
    result = payload.get("result") if isinstance(payload, dict) else None
    rows = result.get("intercoms") if isinstance(result, dict) else None
    if not isinstance(rows, list):
        raise ProbeError("intercom capability response has unexpected schema")
    values: list[int] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        skud_id = item.get("id")
        if (
            isinstance(skud_id, int)
            and not isinstance(skud_id, bool)
            and item.get("has_key_recording_support") is True
        ):
            values.append(skud_id)
    return values


def _extract_keys(payload: Any) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, dict) else None
    rows = data.get("keys") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ProbeError("physical-key response has unexpected schema")
    safe: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        key_id = item.get("id")
        external_id = item.get("external_id")
        devices = item.get("devices")
        if (
            not isinstance(key_id, int)
            or isinstance(key_id, bool)
            or not isinstance(external_id, str)
            or not external_id
            or not isinstance(devices, list)
        ):
            continue
        normalized_devices: list[int] = []
        for raw in devices:
            try:
                normalized_devices.append(int(raw))
            except (TypeError, ValueError):
                pass
        safe.append(
            {
                "key_id": key_id,
                "external_id": external_id,
                "devices": tuple(normalized_devices),
            }
        )
    return safe


async def run(args: argparse.Namespace) -> int:
    username = args.username or os.getenv("UFANET_USERNAME") or input("Ufanet contract/login: ").strip()
    password = os.getenv("UFANET_PASSWORD") or getpass.getpass("Ufanet password: ")
    if not username or not password:
        raise ProbeError("Ufanet username/password are required")

    base_url = args.ufanet_base_url.rstrip("/")
    async with aiohttp.ClientSession() as session:
        token = await _authenticate(session, base_url, username, password)

        intercom_response = await _request(
            session,
            "POST",
            base_url,
            "/api/v0/intercoms/",
            token=token,
            json_body={
                "page": 1,
                "page_size": 10,
                "filters": {"has_key_recording_support": True},
            },
        )
        if intercom_response.status >= 400:
            raise ProbeError(f"intercom capability request failed: HTTP {intercom_response.status}")
        supported = _extract_supported_skuds(intercom_response.payload)

        key_response = await _request(
            session,
            "POST",
            base_url,
            "/api/v4/key/list/",
            token=token,
        )
        if key_response.status >= 400:
            raise ProbeError(f"physical-key list failed: HTTP {key_response.status}")
        keys = _extract_keys(key_response.payload)

        target_skud = args.skud_id
        if target_skud is None:
            target_skud = next(
                (
                    skud_id
                    for skud_id in supported
                    if any(skud_id in item["devices"] for item in keys)
                ),
                None,
            )
        if target_skud is None:
            print("[RESULT] passage schema audit: skipped=no_supported_intercom_with_registered_key")
            return 0

        target_key = next(
            (item for item in keys if int(target_skud) in item["devices"]),
            None,
        )
        if target_key is None:
            raise ProbeError("selected intercom has no registered physical key")

        print(
            "[RESULT] target: "
            f"supported=true registered_keys_for_intercom="
            f"{sum(int(target_skud) in item['devices'] for item in keys)}"
        )

        path = f"/api/v4/key/skud/{int(target_skud)}/key/pass_history/"
        unfiltered = await _request(
            session,
            "POST",
            base_url,
            path,
            token=token,
            json_body={"page": 0, "page_size": PAGE_SIZE},
        )
        print(f"[RESULT] unfiltered shape: {_safe_envelope_summary(unfiltered)}")
        print(
            "[RESULT] unfiltered android_compatible_contract="
            f"{_android_compatible_contract(unfiltered)}"
        )

        filtered = await _request(
            session,
            "POST",
            base_url,
            path,
            token=token,
            json_body={
                "page": 0,
                "page_size": PAGE_SIZE,
                "filters": {"key": target_key["external_id"]},
            },
        )
        print(
            "[RESULT] single-key external-id filtered shape: "
            f"{_safe_envelope_summary(filtered)}"
        )
        print(
            "[RESULT] single-key external-id android_compatible_contract="
            f"{_android_compatible_contract(filtered)}"
        )

        print("[OK] Privacy-safe key passage schema audit completed")
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Privacy-safe Ufanet key-passage response schema audit"
    )
    parser.add_argument("--username", help="Ufanet contract/login")
    parser.add_argument("--skud-id", type=int, help="Optional target intercom ID")
    parser.add_argument(
        "--ufanet-base-url",
        default=UFANET_BASE_URL,
        help="Ufanet API base URL",
    )
    return parser


def main() -> int:
    try:
        return asyncio.run(run(build_parser().parse_args()))
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted")
        return 130
    except ProbeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
