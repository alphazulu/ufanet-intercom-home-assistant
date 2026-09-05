"""Privacy-safe physical-key inventory support for Ufanet Intercom."""

from __future__ import annotations

from typing import Any, TypedDict

from .api import PhysicalKey, UfanetApi as BaseUfanetApi, UfanetResponseError


class PhysicalKeyInventoryItem(PhysicalKey):
    """Normalized physical key retained only in Home Assistant memory."""

    name: str
    created_at: int


class UfanetApi(BaseUfanetApi):
    """Extend the base API with the read-only physical-key inventory fields."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._physical_key_inventory: tuple[PhysicalKeyInventoryItem, ...] = ()

    @property
    def physical_key_inventory(self) -> tuple[PhysicalKeyInventoryItem, ...]:
        """Return the latest normalized key inventory without external IDs."""
        return self._physical_key_inventory

    async def async_get_physical_keys(self) -> list[PhysicalKeyInventoryItem]:
        """Return physical keys needed for counting and read-only presentation.

        The Android model also contains ``external_id``. It is intentionally
        discarded while parsing because it is an access identifier and is not
        needed by the Home Assistant integration.
        """
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
            name = item.get("name")
            created_at = item.get("create_date")
            raw_devices = item.get("devices")
            if (
                not isinstance(key_id, int)
                or isinstance(key_id, bool)
                or key_id < 1
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
                    "name": name,
                    "created_at": created_at,
                    "devices": tuple(devices),
                }
            )

        self._physical_key_inventory = tuple(keys)
        return list(keys)
