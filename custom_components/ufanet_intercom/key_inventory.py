"""Privacy-safe physical-key inventory and passage parsing for Ufanet Intercom."""

from __future__ import annotations

from typing import Any

from .api import (
    KEY_PASSAGE_PAGE_SIZE,
    KeyPassagePage,
    PhysicalKey,
    UfanetApi as BaseUfanetApi,
    UfanetResponseError,
)


class PhysicalKeyInventoryItem(PhysicalKey):
    """Normalized physical key retained only in private Home Assistant memory."""

    external_id: str
    name: str
    created_at: int


def _coerce_passage_key_id(value: Any) -> int:
    """Mirror Gson's live-observed numeric-string coercion for passage ``key``."""
    if isinstance(value, bool):
        raise UfanetResponseError("Key-passage response contains invalid fields")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if raw.isdigit():
            return int(raw)
    raise UfanetResponseError("Key-passage response contains invalid fields")


class UfanetApi(BaseUfanetApi):
    """Extend the base API with physical-key inventory and live schema fixes."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._physical_key_inventory: tuple[PhysicalKeyInventoryItem, ...] = ()

    @property
    def physical_key_inventory(self) -> tuple[PhysicalKeyInventoryItem, ...]:
        """Return the latest private normalized key inventory.

        ``external_id`` is retained only because the official Android client uses
        it for passage-history filtering. Live validation confirmed that role and
        also showed that it does not match the number printed on the tested
        physical key. Neither ``external_id`` nor provider ``key_id`` is exposed
        through public key surfaces, diagnostics, or events.
        """
        return self._physical_key_inventory

    async def async_get_physical_keys(self) -> list[PhysicalKeyInventoryItem]:
        """Return physical keys needed for counting, presentation and filtering."""
        # Never keep stale key metadata after a failed refresh.
        self._physical_key_inventory = ()

        data = await self._async_ufanet_json("POST", "/api/v4/key/list/")
        payload = data.get("data") if isinstance(data, dict) else None
        raw_keys = payload.get("keys") if isinstance(payload, dict) else None
        if not isinstance(raw_keys, list):
            raise UfanetResponseError("Physical-key response has no key list")

        keys: list[PhysicalKeyInventoryItem] = []
        seen_ids: set[int] = set()
        for item in raw_keys:
            if not isinstance(item, dict):
                raise UfanetResponseError("Physical-key response contains invalid item")

            key_id = item.get("id")
            external_id = item.get("external_id")
            name = item.get("name")
            created_at = item.get("create_date")
            raw_devices = item.get("devices")
            if (
                not isinstance(key_id, int)
                or isinstance(key_id, bool)
                or key_id < 1
                or not isinstance(external_id, str)
                or not external_id
                or not isinstance(name, str)
                or not isinstance(created_at, int)
                or isinstance(created_at, bool)
                or created_at < 0
                or created_at > 253_402_300_799
                or not isinstance(raw_devices, list)
            ):
                raise UfanetResponseError("Physical-key response contains invalid fields")
            if key_id in seen_ids:
                raise UfanetResponseError("Physical-key response contains duplicate key ID")
            seen_ids.add(key_id)

            devices: list[int] = []
            for raw_device in raw_devices:
                if isinstance(raw_device, bool):
                    raise UfanetResponseError(
                        "Physical-key response contains invalid device reference"
                    )
                try:
                    device_id = int(raw_device)
                except (TypeError, ValueError) as err:
                    raise UfanetResponseError(
                        "Physical-key response contains invalid device reference"
                    ) from err
                if device_id < 1:
                    raise UfanetResponseError(
                        "Physical-key response contains invalid device reference"
                    )
                devices.append(device_id)

            keys.append(
                {
                    "key_id": key_id,
                    "external_id": external_id,
                    "name": name,
                    "created_at": created_at,
                    "devices": tuple(devices),
                }
            )

        self._physical_key_inventory = tuple(keys)
        return list(keys)

    async def async_get_key_passage_history(
        self,
        skud_id: int,
        *,
        page: int = 0,
        page_size: int = KEY_PASSAGE_PAGE_SIZE,
    ) -> KeyPassagePage:
        """Return passage history accepting the live numeric-string ``key`` field.

        The decompiled Android DTO declares ``key`` as an integer, while the live
        API returns it as a JSON string. Gson accepts a numeric JSON string for an
        integer field, so Home Assistant mirrors that coercion explicitly.
        """
        data = await self._async_ufanet_json(
            "POST",
            f"/api/v4/key/skud/{int(skud_id)}/key/pass_history/",
            json_body={"page": int(page), "page_size": int(page_size)},
        )
        if not isinstance(data, dict):
            raise UfanetResponseError("Unexpected key-passage response")

        pagination: dict[str, int] = {}
        for field in ("count", "current_page", "page_count", "page_size"):
            value = data.get(field)
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                raise UfanetResponseError(
                    "Key-passage response contains invalid pagination"
                )
            pagination[field] = value

        raw_results = data.get("results")
        if not isinstance(raw_results, list):
            raise UfanetResponseError("Key-passage response has no results list")

        passages = []
        for item in raw_results:
            if not isinstance(item, dict):
                raise UfanetResponseError("Key-passage response contains invalid item")
            key_id = _coerce_passage_key_id(item.get("key"))
            key_name = item.get("key_name")
            timestamp = item.get("time_passage")
            if (
                not isinstance(key_name, str)
                or not isinstance(timestamp, int)
                or isinstance(timestamp, bool)
                or timestamp <= 0
                or timestamp > 253_402_300_799
            ):
                raise UfanetResponseError("Key-passage response contains invalid fields")
            passages.append(
                {
                    "key_id": key_id,
                    "key_name": key_name,
                    "timestamp": timestamp,
                }
            )

        return {
            "count": pagination["count"],
            "current_page": pagination["current_page"],
            "page_count": pagination["page_count"],
            "page_size": pagination["page_size"],
            "results": passages,
        }
