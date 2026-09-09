"""Controlled live probe for Ufanet logout_device vs JWT validity.

The probe operates only on the virtual device owned by fcm_probe_py. It never
accepts an arbitrary provider device_id and restores the probe registration at
exit. JWTs, FCM tokens and provider device IDs are kept in memory and are never
printed.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp

import probe as fcm_probe


class ProbeError(RuntimeError):
    """Expected probe failure with an intentionally safe message."""


@dataclass(frozen=True)
class AuthTokens:
    """In-memory Ufanet JWT pair. Values are never printed or persisted."""

    access: str
    refresh: str


@dataclass(frozen=True)
class RequestResult:
    """Privacy-safe HTTP result classification."""

    status: int
    accepted: bool
    auth_rejected: bool
    payload: Any | None = None


def _auth_headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"JWT {access_token.removeprefix('JWT ')}",
        "Accept": "application/json",
    }


async def _request(
    session: aiohttp.ClientSession,
    method: str,
    base_url: str,
    path: str,
    *,
    access_token: str | None = None,
    json_body: object | None = None,
) -> RequestResult:
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
            f"{base_url}{path}",
            **kwargs,
        ) as response:
            text = await response.text()
            payload: Any | None = None
            if text:
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    payload = None
            status = int(response.status)
            return RequestResult(
                status=status,
                accepted=200 <= status < 300,
                auth_rejected=status in {400, 401, 403},
                payload=payload,
            )
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
    base_url: str,
    contract: str,
    password: str,
    *,
    label: str,
) -> AuthTokens:
    result = await _request(
        session,
        "POST",
        base_url,
        "/api/v1/auth/auth_by_contract/",
        json_body={"contract": contract.upper(), "password": password},
    )
    if not result.accepted:
        raise ProbeError(f"{label} failed: HTTP {result.status}")
    tokens = _parse_login_tokens(result.payload)
    print(f"[OK] {label}: HTTP {result.status}")
    return tokens


async def test_access_token(
    session: aiohttp.ClientSession,
    base_url: str,
    access_token: str,
    *,
    label: str,
) -> RequestResult:
    result = await _request(
        session,
        "GET",
        base_url,
        "/api/v0/contract/",
        access_token=access_token,
    )
    print(
        f"[RESULT] {label}: accepted={str(result.accepted).lower()} "
        f"auth_rejected={str(result.auth_rejected).lower()} http_status={result.status}"
    )
    return result


async def test_refresh_token(
    session: aiohttp.ClientSession,
    base_url: str,
    refresh_token: str,
) -> tuple[RequestResult, AuthTokens | None]:
    result = await _request(
        session,
        "POST",
        base_url,
        "/api/v1/auth/refresh/",
        json_body={"token": refresh_token.removeprefix("JWT ")},
    )
    refreshed: AuthTokens | None = None
    if result.accepted:
        refreshed = _parse_refresh_tokens(result.payload)
    print(
        "[RESULT] subject refresh after logout: "
        f"accepted={str(result.accepted).lower()} "
        f"auth_rejected={str(result.auth_rejected).lower()} http_status={result.status}"
    )
    return result, refreshed


def _build_fcm_client(
    state: dict[str, Any],
    state_path: Path,
    firebase: dict[str, str],
) -> fcm_probe.FcmPushClient:
    persistent_ids = state.get("persistent_ids")
    if not isinstance(persistent_ids, list):
        persistent_ids = []
        state["persistent_ids"] = persistent_ids

    def persist_credentials(credentials: dict[str, Any]) -> None:
        state["fcm_credentials"] = credentials
        fcm_probe.save_state(state_path, state)
        print("[OK] FCM credentials saved locally")

    def ignore_push(_notification: dict[str, Any], _persistent_id: str, _context: Any) -> None:
        return

    config = fcm_probe.FcmRegisterConfig(
        project_id=firebase["project_id"],
        app_id=firebase["app_id"],
        api_key=firebase["api_key"],
        messaging_sender_id=firebase["sender_id"],
        bundle_id=firebase["package_name"],
        persistend_ids=persistent_ids,
    )
    return fcm_probe.FcmPushClient(
        ignore_push,
        config,
        credentials=state.get("fcm_credentials"),
        credentials_updated_callback=persist_credentials,
        received_persistent_ids=persistent_ids,
    )


async def _restore_probe_registration(
    session: aiohttp.ClientSession,
    base_url: str,
    contract: str,
    password: str,
    *,
    fcm_token: str,
    device_id: str,
    title: str,
    package_name: str,
) -> None:
    """Restore exactly the probe-owned virtual device using a fresh login."""
    print("[INFO] Restoring probe-owned device registration with a fresh JWT login...")
    restore_auth = await authenticate(
        session,
        base_url,
        contract,
        password,
        label="restore Ufanet authentication",
    )
    await fcm_probe.register_token_with_ufanet(
        session,
        restore_auth.access,
        fcm_token,
        device_id,
        title,
        package_name,
        base_url,
    )
    restored = await fcm_probe._wait_authorized_device_presence(
        session,
        restore_auth.access,
        device_id,
        base_url,
        expected=True,
    )
    if not restored:
        raise ProbeError(
            "probe-owned device registration was restored by POST but is not visible in authorized_devices"
        )
    print("[OK] Probe-owned device registration restored")


async def run(args: argparse.Namespace) -> int:
    base_url = args.ufanet_base_url.rstrip("/")
    state_path = Path(args.state).expanduser().resolve()
    firebase_path = Path(args.firebase_config).expanduser().resolve()
    state = fcm_probe.load_state(state_path)
    firebase = fcm_probe.load_firebase_config(firebase_path)
    fcm_probe.bind_state_to_firebase_config(state, state_path, firebase)

    contract = args.contract or os.getenv("UFANET_USERNAME")
    if not contract:
        contract = input("Ufanet contract/login: ").strip()
    password = os.getenv("UFANET_PASSWORD")
    if not password:
        password = getpass.getpass("Ufanet password: ")
    if not contract or not password:
        raise ProbeError("Ufanet contract/login and password are required")

    print(
        "[INFO] This controlled probe uses only the existing fcm_probe_py virtual device. "
        "It will register that probe-owned device, log out exactly that device, test the "
        "JWT pair used for it, and restore the probe registration with a fresh login."
    )
    print(
        "[INFO] It never accepts or prints a provider device_id, never touches another "
        "authorized device, never prints JWT/FCM tokens, and does not start the MCS listener."
    )

    client = _build_fcm_client(state, state_path, firebase)
    print("[INFO] Registering/checking in virtual FCM device...")
    fcm_token = await client.checkin_or_register()
    print("[OK] FCM token obtained (value suppressed)")
    if not state_path.exists():
        fcm_probe.save_state(state_path, state)

    device_id = str(state["ufanet_device_id"])
    title = str(state["ufanet_device_title"])
    package_name = firebase["package_name"]

    async with aiohttp.ClientSession() as session:
        observer = await authenticate(
            session,
            base_url,
            contract,
            password,
            label="observer poll-only Ufanet authentication",
        )
        subject = await authenticate(
            session,
            base_url,
            contract,
            password,
            label="subject Ufanet authentication",
        )

        restore_needed = False
        try:
            await fcm_probe.register_token_with_ufanet(
                session,
                subject.access,
                fcm_token,
                device_id,
                title,
                package_name,
                base_url,
            )
            present = await fcm_probe._wait_authorized_device_presence(
                session,
                observer.access,
                device_id,
                base_url,
                expected=True,
            )
            if not present:
                raise ProbeError(
                    "probe-owned device did not become visible in authorized_devices"
                )
            print("[OK] Probe-owned device is visible before logout")

            before_access = await test_access_token(
                session,
                base_url,
                subject.access,
                label="subject access before logout",
            )
            if not before_access.accepted:
                raise ProbeError("subject access token was not usable before logout")

            restore_needed = True
            await fcm_probe.logout_device_with_ufanet(
                session,
                subject.access,
                device_id,
                base_url,
            )

            absent = await fcm_probe._wait_authorized_device_presence(
                session,
                observer.access,
                device_id,
                base_url,
                expected=False,
            )
            if not absent:
                raise ProbeError(
                    "logout_device returned success but the probe-owned device remained visible"
                )
            print("[OK] Probe-owned device is absent after logout")

            subject_access_after = await test_access_token(
                session,
                base_url,
                subject.access,
                label="subject access after logout",
            )
            refresh_result, refreshed = await test_refresh_token(
                session,
                base_url,
                subject.refresh,
            )

            refreshed_access_after: RequestResult | None = None
            if refreshed is not None:
                refreshed_access_after = await test_access_token(
                    session,
                    base_url,
                    refreshed.access,
                    label="refreshed subject access after logout",
                )

            observer_after = await test_access_token(
                session,
                base_url,
                observer.access,
                label="independent observer access after logout",
            )

            print("[SUMMARY]")
            print(
                "  subject_access_survived_logout="
                f"{str(subject_access_after.accepted).lower()}"
            )
            print(
                "  subject_refresh_survived_logout="
                f"{str(refresh_result.accepted).lower()}"
            )
            print(
                "  refreshed_subject_access_usable="
                + (
                    "not_tested"
                    if refreshed_access_after is None
                    else str(refreshed_access_after.accepted).lower()
                )
            )
            print(
                "  independent_observer_access_survived_logout="
                f"{str(observer_after.accepted).lower()}"
            )
            print("  target_was_probe_owned_device=true")
            print("  arbitrary_device_id_input_supported=false")
            print("  secrets_printed=false")

            if (
                subject_access_after.accepted
                and refresh_result.accepted
                and refreshed_access_after is not None
                and refreshed_access_after.accepted
                and observer_after.accepted
            ):
                print(
                    "[CONCLUSION] logout_device removed the probe-owned authorized-device "
                    "record but did not invalidate the JWT access/refresh chain used for the "
                    "registration during this test."
                )
            elif (
                not subject_access_after.accepted
                and not refresh_result.accepted
                and observer_after.accepted
            ):
                print(
                    "[CONCLUSION] logout_device removed the probe-owned authorized-device "
                    "record and the tested subject JWT access/refresh chain was rejected afterward; "
                    "the independent observer JWT remained usable."
                )
            else:
                print(
                    "[CONCLUSION] logout_device produced mixed JWT results. Treat the relationship "
                    "as unresolved until the output is reviewed and the test is repeated if needed."
                )
        finally:
            if restore_needed:
                try:
                    await _restore_probe_registration(
                        session,
                        base_url,
                        contract,
                        password,
                        fcm_token=fcm_token,
                        device_id=device_id,
                        title=title,
                        package_name=package_name,
                    )
                except Exception as exc:
                    raise ProbeError(
                        "test completed or failed after logout_device, but automatic restoration "
                        "of the probe-owned registration failed; run the ordinary fcm probe once "
                        "to restore its virtual device"
                    ) from exc

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Controlled live test of whether logout_device invalidates the JWT pair used "
            "to register the probe-owned virtual Ufanet device."
        )
    )
    parser.add_argument(
        "--firebase-config",
        default=str(Path(__file__).with_name("firebase_config.json")),
        help="JSON produced locally by extract_firebase_config.py",
    )
    parser.add_argument(
        "--state",
        default=str(Path(__file__).with_name("fcm_state.json")),
        help="Existing local sensitive fcm_probe_py state JSON",
    )
    parser.add_argument(
        "--contract",
        help="Ufanet contract/login. If omitted, prompt or UFANET_USERNAME is used.",
    )
    parser.add_argument(
        "--ufanet-base-url",
        default=fcm_probe.UFANET_BASE_URL,
        help="Ufanet API base URL",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return asyncio.run(run(args))
    except ProbeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n[ERROR] Interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
