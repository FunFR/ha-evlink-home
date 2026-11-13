"""Diagnostics for EVlink Home, without the account or the Wallbox identity."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .coordinator import EvlinkHomeConfigEntry

TO_REDACT = {
    CONF_EMAIL,
    CONF_PASSWORD,
    "title",
    "unique_id",
    "deviceId",
    "cloudDeviceId",
    "hubDeviceId",
    "hubEvseId",
    "EquipmentId",
    "serialNumber",
    "name",
    "productIdentifier",
    "wiFiSsid",
    "wiFiPassword",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: EvlinkHomeConfigEntry
) -> dict[str, Any]:
    """Return the config entry and the cloud record of each Wallbox."""
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "wallboxes": [
            async_redact_data(wallbox.raw, TO_REDACT)
            for wallbox in entry.runtime_data.data.values()
        ],
    }
