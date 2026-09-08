"""Privacy-safe live probe for Ufanet JWT auth vs authorized-device membership."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import sys
from dataclasses import dataclass
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
class DeviceSnapshot:
    """Private authorized-device membership snapshot."""

    device_ids: frozenset[str]

    @property
    def count(self) -> int:
        return len(self.device_ids)


def _auth_headers(access_token: str) -> dict[str, str]:
    token = access_token.removeprefix("JWT ")
    return {
        "Authorization": f"JWT {token}",
        "Accept": "application/json",
    }


async def _request_json(
    session: aiohttp.ClientSession,
    method: str,
    path: str,
    label: str,
    *,
    access_token: str | None = None,
    json_body: object | None = None,
) -> Any:
    headers = (
        _auth_headers(access_token)
        if access_token is not None
        else {"Accept": "application/json"}
    )
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


def _parse_refresh_tokens(payload: Any) -> AuthTokens:
    if not isinstance(payload, dict):
        raise ProbeError("Ufanet refresh returned an unexpected schema")
    access = payload.get("access")
    refresh = payload.get("refresh")
    if not isinstance(access, str) or not access:
        raise ProbeError("Ufanet refresh response has no access token")
    if not isinstance(refresh, str) or not refresh:
        raise ProbeError("Ufanet refresh response has no refresh token")
    return AuthTokens(access=access, refresh=refresh)


async def authenticate(
    session: aiohttp.ClientSession,
    contract: str,
    password: str,
    *,
    label: str,
) -> AuthTokens:
    payload = await _request_json(
        session,
        "POST",
        "/api/v1/auth/auth_by_contract/",
        label,
        json_body={"contract": contract.upper(), "password": password},
    )
    return _parse_login_tokens(payload)


async def refresh_tokens(
    session: aiohttp.ClientSession,
    tokens: AuthTokens,
) -> AuthTokens:
    payload = await _request_json(
        session,
        "POST",
        "/api/v1/auth/refresh/",
        "Ufanet token refresh",
        json_body={"token": tokens.refresh.removeprefix("JWT ")},
    )
    return _parse_refresh_tokens(payload)


def _parse_authorized_devices(payload: Any) -> DeviceSnapshot:
    if not isinstance(payload, dict):
        raise ProbeError("authorized_devices returned an unexpected schema")
    data = payload.get("data")
    devices = data.get("device_list") if isinstance(data, dict) else None
    if not isinstance(devices, list):
        raise ProbeError("authorized_devices response has no device_list")

    ids: set[str] = set()
    for item in devices:
        if not isinstance(item, dict):
            raise ProbeError("authorized_devices contains an invalid item")
        device_id = item.get("device_id")
        if not isinstance(device_id, str) or not device_id:
            raise ProbeError("authorized_devices contains an invalid device_id")
        if device_id in ids:
            raise ProbeError("authorized_devices contains a duplicate device_id")
        ids.add(device_id)

    return DeviceSnapshot(device_ids=frozenset(ids))


async def get_authorized_devices(
    session: aiohttp.ClientSession,
    access_token: str,
    *,
    label: str,
) -> DeviceSnapshot:
    payload = await _request_json(
        session,
        "POST",
        "/api/v4/fcm_device/authorized_devices/",
        label,
        access_token=access_token,
    )
    return _parse_authorized_devices(payload)


async def exercise_poll_only_access(
    session: aiohttp.ClientSession,
    access_token: str,
) -> None:
    await _request_json(
        session,
        "GET",
        "/api/v0/contract/",
        "poll-only GET /api/v0/contract/",
        access_token=access_token,
    )
    await _request_json(
        session,
        "GET",
        "/api/v0/skud/shared/",
        "poll-only GET /api/v0/skud/shared/",
        access_token=access_token,
    )


def _report_membership_change(
    label: str,
    before: DeviceSnapshot,
    after: DeviceSnapshot,
) -> bool:
    added = after.device_ids - before.device_ids
    removed = before.device_ids - after.device_ids
    unchanged = not added and not removed
    print(
        f"[RESULT] {label}: "
        f"before={before.count} after={after.count} "
        f"membership_unchanged={str(unchanged).lower()} "
        f"added={len(added)} removed={len(removed)}"
    )
    return unchanged


async def run_probe(contract: str, password: str) -> int:
    async with aiohttp.ClientSession() as session:
        # Login A is used only to establish an authenticated baseline snapshot.
        baseline_auth = await authenticate(
            session,
            contract,
            password,
            label="baseline Ufanet authentication",
        )
        baseline = await get_authorized_devices(
            session,
            baseline_auth.access,
            label="authorized_devices baseline",
        )
        print(f"[RESULT] baseline authorized-device count: {baseline.count}")

        # Login B intentionally does NOT call /api/v0/fcm/ or any logout endpoint.
        poll_auth = await authenticate(
            session,
            contract,
            password,
            label="independent poll-only Ufanet authentication",
        )
        after_login = await get_authorized_devices(
            session,
            poll_auth.access,
            label="authorized_devices after second login",
        )
        login_unchanged = _report_membership_change(
            "second login vs baseline",
            baseline,
            after_login,
        )

        await exercise_poll_only_access(session, poll_auth.access)
        after_poll = await get_authorized_devices(
            session,
            poll_auth.access,
            label="authorized_devices after poll-only requests",
        )
        poll_unchanged = _report_membership_change(
            "poll-only requests vs post-login",
            after_login,
            after_poll,
        )

        refreshed = await refresh_tokens(session, poll_auth)
        print(
            "[RESULT] refresh token rotation: "
            f"access_changed={str(refreshed.access != poll_auth.access).lower()} "
            f"refresh_changed={str(refreshed.refresh != poll_auth.refresh).lower()}"
        )
        await exercise_poll_only_access(session, refreshed.access)
        after_refresh = await get_authorized_devices(
            session,
            refreshed.access,
            label="authorized_devices after JWT refresh",
        )
        refresh_unchanged = _report_membership_change(
            "JWT refresh vs pre-refresh",
            after_poll,
            after_refresh,
        )

        print("[SUMMARY]")
        print(
            "  second_login_changed_authorized_device_membership="
            f"{str(not login_unchanged).lower()}"
        )
        print(
            "  poll_requests_changed_authorized_device_membership="
            f"{str(not poll_unchanged).lower()}"
        )
        print(
            "  jwt_refresh_changed_authorized_device_membership="
            f"{str(not refresh_unchanged).lower()}"
        )
        print("  fcm_registration_requests_sent=false")
        print("  logout_or_revoke_requests_sent=false")
        print("  secrets_persisted=false")

        if login_unchanged and poll_unchanged and refresh_unchanged:
            print(
                "[CONCLUSION] Additional poll-only JWT authentication and refresh did "
                "not change authorized_devices membership during this test."
            )
        else:
            print(
                "[CONCLUSION] authorized_devices membership changed during the test; "
                "inspect timing and repeat before assigning semantics."
            )
        return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare Ufanet JWT login/refresh behavior with authorized_devices "
            "membership without registering FCM or revoking any device."
        )
    )
    parser.add_argument(
        "--contract",
        help="Ufanet contract/login. If omitted, it is requested interactively.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    contract = (args.contract or input("Ufanet contract/login: ")).strip()
    if not contract:
        print("[ERROR] Ufanet contract/login is required", file=sys.stderr)
        return 2
    password = getpass.getpass("Ufanet password: ")
    if not password:
        print("[ERROR] Ufanet password is required", file=sys.stderr)
        return 2

    print(
        "[INFO] This probe performs two JWT logins and one JWT refresh, but does not "
        "register FCM, unregister FCM, log out devices, or persist credentials."
    )
    try:
        return asyncio.run(run_probe(contract, password))
    except ProbeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n[ERROR] Interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
