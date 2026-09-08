"""Controlled Ufanet authorization-revocation probe with no FCM registration."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aiohttp

UFANET_BASE_URL = "https://dom.ufanet.ru"


class ProbeError(RuntimeError):
    """Expected probe failure with an intentionally safe message."""


@dataclass(frozen=True)
class AuthTokens:
    """In-memory Ufanet JWT pair. Values are never printed or persisted."""

    access: str
    refresh: str


@dataclass(frozen=True)
class AuthorizedDevice:
    """One authorized-device row with private provider ID retained in memory only."""

    device_id: str
    title: str
    last_update: str | None
    is_call_access: bool | None
    os_display: str | None

    @property
    def session_ref(self) -> str:
        digest = hashlib.sha256(self.device_id.encode("utf-8")).hexdigest()[:12]
        return f"auth-{digest}"


def _auth_headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"JWT {access_token.removeprefix('JWT ')}",
        "Accept": "application/json",
    }


async def _request_json(
    session: aiohttp.ClientSession,
    method: str,
    path: str,
    *,
    access_token: str | None = None,
    json_body: object | None = None,
    allow_empty: bool = False,
) -> tuple[int, Any | None]:
    headers = _auth_headers(access_token) if access_token else {"Accept": "application/json"}
    kwargs: dict[str, Any] = {
        "headers": headers,
        "timeout": aiohttp.ClientTimeout(total=30),
    }
    if json_body is not None:
        kwargs["json"] = json_body

    try:
        async with session.request(
            method,
            f"{UFANET_BASE_URL}{path}",
            **kwargs,
        ) as response:
            text = await response.text()
            if response.status >= 400:
                raise ProbeError(f"{path} failed: HTTP {response.status}")
            if not text:
                if allow_empty:
                    return response.status, None
                raise ProbeError(f"{path} returned an empty body")
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                if allow_empty:
                    payload = None
                else:
                    raise ProbeError(f"{path} returned invalid JSON")
            return response.status, payload
    except aiohttp.ClientError as exc:
        raise ProbeError(f"request failed: {type(exc).__name__}") from exc
    except asyncio.TimeoutError as exc:
        raise ProbeError("request timed out") from exc


def _parse_login_tokens(payload: Any) -> AuthTokens:
    if not isinstance(payload, dict):
        raise ProbeError("Ufanet authentication returned an unexpected schema")
    token = payload.get("token")
    access = token.get("access") if isinstance(token, dict) else None
    refresh = token.get("refresh") if isinstance(token, dict) else None
    if not isinstance(access, str) or not access:
        raise ProbeError("Ufanet authentication response has no access token")
    if not isinstance(refresh, str) or not refresh:
        raise ProbeError("Ufanet authentication response has no refresh token")
    return AuthTokens(access=access, refresh=refresh)


async def authenticate(
    session: aiohttp.ClientSession,
    contract: str,
    password: str,
) -> AuthTokens:
    status, payload = await _request_json(
        session,
        "POST",
        "/api/v1/auth/auth_by_contract/",
        json_body={"contract": contract.upper(), "password": password},
    )
    tokens = _parse_login_tokens(payload)
    print(f"[OK] Pure JWT Ufanet authentication: HTTP {status}")
    return tokens


async def refresh_tokens(
    session: aiohttp.ClientSession,
    refresh_token: str,
) -> AuthTokens:
    status, payload = await _request_json(
        session,
        "POST",
        "/api/v1/auth/refresh/",
        json_body={"token": refresh_token.removeprefix("JWT ")},
    )
    tokens = _parse_login_tokens({"token": payload})
    print(f"[OK] Controller JWT refresh after revoke: HTTP {status}")
    return tokens


def _parse_devices(payload: Any) -> list[AuthorizedDevice]:
    if not isinstance(payload, dict):
        raise ProbeError("authorized_devices returned an unexpected schema")
    data = payload.get("data")
    devices = data.get("device_list") if isinstance(data, dict) else None
    if not isinstance(devices, list):
        raise ProbeError("authorized_devices response has no device_list")

    parsed: list[AuthorizedDevice] = []
    seen: set[str] = set()
    for raw in devices:
        if not isinstance(raw, dict):
            raise ProbeError("authorized_devices contains an invalid item")
        device_id = raw.get("device_id")
        if not isinstance(device_id, str) or not device_id:
            raise ProbeError("authorized_devices contains an invalid device_id")
        if device_id in seen:
            raise ProbeError("authorized_devices contains a duplicate device_id")
        seen.add(device_id)

        title_raw = raw.get("title")
        title = title_raw.strip() if isinstance(title_raw, str) and title_raw.strip() else "(no title)"
        last_update = raw.get("last_update") if isinstance(raw.get("last_update"), str) else None
        call_access = raw.get("is_call_access") if isinstance(raw.get("is_call_access"), bool) else None
        os_display = raw.get("os_display") if isinstance(raw.get("os_display"), str) else None
        parsed.append(
            AuthorizedDevice(
                device_id=device_id,
                title=title,
                last_update=last_update,
                is_call_access=call_access,
                os_display=os_display,
            )
        )
    return parsed


async def get_authorized_devices(
    session: aiohttp.ClientSession,
    access_token: str,
) -> list[AuthorizedDevice]:
    status, payload = await _request_json(
        session,
        "POST",
        "/api/v4/fcm_device/authorized_devices/",
        access_token=access_token,
    )
    devices = _parse_devices(payload)
    print(
        "[OK] POST /api/v4/fcm_device/authorized_devices/: "
        f"HTTP {status}; count={len(devices)}"
    )
    return devices


def _format_activity(value: str | None) -> str:
    if value is None:
        return "unknown"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.astimezone().isoformat(timespec="seconds")


def print_inventory(devices: list[AuthorizedDevice]) -> None:
    print("[RESULT] Authorized Ufanet devices visible to pure JWT controller:")
    for index, device in enumerate(devices, start=1):
        print(f"  [{index}] {device.title}")
        print(f"      session_ref={device.session_ref}")
        print(f"      last_update={_format_activity(device.last_update)}")
        print(f"      os_display={device.os_display or 'unknown'}")
        print(
            "      is_call_access="
            + (
                "unknown"
                if device.is_call_access is None
                else str(device.is_call_access).lower()
            )
        )


def resolve_target(
    devices: list[AuthorizedDevice],
    *,
    title: str | None,
    session_ref: str | None,
) -> AuthorizedDevice:
    if bool(title) == bool(session_ref):
        raise ProbeError("specify exactly one of --title or --session-ref")

    if title is not None:
        matches = [device for device in devices if device.title == title]
        if len(matches) != 1:
            raise ProbeError(
                f"exact title matched {len(matches)} devices; use --session-ref instead"
            )
        return matches[0]

    assert session_ref is not None
    matches = [device for device in devices if device.session_ref == session_ref]
    if len(matches) != 1:
        raise ProbeError(f"session_ref matched {len(matches)} devices")
    return matches[0]


async def test_controller_access(
    session: aiohttp.ClientSession,
    access_token: str,
    *,
    label: str,
) -> None:
    status, _payload = await _request_json(
        session,
        "GET",
        "/api/v0/contract/",
        access_token=access_token,
    )
    print(f"[OK] {label}: HTTP {status}")


async def revoke_device(
    session: aiohttp.ClientSession,
    access_token: str,
    target: AuthorizedDevice,
) -> None:
    status, _payload = await _request_json(
        session,
        "POST",
        "/api/v4/fcm_device/logout_device/",
        access_token=access_token,
        json_body={"device_id": target.device_id},
        allow_empty=True,
    )
    print(
        "[OK] POST /api/v4/fcm_device/logout_device/: "
        f"HTTP {status}; target={target.title} ({target.session_ref})"
    )


async def run(args: argparse.Namespace) -> int:
    contract = args.contract or input("Ufanet contract/login: ").strip()
    password = getpass.getpass("Ufanet password: ")
    if not contract or not password:
        raise ProbeError("Ufanet contract/login and password are required")

    print(
        "[INFO] This test uses only Ufanet JWT endpoints. It does NOT import Firebase/FCM "
        "libraries, does NOT call POST/DELETE /api/v0/fcm/, does NOT obtain an FCM token, "
        "and does NOT start an MCS listener."
    )

    async with aiohttp.ClientSession() as session:
        controller = await authenticate(session, contract, password)
        await test_controller_access(
            session,
            controller.access,
            label="controller access before revoke",
        )

        before = await get_authorized_devices(session, controller.access)
        print_inventory(before)
        target = resolve_target(
            before,
            title=args.title,
            session_ref=args.session_ref,
        )

        if not args.confirm:
            raise ProbeError(
                "destructive revoke was not performed; rerun with --confirm after checking the target"
            )

        if target.title.startswith("Home Assistant") and not args.allow_home_assistant:
            raise ProbeError(
                "refusing a Home Assistant target without --allow-home-assistant"
            )

        print(
            f"[INFO] Revoking exactly: title={target.title!r} "
            f"session_ref={target.session_ref}"
        )
        await revoke_device(session, controller.access, target)

        after = await get_authorized_devices(session, controller.access)
        still_present = any(device.device_id == target.device_id for device in after)
        print(
            "[RESULT] target_present_after_logout_device="
            f"{str(still_present).lower()}"
        )
        if still_present:
            raise ProbeError("target is still present after logout_device")

        await test_controller_access(
            session,
            controller.access,
            label="controller old access after revoke",
        )
        refreshed = await refresh_tokens(session, controller.refresh)
        await test_controller_access(
            session,
            refreshed.access,
            label="controller refreshed access after revoke",
        )

        print("[SUMMARY]")
        print("  firebase_or_fcm_library_used=false")
        print("  fcm_registration_requests_sent=false")
        print("  fcm_unregistration_requests_sent=false")
        print("  mcs_listener_started=false")
        print("  controller_was_plain_jwt_login=true")
        print("  target_removed_from_authorized_devices=true")
        print("  controller_old_access_survived=true")
        print("  controller_refresh_survived=true")
        print("  secrets_persisted=false")
        print(
            "[CONCLUSION] A plain Ufanet JWT session revoked another authorized-device "
            "record through logout_device without performing any FCM registration or "
            "unregistration in this probe."
        )
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Controlled cross-device Ufanet authorization revoke using only ordinary JWT API calls"
        )
    )
    parser.add_argument("--contract", help="Ufanet contract/login")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--title", help="Exact authorized-device title to revoke")
    target.add_argument("--session-ref", help="Opaque auth-XXXXXXXXXXXX reference shown by this probe")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required to perform logout_device",
    )
    parser.add_argument(
        "--allow-home-assistant",
        action="store_true",
        help="Allow a target whose title starts with 'Home Assistant'",
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
