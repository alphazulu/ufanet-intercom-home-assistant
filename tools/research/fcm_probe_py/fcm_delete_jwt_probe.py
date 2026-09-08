"""Controlled live probe for Ufanet FCM DELETE vs JWT validity.

The probe operates only on the existing virtual device owned by fcm_probe_py.
It registers that probe-owned device with a dedicated subject JWT pair, deletes
only its FCM registration through DELETE /api/v0/fcm/ from an independent
observer JWT, then tests whether the subject access/refresh chain remains valid.
The probe never accepts an arbitrary provider device_id, never touches another
device, never prints JWT/FCM tokens or provider IDs, never calls logout_device,
and never starts the MCS listener. The probe registration is restored at exit.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path

import aiohttp

import logout_jwt_probe as auth_probe
import probe as fcm_probe


class ProbeError(RuntimeError):
    """Expected probe failure with an intentionally safe message."""


async def _test_refresh_after_delete(
    session: aiohttp.ClientSession,
    base_url: str,
    refresh_token: str,
) -> tuple[auth_probe.RequestResult, auth_probe.AuthTokens | None]:
    result = await auth_probe._request(
        session,
        "POST",
        base_url,
        "/api/v1/auth/refresh/",
        json_body={"token": refresh_token.removeprefix("JWT ")},
    )
    refreshed: auth_probe.AuthTokens | None = None
    if result.accepted:
        refreshed = auth_probe._parse_refresh_tokens(result.payload)
    print(
        "[RESULT] subject refresh after FCM DELETE: "
        f"accepted={str(result.accepted).lower()} "
        f"auth_rejected={str(result.auth_rejected).lower()} http_status={result.status}"
    )
    return result, refreshed


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
        "[INFO] Controlled FCM DELETE vs JWT test using only the existing "
        "probe-owned virtual device."
    )
    print(
        "[INFO] The probe obtains/reuses its own virtual FCM token only so it can "
        "create the disposable device row. It does NOT start MCS, does NOT accept "
        "an arbitrary device_id, and NEVER calls logout_device."
    )

    client = auth_probe._build_fcm_client(state, state_path, firebase)
    print("[INFO] Registering/checking in virtual FCM device...")
    fcm_token = await client.checkin_or_register()
    print("[OK] FCM token obtained (value suppressed)")
    if not state_path.exists():
        fcm_probe.save_state(state_path, state)

    device_id = str(state["ufanet_device_id"])
    title = str(state["ufanet_device_title"])
    package_name = firebase["package_name"]

    async with aiohttp.ClientSession() as session:
        observer = await auth_probe.authenticate(
            session,
            base_url,
            contract,
            password,
            label="observer plain Ufanet authentication",
        )
        subject = await auth_probe.authenticate(
            session,
            base_url,
            contract,
            password,
            label="subject Ufanet authentication",
        )

        restore_needed = False
        try:
            # Bind the probe-owned FCM/device registration to this exact subject JWT pair.
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
            print("[OK] Probe-owned device is visible before FCM DELETE")

            before_access = await auth_probe.test_access_token(
                session,
                base_url,
                subject.access,
                label="subject access before FCM DELETE",
            )
            if not before_access.accepted:
                raise ProbeError("subject access token was not usable before FCM DELETE")

            restore_needed = True
            # Critical separation: delete the push registration from the independent
            # observer session. This is deliberately NOT logout_device.
            await fcm_probe.unregister_token_with_ufanet(
                session,
                observer.access,
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
                    "FCM DELETE returned success but the probe-owned device remained visible"
                )
            print("[OK] Probe-owned device is absent after FCM DELETE")

            subject_access_after = await auth_probe.test_access_token(
                session,
                base_url,
                subject.access,
                label="subject access after FCM DELETE",
            )
            refresh_result, refreshed = await _test_refresh_after_delete(
                session,
                base_url,
                subject.refresh,
            )

            refreshed_access_after: auth_probe.RequestResult | None = None
            if refreshed is not None:
                refreshed_access_after = await auth_probe.test_access_token(
                    session,
                    base_url,
                    refreshed.access,
                    label="refreshed subject access after FCM DELETE",
                )

            observer_after = await auth_probe.test_access_token(
                session,
                base_url,
                observer.access,
                label="independent observer access after FCM DELETE",
            )

            print("[SUMMARY]")
            print("  target_was_probe_owned_device=true")
            print("  fcm_delete_requests_sent=true")
            print("  logout_device_requests_sent=false")
            print("  mcs_listener_started=false")
            print(
                "  subject_access_survived_fcm_delete="
                f"{str(subject_access_after.accepted).lower()}"
            )
            print(
                "  subject_refresh_survived_fcm_delete="
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
                "  independent_observer_access_survived_fcm_delete="
                f"{str(observer_after.accepted).lower()}"
            )
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
                    "[CONCLUSION] DELETE /api/v0/fcm/ removed the probe-owned device "
                    "from authorized_devices but did NOT invalidate the subject JWT "
                    "access/refresh chain used to create that registration. FCM cleanup "
                    "and Ufanet authorization revocation are therefore distinct operations."
                )
            elif (
                subject_access_after.accepted
                and not refresh_result.accepted
                and observer_after.accepted
            ):
                print(
                    "[CONCLUSION] DELETE /api/v0/fcm/ removed the probe-owned device; "
                    "the already-issued subject access token still worked, but its refresh "
                    "token was rejected. FCM DELETE therefore also invalidated the tested "
                    "subject refresh authorization chain even without logout_device."
                )
            elif (
                not subject_access_after.accepted
                and not refresh_result.accepted
                and observer_after.accepted
            ):
                print(
                    "[CONCLUSION] DELETE /api/v0/fcm/ removed the probe-owned device and "
                    "the tested subject access/refresh chain was rejected afterward. FCM "
                    "DELETE behaved as an authorization revoke for this controlled subject."
                )
            else:
                print(
                    "[CONCLUSION] FCM DELETE produced mixed JWT results. Treat the relation "
                    "between push cleanup and authorization as unresolved until reviewed."
                )
        finally:
            if restore_needed:
                try:
                    await auth_probe._restore_probe_registration(
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
                        "test completed or failed after FCM DELETE, but automatic restoration "
                        "of the probe-owned registration failed; run the ordinary fcm probe once "
                        "to restore its virtual device"
                    ) from exc

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Controlled live test of whether DELETE /api/v0/fcm/ invalidates the JWT "
            "pair used to create the probe-owned virtual Ufanet device registration."
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
    except (ProbeError, auth_probe.ProbeError, RuntimeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n[ERROR] Interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
