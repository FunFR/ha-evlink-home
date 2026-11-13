"""Binary sensors of the EVlink Home Wallboxes, derived from the status."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import STATUSES
from .coordinator import EvlinkHomeConfigEntry
from .entity import EvlinkHomeEntity

PARALLEL_UPDATES = 0

_PLUGGED_IN = {
    "charging",
    "paused",
    "plugged_in",
    "schedule_paused",
    "stopped",
    "suspended_dso",
    "suspended_ev",
}
_UNPLUGGED = {"unplugged"}


def _plugged_in(status: str | None) -> bool | None:
    """Whether a car is plugged in, unknown when the status does not tell."""
    if status in _PLUGGED_IN:
        return True
    if status in _UNPLUGGED:
        return False
    return None


@dataclass(frozen=True, kw_only=True)
class EvlinkHomeBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Binary sensor read from the Wallbox status."""

    is_on_fn: Callable[[str | None], bool | None]


BINARY_SENSORS: tuple[EvlinkHomeBinarySensorEntityDescription, ...] = (
    EvlinkHomeBinarySensorEntityDescription(
        key="plugged_in",
        translation_key="plugged_in",
        device_class=BinarySensorDeviceClass.PLUG,
        is_on_fn=_plugged_in,
    ),
    EvlinkHomeBinarySensorEntityDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        is_on_fn=lambda status: status == "charging",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EvlinkHomeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the binary sensors of every Wallbox of the account."""
    coordinator = entry.runtime_data
    async_add_entities(
        EvlinkHomeBinarySensor(coordinator, device_id, description)
        for device_id in coordinator.data
        for description in BINARY_SENSORS
    )


class EvlinkHomeBinarySensor(EvlinkHomeEntity, BinarySensorEntity):
    """Binary sensor of one Wallbox."""

    entity_description: EvlinkHomeBinarySensorEntityDescription

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.is_on_fn(STATUSES.get(self.charger.status))
