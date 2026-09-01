from __future__ import annotations

import argparse
import asyncio
import getpass
import hashlib
import json
import os
import stat
import statistics
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import aiohttp
from firebase_messaging import FcmPushClient, FcmRegisterConfig

UFANET_BASE_URL = "https://dom.ufanet.ru"
DEFAULT_DEVICE_TITLE = "Home Assistant Windows"
STATE_VERSION = 1
DEFAULT_HISTORY_DELAYS = (0.0, 0.25, 0.5, 1.0, 2.0, 5.0)
REQUIRED_FIREBASE_FIELDS = (
    "project_id",
    "sender_id",
    "app_id",
    "package_name",
    "api_key",
)

SENSITIVE_KEYS = {
    "authorization",
    "token",
    "fcm_token",
    "refresh_token",
    "password",
    "username",
    "server",
    "contract",
    "flat",
    "house_id",
    "skud_id",
    "camera_number",
    "device_id",
    "key_id",
    "address",
    "skud_mac",
    "api_key",
    "from",
    "fcmmessageid",
    "uuid",
    "time",
}


def _fingerprint(value: Any) -> str:
    raw = str(value).encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()[:10]


def _redacted(value: Any) -> str:
    text = "" if value is None else str(value)
    return f"<redacted len={len(text)}>"


def sanitize(value: Any, key: str | None = None) -> Any:
    if key and key.lower() in SENSITIVE_KEYS:
        return _redacted(value)
    if isinstance(value, dict):
        return {str(k): sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, bytes):
        return f"<bytes len={len(value)} sha256={hashlib.sha256(value).hexdigest()[:10]}>"
    return value


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "version": STATE_VERSION,
            "fcm_credentials": None,
            "persistent_ids": [],
            "ufanet_device_id": f"{DEFAULT_DEVICE_TITLE}_{uuid.uuid4()}",
            "ufanet_device_title": DEFAULT_DEVICE_TITLE,
        }
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise RuntimeError("State file must contain a JSON object")
    data.setdefault("version", STATE_VERSION)
    data.setdefault("persistent_ids", [])
    data.setdefault("fcm_credentials", None)
    data.setdefault("ufanet_device_title", DEFAULT_DEVICE_TITLE)
    data.setdefault(
        "ufanet_device_id",
        f"{data['ufanet_device_title']}_{uuid.uuid4()}",
    )
    return data


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    try:
        os.chmod(tmp, stat.S_IREAD | stat.S_IWRITE)
    except OSError:
        pass
    os.replace(tmp, path)
    try:
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
    except OSError:
        pass


def load_firebase_config(path: Path) -> dict[str, str]:
    if not path.exists():
        raise RuntimeError(
            f"Firebase config not found: {path}. Run extract_firebase_config.py "
            "against your own decompiled/app resources first."
        )
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise RuntimeError("Firebase config must contain a JSON object")

    raw = payload.get("firebase", payload)
    if not isinstance(raw, dict):
        raise RuntimeError("Firebase config has no firebase object")

    config: dict[str, str] = {}
    missing: list[str] = []
    for field in REQUIRED_FIREBASE_FIELDS:
        value = raw.get(field)
        if value is None or not str(value).strip():
            missing.append(field)
        else:
            config[field] = str(value).strip()
    if missing:
        raise RuntimeError(f"Firebase config is missing required fields: {', '.join(missing)}")

    sender = config["sender_id"]
    app_parts = config["app_id"].split(":")
    if not sender.isdigit():
        raise RuntimeError("Firebase sender_id must be numeric")
    if len(app_parts) < 4 or app_parts[2] != "android":
        raise RuntimeError("Firebase app_id does not look like an Android app id")
    if app_parts[1] != sender:
        raise RuntimeError("Firebase sender_id does not match app_id project number")
    return config


def firebase_identity_fingerprint(config: dict[str, str]) -> str:
    identity = "\n".join(
        config[field] for field in ("project_id", "sender_id", "app_id", "package_name")
    )
    return _fingerprint(identity)


def bind_state_to_firebase_config(
    state: dict[str, Any],
    state_path: Path,
    config: dict[str, str],
) -> None:
    current = firebase_identity_fingerprint(config)
    previous = state.get("firebase_config_fingerprint")
    if previous and previous != current and state.get("fcm_credentials"):
        raise RuntimeError(
            "firebase_config.json describes a different Firebase application than the "
            "existing fcm_state.json. Move/delete the state file or restore the matching config."
        )
    if previous != current:
        state["firebase_config_fingerprint"] = current
        save_state(state_path, state)


def parse_history_delays(raw: str) -> tuple[float, ...]:
    try:
        values = tuple(float(value.strip()) for value in raw.split(",") if value.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "history delays must be comma-separated seconds"
        ) from exc
    if not values:
        raise argparse.ArgumentTypeError("at least one history delay is required")
    if any(value < 0 for value in values):
        raise argparse.ArgumentTypeError("history delays cannot be negative")
    if tuple(sorted(values)) != values:
        raise argparse.ArgumentTypeError("history delays must be in ascending order")
    return values


def parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


async def ufanet_login(
    session: aiohttp.ClientSession,
    username: str,
    password: str,
    base_url: str,
) -> str:
    url = f"{base_url}/api/v1/auth/auth_by_contract/"
    async with session.post(
        url,
        json={"contract": username.upper(), "password": password},
        timeout=aiohttp.ClientTimeout(total=30),
    ) as response:
        text = await response.text()
        if response.status >= 400:
            raise RuntimeError(f"Ufanet login failed: HTTP {response.status}")
        try:
            payload = json.loads(text)
            return str(payload["token"]["access"])
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise RuntimeError("Unexpected Ufanet login response") from exc


async def register_token_with_ufanet(
    session: aiohttp.ClientSession,
    access_token: str,
    fcm_token: str,
    device_id: str,
    title: str,
    package_name: str,
    base_url: str,
) -> None:
    url = f"{base_url}/api/v0/fcm/"
    body = {
        "token": fcm_token,
        "device_id": device_id,
        "title": title,
        "application": package_name,
        "os": 0,
        "token_type": 0,
    }
    async with session.post(
        url,
        headers={
            "Authorization": f"JWT {access_token.replace('JWT ', '')}",
            "Accept": "application/json",
        },
        json=body,
        timeout=aiohttp.ClientTimeout(total=30),
    ) as response:
        text = await response.text()
        if response.status >= 400:
            raise RuntimeError(f"Ufanet FCM registration failed: HTTP {response.status}")
        print(f"[OK] Ufanet accepted FCM registration: HTTP {response.status}")
        if text:
            try:
                print("[INFO] Sanitized response:")
                print(json.dumps(sanitize(json.loads(text)), ensure_ascii=False, indent=2))
            except json.JSONDecodeError:
                print(f"[INFO] Response body length: {len(text)}")


async def unregister_token_with_ufanet(
    session: aiohttp.ClientSession,
    access_token: str,
    device_id: str,
    base_url: str,
) -> None:
    """Remove only this probe's virtual FCM registration."""
    url = f"{base_url}/api/v0/fcm/"
    async with session.delete(
        url,
        headers={
            "Authorization": f"JWT {access_token.replace('JWT ', '')}",
            "Accept": "application/json",
        },
        json={"device_id": device_id},
        timeout=aiohttp.ClientTimeout(total=30),
    ) as response:
        text = await response.text()
        if response.status >= 400:
            raise RuntimeError(
                f"Ufanet FCM unregistration failed: HTTP {response.status}"
            )
        print(f"[OK] Ufanet removed the probe FCM registration: HTTP {response.status}")
        if text:
            try:
                print("[INFO] Sanitized response:")
                print(json.dumps(sanitize(json.loads(text)), ensure_ascii=False, indent=2))
            except json.JSONDecodeError:
                print(f"[INFO] Response body length: {len(text)}")


async def verify_unregister_with_ufanet(
    session: aiohttp.ClientSession,
    access_token: str,
    fcm_token: str,
    device_id: str,
    title: str,
    package_name: str,
    base_url: str,
) -> None:
    """Live-check DELETE for the probe registration, then restore it immediately."""
    print(
        "[INFO] Verifying DELETE /api/v0/fcm/ for this probe's virtual registration..."
    )
    await unregister_token_with_ufanet(
        session,
        access_token,
        device_id,
        base_url,
    )
    print("[INFO] Restoring the probe FCM registration...")
    try:
        await register_token_with_ufanet(
            session,
            access_token,
            fcm_token,
            device_id,
            title,
            package_name,
            base_url,
        )
    except Exception as exc:
        raise RuntimeError(
            "DELETE succeeded, but restoring the probe FCM registration failed. "
            "Run probe.py again without --verify-unregister to restore it."
        ) from exc
    print("[OK] FCM unregister contract verified and probe registration restored")


async def fetch_call_history(
    session: aiohttp.ClientSession,
    access_token: str,
    base_url: str,
    *,
    page_size: int,
) -> list[dict[str, Any]]:
    url = f"{base_url}/api/v1/skuds/call-history/"
    async with session.get(
        url,
        headers={
            "Authorization": f"JWT {access_token.replace('JWT ', '')}",
            "Accept": "application/json",
        },
        params={"page": 1, "page_size": int(page_size)},
        timeout=aiohttp.ClientTimeout(total=15),
    ) as response:
        text = await response.text()
        if response.status >= 400:
            raise RuntimeError(f"call-history failed: HTTP {response.status}")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Unexpected call-history response") from exc

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return [item for item in payload["results"] if isinstance(item, dict)]
    raise RuntimeError("Unexpected call-history response schema")


def find_history_match(
    push_data: dict[str, Any],
    calls: list[dict[str, Any]],
    tolerance_seconds: float,
) -> tuple[dict[str, Any], float] | None:
    push_time = parse_iso_datetime(push_data.get("time"))
    if push_time is None:
        return None

    push_house_id = push_data.get("house_id")
    push_flat = push_data.get("flat")
    candidates: list[tuple[float, dict[str, Any]]] = []

    for item in calls:
        called_at = parse_iso_datetime(item.get("called_at"))
        if called_at is None:
            continue
        delta = abs((called_at - push_time).total_seconds())
        if delta > tolerance_seconds:
            continue
        if (
            push_house_id not in (None, "")
            and item.get("house_id") not in (None, "")
            and str(item["house_id"]) != str(push_house_id)
        ):
            continue
        if (
            push_flat not in (None, "")
            and item.get("flat") not in (None, "")
            and str(item["flat"]) != str(push_flat)
        ):
            continue
        candidates.append((delta, item))

    if not candidates:
        return None
    candidates.sort(key=lambda entry: entry[0])
    delta, item = candidates[0]
    return item, delta


def print_latency_stats(samples: list[float]) -> None:
    if not samples:
        return
    print(
        "[STATS] successful_correlations="
        f"{len(samples)} min={min(samples):.3f}s "
        f"median={statistics.median(samples):.3f}s "
        f"avg={statistics.fmean(samples):.3f}s "
        f"max={max(samples):.3f}s"
    )


async def check_mcs_port() -> None:
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection("mtalk.google.com", 5228), timeout=5
        )
        writer.close()
        await writer.wait_closed()
        print("[OK] TCP mtalk.google.com:5228 reachable")
    except Exception as exc:
        print(
            f"[WARN] Cannot pre-connect to mtalk.google.com:5228: {type(exc).__name__}. "
            "The FCM client may still retry, but check firewall/NAT if listening fails."
        )


async def run(args: argparse.Namespace) -> int:
    state_path = Path(args.state).expanduser().resolve()
    firebase_path = Path(args.firebase_config).expanduser().resolve()
    state = load_state(state_path)
    firebase = load_firebase_config(firebase_path)
    bind_state_to_firebase_config(state, state_path, firebase)
    history_delays = args.history_delays
    base_url = args.ufanet_base_url.rstrip("/")

    print(
        "[INFO] Loaded local Firebase configuration: "
        f"identity_sha256={firebase_identity_fingerprint(firebase)}"
    )

    persistent_ids = state.get("persistent_ids")
    if not isinstance(persistent_ids, list):
        persistent_ids = []
        state["persistent_ids"] = persistent_ids

    first_done = asyncio.Event()
    correlation_tasks: set[asyncio.Task[Any]] = set()
    latency_samples: list[float] = []
    ufanet_session: aiohttp.ClientSession | None = None
    ufanet_access: str | None = None

    def persist_credentials(credentials: dict[str, Any]) -> None:
        state["fcm_credentials"] = credentials
        save_state(state_path, state)
        print("[OK] FCM credentials saved locally")

    async def correlate_sip_push(notification: dict[str, Any]) -> None:
        started = time.perf_counter()
        data = notification.get("data")
        if not isinstance(data, dict):
            print("[HISTORY] SIP push has no data object; correlation skipped")
            first_done.set()
            return
        if ufanet_session is None or ufanet_access is None:
            print("[HISTORY] Ufanet session unavailable; correlation skipped")
            first_done.set()
            return

        print(f"[HISTORY] correlating SIP push time={data.get('time')!r}")
        try:
            for attempt, scheduled_delay in enumerate(history_delays, start=1):
                wait_for = started + scheduled_delay - time.perf_counter()
                if wait_for > 0:
                    await asyncio.sleep(wait_for)

                request_started = time.perf_counter()
                try:
                    calls = await fetch_call_history(
                        ufanet_session,
                        ufanet_access,
                        base_url,
                        page_size=args.history_page_size,
                    )
                except Exception as exc:
                    elapsed = time.perf_counter() - started
                    print(
                        f"[HISTORY] attempt {attempt} (+{elapsed:.3f}s): "
                        f"request failed: {type(exc).__name__}: {exc}"
                    )
                    continue

                request_duration = time.perf_counter() - request_started
                elapsed = time.perf_counter() - started
                match = find_history_match(data, calls, args.history_time_tolerance)
                if match is None:
                    print(
                        f"[HISTORY] attempt {attempt} (+{elapsed:.3f}s, "
                        f"HTTP {request_duration:.3f}s): not found"
                    )
                    continue

                item, timestamp_delta = match
                push_uuid = data.get("uuid")
                history_uuid = item.get("uuid")
                relation = (
                    "SAME"
                    if push_uuid and history_uuid and str(push_uuid) == str(history_uuid)
                    else "DIFFERENT"
                )
                latency_samples.append(elapsed)
                print(
                    f"[HISTORY] attempt {attempt} (+{elapsed:.3f}s, "
                    f"HTTP {request_duration:.3f}s): FOUND"
                )
                print("[RESULT] call-history correlation")
                print(f"  observed_after:   <= {elapsed:.3f} s")
                print(f"  timestamp_delta:  {timestamp_delta:.3f} s")
                print(f"  push_uuid:        {_redacted(push_uuid)}")
                print(f"  history_uuid:     {_redacted(history_uuid)}")
                print(f"  uuid_relation:    {relation}")
                print_latency_stats(latency_samples)
                return

            elapsed = time.perf_counter() - started
            print(
                "[RESULT] matching call-history entry was not observed "
                f"within {elapsed:.3f}s"
            )
        finally:
            first_done.set()

    def on_push(notification: dict[str, Any], persistent_id: str, _context: Any) -> None:
        print("\n=== FCM PUSH RECEIVED ===")
        print(f"persistent_id: {_redacted(persistent_id)}")
        print(json.dumps(sanitize(notification), ensure_ascii=False, indent=2, sort_keys=True))
        if persistent_id and persistent_id not in persistent_ids:
            persistent_ids.append(persistent_id)
            if len(persistent_ids) > 100:
                del persistent_ids[:-100]
            save_state(state_path, state)

        data = notification.get("data") if isinstance(notification, dict) else None
        if (
            not args.no_correlate_history
            and isinstance(data, dict)
            and data.get("reason") == "sip"
        ):
            task = asyncio.create_task(correlate_sip_push(notification))
            correlation_tasks.add(task)
            task.add_done_callback(correlation_tasks.discard)
        else:
            first_done.set()

    fcm_config = FcmRegisterConfig(
        project_id=firebase["project_id"],
        app_id=firebase["app_id"],
        api_key=firebase["api_key"],
        messaging_sender_id=firebase["sender_id"],
        bundle_id=firebase["package_name"],
        persistend_ids=persistent_ids,
    )

    client = FcmPushClient(
        on_push,
        fcm_config,
        credentials=state.get("fcm_credentials"),
        credentials_updated_callback=persist_credentials,
        received_persistent_ids=persistent_ids,
    )

    print("[INFO] Registering/checking in virtual FCM device...")
    fcm_token = await client.checkin_or_register()
    print(f"[OK] FCM token obtained: {_redacted(fcm_token)}")
    if not state_path.exists():
        save_state(state_path, state)

    try:
        if not args.skip_ufanet:
            username = args.username or os.getenv("UFANET_USERNAME")
            if not username:
                username = input("Ufanet contract/login: ").strip()
            password = os.getenv("UFANET_PASSWORD")
            if not password:
                password = getpass.getpass("Ufanet password: ")
            if not username or not password:
                raise RuntimeError("Ufanet username/password are required")

            ufanet_session = aiohttp.ClientSession()
            print("[INFO] Authenticating to Ufanet...")
            ufanet_access = await ufanet_login(
                ufanet_session, username, password, base_url
            )
            print("[OK] Ufanet authentication succeeded")
            await register_token_with_ufanet(
                ufanet_session,
                ufanet_access,
                fcm_token,
                str(state["ufanet_device_id"]),
                str(state["ufanet_device_title"]),
                firebase["package_name"],
                base_url,
            )
            if args.verify_unregister:
                await verify_unregister_with_ufanet(
                    ufanet_session,
                    ufanet_access,
                    fcm_token,
                    str(state["ufanet_device_id"]),
                    str(state["ufanet_device_title"]),
                    firebase["package_name"],
                    base_url,
                )
                print("[OK] Unregister verification completed; listener was not started")
                return 0

        if args.skip_ufanet and not args.no_correlate_history:
            print("[INFO] History correlation disabled because --skip-ufanet is active")

        await check_mcs_port()
        print("[INFO] Starting MCS listener (mtalk.google.com:5228)...")
        await client.start()
        if not args.no_correlate_history and not args.skip_ufanet:
            delays_text = ", ".join(f"{value:g}" for value in history_delays)
            print(
                "[OK] Listener started. SIP push -> automatic call-history probes "
                f"at [{delays_text}] seconds."
            )
        else:
            print("[OK] Listener started. Ring the intercom now. Ctrl+C to stop.")

        if args.once:
            await first_done.wait()
            if correlation_tasks:
                await asyncio.gather(*tuple(correlation_tasks), return_exceptions=True)
            await asyncio.sleep(0.2)
        else:
            await asyncio.Event().wait()
    finally:
        if correlation_tasks:
            for task in tuple(correlation_tasks):
                task.cancel()
            await asyncio.gather(*tuple(correlation_tasks), return_exceptions=True)
        await client.stop()
        if ufanet_session is not None:
            await ufanet_session.close()

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Headless Ufanet FCM receiver research probe for Windows/Python"
    )
    parser.add_argument(
        "--firebase-config",
        default=str(Path(__file__).with_name("firebase_config.json")),
        help="JSON produced locally by extract_firebase_config.py",
    )
    parser.add_argument(
        "--state",
        default=str(Path(__file__).with_name("fcm_state.json")),
        help="Path to local sensitive FCM state JSON",
    )
    parser.add_argument("--username", help="Ufanet contract/login")
    parser.add_argument(
        "--ufanet-base-url",
        default=UFANET_BASE_URL,
        help="Ufanet API base URL",
    )
    parser.add_argument(
        "--skip-ufanet",
        action="store_true",
        help="Only create/listen on FCM; do not register the token with Ufanet",
    )
    parser.add_argument(
        "--verify-unregister",
        action="store_true",
        help=(
            "Live-check DELETE /api/v0/fcm/ for this probe's own virtual device, "
            "immediately register it again, then exit"
        ),
    )
    parser.add_argument(
        "--no-correlate-history",
        action="store_true",
        help="Do not query call-history after SIP pushes",
    )
    parser.add_argument(
        "--history-delays",
        type=parse_history_delays,
        default=DEFAULT_HISTORY_DELAYS,
        metavar="SECONDS",
        help="Absolute retry offsets after push, comma-separated (default: 0,0.25,0.5,1,2,5)",
    )
    parser.add_argument(
        "--history-page-size",
        type=int,
        default=25,
        help="Number of latest call-history rows to inspect (default: 25)",
    )
    parser.add_argument(
        "--history-time-tolerance",
        type=float,
        default=1.0,
        help="Maximum |called_at - push.time| in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Exit after the first push and, for SIP, after correlation completes",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.verify_unregister and args.skip_ufanet:
        print(
            "[ERROR] --verify-unregister cannot be used with --skip-ufanet",
            file=sys.stderr,
        )
        return 2
    if args.history_page_size < 1:
        print("[ERROR] --history-page-size must be >= 1", file=sys.stderr)
        return 2
    if args.history_time_tolerance < 0:
        print("[ERROR] --history-time-tolerance cannot be negative", file=sys.stderr)
        return 2
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted")
        return 130
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
