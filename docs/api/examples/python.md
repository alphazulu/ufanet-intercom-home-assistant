# Python read-only example

This minimal example demonstrates the authentication chain, SKUD discovery, UCAMS exchange, minimal analytics capability discovery, and a privacy-safe read-only `motion_alarm` query. It intentionally does **not** open the door, modify guest access, print provider identifiers, or dump raw event history.

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from typing import Any

import requests

UFANET = "https://dom.ufanet.ru"
UCAMS = "https://cloud.ucams.ru"

contract = os.environ["UFANET_CONTRACT"]
password = os.environ["UFANET_PASSWORD"]

session = requests.Session()


def find_camera(value: Any, camera_number: str) -> dict[str, Any] | None:
    """Find the requested camera object without printing the private response."""
    if isinstance(value, dict):
        if value.get("number") == camera_number:
            return value
        for child in value.values():
            found = find_camera(child, camera_number)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_camera(child, camera_number)
            if found is not None:
                return found
    return None


# 1. Ufanet login
r = session.post(
    f"{UFANET}/api/v1/auth/auth_by_contract/",
    json={"contract": contract, "password": password},
    timeout=20,
)
r.raise_for_status()
auth = r.json()
ufanet_access = auth["token"]["access"]
ufanet_headers = {"Authorization": f"JWT {ufanet_access}"}

# 2. Intercom discovery
r = session.get(
    f"{UFANET}/api/v0/skud/shared/",
    headers=ufanet_headers,
    timeout=20,
)
r.raise_for_status()
skuds = r.json()

if not isinstance(skuds, list) or not skuds:
    raise RuntimeError("No shared SKUD/intercom objects returned")

skud = skuds[0]
camera_number = skud.get("cctv_number")
if not isinstance(camera_number, str) or not camera_number:
    raise RuntimeError("Selected intercom has no UCAMS camera number")

# 3. Ufanet JWT -> UCAMS bearer token
r = session.post(
    f"{UCAMS}/api/v0/auth/?ttl=20800",
    headers=ufanet_headers,
    timeout=20,
)
r.raise_for_status()
ucams_token = r.json()["token"]
ucams_headers = {"Authorization": f"Bearer {ucams_token}"}

# 4. Minimal analytics capability discovery used by v0.28.0
r = session.post(
    f"{UCAMS}/api/v0/cameras/this/",
    headers=ucams_headers,
    json={
        "fields": ["number", "analytics"],
        "numbers": [camera_number],
    },
    timeout=20,
)
r.raise_for_status()
camera_response = r.json()
camera = find_camera(camera_response, camera_number)

analytics = camera.get("analytics") if camera is not None else None
motion_supported = isinstance(analytics, list) and "motion_alarm" in analytics
print("Camera metadata received:", camera is not None)
print("motion_alarm advertised:", motion_supported)

# 5. Query the confirmed read-only report only when the camera advertises it.
if motion_supported:
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=5)
    r = session.post(
        f"{UCAMS}/api/v0/analytics/motion_alarm/report/",
        headers=ucams_headers,
        json={
            "camera_number": camera_number,
            "start": start.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "end": end.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "limit": 25,
            "order_by_date": "desc",
        },
        timeout=20,
    )
    r.raise_for_status()
    report = r.json()

    if not isinstance(report, dict):
        raise RuntimeError("Unexpected motion report envelope")

    results = report.get("results")
    page = report.get("page")
    count = report.get("count")
    if not isinstance(results, list) or not isinstance(page, dict):
        raise RuntimeError("Unexpected motion report schema")

    # Keep exact event IDs/timestamps private. A production cursor may use the
    # confirmed numeric `id` and ISO-8601 UTC `date`, but they should not be
    # printed or copied into public diagnostics/logs.
    valid = 0
    for item in results:
        if not isinstance(item, dict):
            continue
        event_id = item.get("id")
        event_date = item.get("date")
        if isinstance(event_id, int) and not isinstance(event_id, bool) and isinstance(event_date, str):
            valid += 1

    print("Motion report received:", True)
    print("Returned result count:", len(results))
    print("Results with confirmed id/date types:", valid)
    print("Server count present:", isinstance(count, int) and not isinstance(count, bool))
    print("Pagination metadata present:", bool(page))
```

## Analytics-specific cautions

- `motion_alarm` is Confirmed; `perimeter_security` remains Observed only and should not be called merely because it exists in decompiled client code.
- The live wire timestamp is `date`; do not substitute the Android DTO field `time` or apply an archive playback offset.
- Treat `id` as private cursor material, not user-facing event data.
- Do not assume the requested `limit` bounds the returned page. The live service returned `page_size=60` despite a smaller requested value.
- No pagination request field such as `page`/`offset` has been live-confirmed for this report. Production v0.28.0 safely resolves incomplete reports by splitting the confirmed `start`/`end` interval and never advancing the cursor past an unresolved gap.
- Preserve fractional `date` precision if you persist a replay cursor; truncating it can replay an already processed event after restart.
- The first successful production poll should establish a baseline instead of replaying existing history; an empty baseline should use the poll time rather than Unix epoch.

## Production recommendations

- Use `httpx.AsyncClient`/`aiohttp` or another async client in asynchronous applications.
- Implement token expiration/refresh rather than logging in for every request.
- Never print or persist raw tokens in diagnostics.
- Treat all camera/analytics responses as private API structures: validate types and discard unknown fields at the boundary.
- Keep provider camera IDs, event IDs, exact raw history, media, screenshots, and recognition data out of public entities/logs/diagnostics.
- Sanitize API failures before passing them to user-visible logs; response bodies can contain private values.
- Before reading an archive clip, query recording ranges first.
- Do not automatically call physical/state-changing endpoints during startup or health checks.

The Home Assistant integration in this repository contains the more complete production implementation described in [../analytics.md](../analytics.md).
