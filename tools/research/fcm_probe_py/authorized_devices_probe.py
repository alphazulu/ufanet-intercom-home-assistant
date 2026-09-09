"""Read-only inventory probe for Ufanet authorized device sessions."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

import aiohttp

UFANET_BASE_URL = "https://dom.ufanet.ru"
KNOWN_DEVICE_FIELDS = {
    "device_id",
    "title",
    "last_update",
    "is_call_access",
    "os",
    "os_display",
}
SENSITIVE_NAME_PARTS = (
    "token",
    "password",
    "secret",
    "credential",
    "authorization",
    "refresh",
    "access_token",
    "device_id",
    "uuid",
)


class ProbeError(RuntimeError):
    """Expected probe failure with a privacy-safe message."""


def _headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"JWT {access_token.removeprefix('JWT ')}",
        "Accept": "application/json",
    }


async def _request_json(
    session: aiohttp.ClientSession,
    method: str,
    base_url: str,
    path: str,
    *,
    access_token: str | None = None,
    json_body: object | None = None,
) -> tuple[int, Any]:
    headers = _headers(access_token) if access_token else {"Accept": "application/json"}
    kwargs: dict[str, Any] = {
        "headers": headers,
        "timeout": aiohttp.ClientTimeout(total=30),
    }
    if json_body is not None:
        kwargs["json"] = json_body

    try:
        async with session.request(method, f"{base_url}{path}", **kwargs) as response:
            text = await response.text()
            if response.status >= 400:
                raise ProbeError(f"{path} failed: HTTP {response.status}")
            if not text:
                return response.status, None
            try:
                return response.status, json.loads(text)
            except json.JSONDecodeError as exc:
                raise ProbeError(f"{path} returned non-JSON data") from exc
    except aiohttp.ClientError as exc:
        raise ProbeError(f"request failed: {type(exc).__name__}") from exc
    except asyncio.TimeoutError as exc:
        raise ProbeError("request timed out") from exc


async def authenticate(
    session: aiohttp.ClientSession,
    base_url: str,
    contract: str,
    password: str,
) -> str:
    status, payload = await _request_json(
        session,
        "POST",
        base_url,
        "/api/v1/auth/auth_by_contract/",
        json_body={"contract": contract.upper(), "password": password},
    )
    if not isinstance(payload, dict):
        raise ProbeError("Ufanet authentication returned an unexpected schema")
    token = payload.get("token")
    access = token.get("access") if isinstance(token, dict) else None
    if not isinstance(access, str) or not access:
        raise ProbeError("Ufanet authentication response has no access token")
    print(f"[OK] Ufanet authentication: HTTP {status}")
    return access


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _local_time_text(value: Any) -> str | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    return parsed.astimezone().isoformat(timespec="seconds")


def _age_text(value: Any, *, now: datetime | None = None) -> str | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    seconds = (current - parsed.astimezone(timezone.utc)).total_seconds()
    if seconds < 0:
        return "future"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h"
    days = hours // 24
    return f"{days}d"


def _session_ref(device_id: Any) -> str:
    if not isinstance(device_id, str) or not device_id:
        return "auth-missing-id"
    digest = hashlib.sha256(device_id.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"auth-{digest}"


def _safe_text(value: Any, *, max_length: int = 160) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        cleaned = "".join(ch if ord(ch) >= 32 and ord(ch) != 127 else "?" for ch in value)
        if len(cleaned) > max_length:
            return cleaned[:max_length] + "…"
        return cleaned
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return f"<{type(value).__name__}>"
    if len(raw) > max_length:
        return raw[:max_length] + "…"
    return raw


def _safe_extra_value(key: str, value: Any) -> str:
    normalized = key.casefold()
    if any(part in normalized for part in SENSITIVE_NAME_PARTS):
        text = "" if value is None else str(value)
        return f"<redacted len={len(text)}>"
    return _safe_text(value)


def _definitive_title(item: dict[str, Any]) -> str:
    title = item.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    device_id = item.get("device_id")
    if isinstance(device_id, str) and device_id:
        return device_id.split("_", 1)[0]
    return "(no title)"


def _sort_key(item: dict[str, Any]) -> float:
    parsed = _parse_datetime(item.get("last_update"))
    if parsed is None:
        return float("-inf")
    return parsed.timestamp()


def build_inventory(
    payload: Any,
    *,
    show_device_id: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ProbeError("authorized_devices returned an unexpected schema")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ProbeError("authorized_devices response has no data object")
    raw_devices = data.get("device_list")
    if not isinstance(raw_devices, list):
        raise ProbeError("authorized_devices response has no device_list array")

    inventory: list[dict[str, Any]] = []
    for raw in raw_devices:
        if not isinstance(raw, dict):
            continue
        extras = {
            str(key): _safe_extra_value(str(key), value)
            for key, value in raw.items()
            if str(key) not in KNOWN_DEVICE_FIELDS
        }
        row: dict[str, Any] = {
            "session_ref": _session_ref(raw.get("device_id")),
            "title": _definitive_title(raw),
            "last_update": raw.get("last_update"),
            "last_update_local": _local_time_text(raw.get("last_update")),
            "last_update_age": _age_text(raw.get("last_update")),
            "is_call_access": raw.get("is_call_access"),
            "os": raw.get("os"),
            "os_display": raw.get("os_display"),
            "extra_fields": extras,
        }
        if show_device_id:
            row["device_id"] = raw.get("device_id")
        inventory.append(row)

    inventory.sort(
        key=lambda row: _sort_key({"last_update": row.get("last_update")}),
        reverse=True,
    )

    top_extra = {
        str(key): _safe_extra_value(str(key), value)
        for key, value in payload.items()
        if key != "data"
    }
    data_extra = {
        str(key): _safe_extra_value(str(key), value)
        for key, value in data.items()
        if key not in {"device_list", "devices_num_permission"}
    }
    meta = {
        "count": len(inventory),
        "devices_num_permission": data.get("devices_num_permission"),
        "top_level_extra_fields": top_extra,
        "data_extra_fields": data_extra,
        "login_time_available": any(
            any(
                field.casefold() in {"login_time", "login_at", "created_at", "authorized_at"}
                for field in row["extra_fields"]
            )
            for row in inventory
        ),
    }
    return inventory, meta


def print_inventory(inventory: list[dict[str, Any]], meta: dict[str, Any]) -> None:
    print("[RESULT] authorized device inventory")
    print(f"  total: {meta['count']}")
    print(f"  devices_num_permission: {_safe_text(meta.get('devices_num_permission'))}")
    print(
        "  login_time_available: "
        + str(bool(meta.get("login_time_available"))).lower()
    )
    if meta["top_level_extra_fields"]:
        print("  top_level_extra_fields:")
        for key, value in sorted(meta["top_level_extra_fields"].items()):
            print(f"    {key}: {value}")
    if meta["data_extra_fields"]:
        print("  data_extra_fields:")
        for key, value in sorted(meta["data_extra_fields"].items()):
            print(f"    {key}: {value}")

    if not inventory:
        print("  (no authorized devices)")
        return

    for index, row in enumerate(inventory, start=1):
        print()
        print(f"[DEVICE {index}]")
        for key in (
            "session_ref",
            "title",
            "device_id",
            "last_update",
            "last_update_local",
            "last_update_age",
            "is_call_access",
            "os",
            "os_display",
        ):
            if key in row:
                print(f"  {key}: {_safe_text(row.get(key))}")
        extras = row.get("extra_fields")
        if isinstance(extras, dict) and extras:
            print("  extra_fields:")
            for key, value in sorted(extras.items()):
                print(f"    {key}: {value}")
        else:
            print("  extra_fields: (none)")


async def run(args: argparse.Namespace) -> int:
    base_url = args.ufanet_base_url.rstrip("/")
    contract = args.username or os.getenv("UFANET_USERNAME")
    if not contract:
        contract = input("Ufanet contract/login: ").strip()
    password = os.getenv("UFANET_PASSWORD")
    if not password:
        password = getpass.getpass("Ufanet password: ")
    if not contract or not password:
        raise ProbeError("Ufanet contract/login and password are required")

    print(
        "[INFO] Read-only probe: authenticates and requests "
        "POST /api/v4/fcm_device/authorized_devices/ only."
    )
    async with aiohttp.ClientSession() as session:
        access = await authenticate(session, base_url, contract, password)
        status, payload = await _request_json(
            session,
            "POST",
            base_url,
            "/api/v4/fcm_device/authorized_devices/",
            access_token=access,
        )
        print(
            "[OK] POST /api/v4/fcm_device/authorized_devices/: "
            f"HTTP {status}"
        )

    inventory, meta = build_inventory(
        payload,
        show_device_id=args.show_device_id,
    )
    if args.json:
        output = {
            "meta": meta,
            "devices": inventory,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=False))
    else:
        print_inventory(inventory, meta)

    print()
    print(
        "[INFO] last_update is treated as provider activity time; "
        "it is not labeled as login time unless a separate field is actually returned."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only Ufanet authorized-device inventory probe"
    )
    parser.add_argument("--username", help="Ufanet contract/login")
    parser.add_argument(
        "--ufanet-base-url",
        default=UFANET_BASE_URL,
        help="Ufanet API base URL",
    )
    parser.add_argument(
        "--show-device-id",
        action="store_true",
        help=(
            "Also print raw provider device_id values. By default only stable "
            "opaque session_ref values are shown."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the same inventory as JSON",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return asyncio.run(run(args))
    except ProbeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n[ERROR] Interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
