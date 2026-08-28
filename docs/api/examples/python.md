# Python read-only example

This minimal example demonstrates the authentication chain, SKUD discovery, UCAMS exchange, camera metadata and archive-range query. It intentionally does **not** open the door or modify guest access.

```python
from __future__ import annotations

import os
import requests

UFANET = "https://dom.ufanet.ru"
UCAMS = "https://cloud.ucams.ru"

contract = os.environ["UFANET_CONTRACT"]
password = os.environ["UFANET_PASSWORD"]

session = requests.Session()
session.timeout = 20

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

if not skuds:
    raise RuntimeError("No shared SKUD/intercom objects returned")

skud = skuds[0]
camera_number = skud["cctv_number"]

# 3. Ufanet JWT -> UCAMS bearer token
r = session.post(
    f"{UCAMS}/api/v0/auth/?ttl=20800",
    headers=ufanet_headers,
    timeout=20,
)
r.raise_for_status()
ucams_token = r.json()["token"]
ucams_headers = {"Authorization": f"Bearer {ucams_token}"}

# 4. Camera metadata
r = session.post(
    f"{UCAMS}/api/v0/cameras/this/",
    headers=ucams_headers,
    json={
        "fields": [
            "number",
            "token_l",
            "token_r",
            "timezone",
            "server",
            "tariff",
            "streams_count",
        ],
        "token_l_ttl": 20800,
        "token_r_ttl": 20800,
        "numbers": [camera_number],
    },
    timeout=20,
)
r.raise_for_status()
camera_response = r.json()

# The exact private response nesting can vary. Inspect it locally and extract
# the camera item, media-server domain and token_r appropriate to your account.
# Do NOT log tokens in shared/public logs.

print("SKUD id:", skud.get("id"))
print("Camera number present:", bool(camera_number))
print("Camera metadata received:", bool(camera_response))
```

## Production recommendations

- Use `httpx.AsyncClient`/`aiohttp` or another async client in asynchronous applications.
- Implement token expiration/refresh rather than logging in for every request.
- Never print or persist raw tokens in diagnostics.
- Treat the camera metadata response as a private API structure: validate types and tolerate optional/null fields.
- Before reading an archive clip, query recording ranges first.
- Do not automatically call physical/state-changing endpoints during startup or health checks.

The Home Assistant integration in this repository contains the more complete production implementation.