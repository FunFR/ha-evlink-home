"""Charging switch of the EVlink Home Wallboxes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import CannotConnectError, InvalidCredentialsError, WiserHomeError
from .const import DOMAIN
from .coordinator import EvlinkHomeConfigEntry
from .entity import EvlinkHomeEntity, async_add_wallbox_entities

PARALLEL_UPDATES = 1

CHARGING = SwitchEntityDescription(key="charging", translation_key="charging")

_CHARGING_STATUSES = frozenset({"Charging", "SuspendedEv"})

_ERROR_KEYS: dict[type[WiserHomeError], str] = {
    CannotConnectError: "cannot_connect",
    InvalidCredentialsError: "invalid_credentials",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EvlinkHomeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the Charging switch of every Wallbox."""
    coordinator = entry.runtime_data
    async_add_wallbox_entities(
        entry,
        async_add_entities,
        lambda device_id: [EvlinkHomeChargingSwitch(coordinator, device_id, CHARGING)],
    )


class EvlinkHomeChargingSwitch(EvlinkHomeEntity, SwitchEntity):
    """On while the Wallbox charges the car; Start and Stop drive it."""

    _requested: bool | None = None
    _refreshing = False

    @property
    def is_on(self) -> bool:
        if self._requested is not None:
            return self._requested
        return self.wallbox.status in _CHARGING_STATUSES

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self.wallbox.status == "Unplugged":
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="no_car_plugged_in"
            )
        await self._command(self.coordinator.client.start, requested=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._command(self.coordinator.client.stop, requested=False)

    async def _command(
        self, send: Callable[[str], Awaitable[None]], *, requested: bool
    ) -> None:
        """Send the command, show ``requested`` until the next scheduled poll."""
        try:
            await send(self.device_id)
        except WiserHomeError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key=_ERROR_KEYS.get(type(err), "unexpected_response"),
            ) from err
        self._requested = requested
        self.async_write_ha_state()
        self._refreshing = True
        try:
            await self.coordinator.async_refresh()
        finally:
            self._refreshing = False

    @callback
    def _handle_coordinator_update(self) -> None:
        if not self._refreshing:
            self._requested = None
        super()._handle_coordinator_update()
