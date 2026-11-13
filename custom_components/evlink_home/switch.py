"""Charging switch of the EVlink Home Wallboxes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import WallboxStatus, WiserHomeError
from .const import DOMAIN
from .coordinator import EvlinkHomeConfigEntry, error_translation_key
from .entity import EvlinkHomeEntity, async_add_wallbox_entities

PARALLEL_UPDATES = 1

CHARGING = SwitchEntityDescription(key="charging", translation_key="charging")

_CHARGING_STATUSES = frozenset({WallboxStatus.CHARGING, WallboxStatus.SUSPENDED_EV})


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

    @property
    def is_on(self) -> bool:
        if self._requested is not None:
            return self._requested
        return self.wallbox.status in _CHARGING_STATUSES

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self.wallbox.status is WallboxStatus.UNPLUGGED:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="no_car_plugged_in"
            )
        await self._command(self.coordinator.client.start, requested=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._command(self.coordinator.client.stop, requested=False)

    async def _command(
        self, send: Callable[[str], Awaitable[None]], *, requested: bool
    ) -> None:
        """Send the command, show ``requested`` until a poll not made for a command."""
        try:
            await send(self.device_id)
        except WiserHomeError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key=error_translation_key(err),
            ) from err
        self._requested = requested
        self.async_write_ha_state()
        await self.coordinator.async_refresh_after_command()

    @callback
    def _handle_coordinator_update(self) -> None:
        if not self.coordinator.refreshing_after_command:
            self._requested = None
        super()._handle_coordinator_update()
