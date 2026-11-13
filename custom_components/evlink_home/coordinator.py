"""Polling of the Wiser Home cloud for every Wallbox of the account."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    CannotConnectError,
    InvalidCredentialsError,
    UnexpectedResponseError,
    Wallbox,
    WiserHomeClient,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

type EvlinkHomeConfigEntry = ConfigEntry[EvlinkHomeCoordinator]


class EvlinkHomeCoordinator(DataUpdateCoordinator[dict[str, Wallbox]]):
    """Wallboxes of one Wiser Home account, keyed by device id."""

    config_entry: EvlinkHomeConfigEntry

    def __init__(self, hass: HomeAssistant, entry: EvlinkHomeConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
        )
        self.client = WiserHomeClient(
            async_get_clientsession(hass),
            entry.data[CONF_EMAIL],
            entry.data[CONF_PASSWORD],
        )

    async def _async_setup(self) -> None:
        with _cloud_errors():
            await self.client.login()

    async def _async_update_data(self) -> dict[str, Wallbox]:
        with _cloud_errors():
            wallboxes = await self.client.get_wallboxes()
        return {wallbox.device_id: wallbox for wallbox in wallboxes}


@contextmanager
def _cloud_errors() -> Iterator[None]:
    """Turn client errors into the coordinator's reauth and outage signals."""
    try:
        yield
    except InvalidCredentialsError as err:
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN, translation_key="invalid_credentials"
        ) from err
    except CannotConnectError as err:
        raise UpdateFailed(
            translation_domain=DOMAIN, translation_key="cannot_connect"
        ) from err
    except UnexpectedResponseError as err:
        raise UpdateFailed(
            translation_domain=DOMAIN, translation_key="unexpected_response"
        ) from err
