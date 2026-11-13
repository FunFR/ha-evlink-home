"""The EVlink Home integration."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import EvlinkHomeConfigEntry, EvlinkHomeCoordinator

PLATFORMS: list[Platform] = []


async def async_setup_entry(hass: HomeAssistant, entry: EvlinkHomeConfigEntry) -> bool:
    """Set up EVlink Home from a config entry."""
    coordinator = EvlinkHomeCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EvlinkHomeConfigEntry) -> bool:
    """Unload an EVlink Home config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
