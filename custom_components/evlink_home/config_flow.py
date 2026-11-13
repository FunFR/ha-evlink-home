"""Config flow for the EVlink Home integration."""

from homeassistant.config_entries import ConfigFlow

from .const import DOMAIN


class EvlinkHomeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EVlink Home."""

    VERSION = 1
