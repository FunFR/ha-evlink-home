"""The EVlink Home integration."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .coordinator import EvlinkHomeConfigEntry, EvlinkHomeCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: EvlinkHomeConfigEntry) -> bool:
    """Set up EVlink Home from a config entry."""
    coordinator = EvlinkHomeCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: EvlinkHomeConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow removing a Wallbox that the account no longer lists."""
    return not any(
        domain == DOMAIN and device_id in entry.runtime_data.data
        for domain, device_id in device.identifiers
    )


async def async_unload_entry(hass: HomeAssistant, entry: EvlinkHomeConfigEntry) -> bool:
    """Unload an EVlink Home config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
