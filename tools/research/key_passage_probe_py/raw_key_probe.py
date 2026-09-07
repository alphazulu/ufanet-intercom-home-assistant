"""Read-only raw inspector for Ufanet physical-key records.

This probe intentionally prints every field returned for each physical key so a
local operator can compare provider values with markings printed on the physical
key. It never performs enrollment, rename, delete, door-open, or other writes.

WARNING: output contains access-control identifiers. Do not publish it in GitHub
issues, logs, screenshots, or support bundles.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Iterable

import aiohttp

UFANET_BASE_URL = "https://dom.ufanet.ru"


class ProbeError(RuntimeError):
    """Expected probe failure with a deliberately short message."""


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


def _extract_keys(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ProbeError("key list returned an unexpected schema")
    data = payload.get("data")
    raw_keys = data.get("keys") if isinstance(data, dict) else None
    if not isinstance(raw_keys, list):
        raise ProbeError("key list returned an unexpected schema")

    keys: list[dict[str, Any]] = []
    for index, item in enumerate(raw_keys, start=1):
        if not isinstance(item, dict):
            raise ProbeError(f"key #{index} is not a JSON object")
        keys.append(item)
    return keys


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
        return "object"
    return type(value).__name__


def _flatten(value: Any, path: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        if not value:
            yield path or "<root>", value
            return
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield from _flatten(child, child_path)
        return
    if isinstance(value, list):
        if not value:
            yield path, value
            return
        for index, child in enumerate(value):
            yield from _flatten(child, f"{path}[{index}]")
        return
    yield path, value


def _format_scalar(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False)


def _looks_like_integer_text(value: str) -> bool:
    stripped = value.strip()
    return bool(stripped) and stripped.isdigit()


def _looks_like_hex_text(value: str) -> bool:
    stripped = value.strip().lower().removeprefix("0x")
    if not stripped or len(stripped) > 32:
        return False
    return all(char in "0123456789abcdef" for char in stripped) and any(
        char in "abcdef" for char in stripped
    )


def _candidate_forms(path: str, value: Any) -> list[str]:
    """Return harmless display conversions useful when comparing printed numbers."""
    rows: list[str] = []

    if isinstance(value, bool) or value is None:
        return rows

    if isinstance(value, int):
        rows.append(f"{path}: decimal={value} hex=0x{value:X}")
        return rows

    if not isinstance(value, str):
        return rows

    stripped = value.strip()
    if not stripped:
        return rows

    if _looks_like_integer_text(stripped):
        try:
            number = int(stripped, 10)
        except ValueError:
            return rows
        rows.append(
            f"{path}: raw={json.dumps(value, ensure_ascii=False)} "
            f"decimal={number} hex=0x{number:X} digits={len(stripped)}"
        )
        return rows

    if _looks_like_hex_text(stripped):
        normalized = stripped.lower().removeprefix("0x")
        try:
            number = int(normalized, 16)
        except ValueError:
            return rows
        rows.append(
            f"{path}: raw={json.dumps(value, ensure_ascii=False)} "
            f"hex=0x{normalized.upper()} decimal={number} chars={len(normalized)}"
        )

    return rows


def _timestamp_hint(path: str, value: Any) -> str | None:
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    lowered = path.lower()
    if not any(token in lowered for token in ("date", "time", "created", "updated")):
        return None
    if value < 0 or value > 253_402_300_799:
        return None
    try:
        rendered = datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return None
    return f"{path}: unix={value} UTC={rendered}"


def print_key(index: int, key: dict[str, Any], *, show_candidates: bool) -> None:
    print()
    print("=" * 78)
    print(f"KEY #{index}")
    print("=" * 78)
    print("[RAW JSON]")
    print(json.dumps(key, ensure_ascii=False, indent=2, sort_keys=True))

    print()
    print("[FIELDS]")
    flattened = list(_flatten(key))
    for path, value in flattened:
        print(f"{path:<42} type={_type_name(value):<7} value={_format_scalar(value)}")

    timestamp_hints = [
        hint
        for path, value in flattened
        if (hint := _timestamp_hint(path, value)) is not None
    ]
    if timestamp_hints:
        print()
        print("[TIMESTAMP HINTS]")
        for hint in timestamp_hints:
            print(hint)

    if show_candidates:
        candidates: list[str] = []
        for path, value in flattened:
            candidates.extend(_candidate_forms(path, value))
        if candidates:
            print()
            print("[NUMBER CANDIDATES]")
            print(
                "The following are display-only representations. They are NOT proof "
                "of the printed key number."
            )
            for candidate in candidates:
                print(candidate)


async def inspect_keys(
    session: aiohttp.ClientSession,
    access_token: str,
    base_url: str,
    *,
    key_index: int | None,
    show_candidates: bool,
) -> None:
    payload = await _request_json(
        session,
        "POST",
        base_url,
        "/api/v4/key/list/",
        "POST /api/v4/key/list/",
        access_token=access_token,
    )
    keys = _extract_keys(payload)
    print(f"[RESULT] physical keys returned: {len(keys)}")

    if not keys:
        print("[INFO] No physical keys are registered on this account.")
        return

    if key_index is not None:
        if key_index < 1 or key_index > len(keys):
            raise ProbeError(
                f"--key-index {key_index} is outside the returned range 1..{len(keys)}"
            )
        selected = [(key_index, keys[key_index - 1])]
    else:
        selected = list(enumerate(keys, start=1))

    for index, key in selected:
        print_key(index, key, show_candidates=show_candidates)

    print()
    print("[WARNING] Output above contains real access-control identifiers.")
    print("[WARNING] Do not publish it in GitHub issues, public screenshots, or logs.")


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
        await inspect_keys(
            session,
            access_token,
            base_url,
            key_index=args.key_index,
            show_candidates=not args.no_candidate_forms,
        )

    print("[OK] Read-only raw physical-key inspection completed")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only Ufanet raw physical-key inspector. Prints every key field "
            "and optional number-like representations for local comparison."
        )
    )
    parser.add_argument("--username", help="Ufanet contract/login")
    parser.add_argument(
        "--ufanet-base-url",
        default=UFANET_BASE_URL,
        help="Ufanet API base URL",
    )
    parser.add_argument(
        "--key-index",
        type=int,
        help="Print only this 1-based key index (default: print all keys)",
    )
    parser.add_argument(
        "--no-candidate-forms",
        action="store_true",
        help="Do not print decimal/hex helper representations",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.key_index is not None and args.key_index < 1:
        print("[ERROR] --key-index must be >= 1", file=sys.stderr)
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
