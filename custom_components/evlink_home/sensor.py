"""Sensors of the EVlink Home Wallboxes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .api import Charger
from .const import STATUSES
from .coordinator import EvlinkHomeConfigEntry, EvlinkHomeCoordinator
from .entity import EvlinkHomeEntity, async_add_wallbox_entities

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class EvlinkHomeSensorEntityDescription(SensorEntityDescription):
    """Sensor read from the Wallbox record."""

    value_fn: Callable[[Charger], StateType | datetime]


def _home_time(value: datetime | None) -> datetime | None:
    """Attach the Home Assistant time zone, assumed to be the Wallbox's."""
    if value is None:
        return None
    return value.replace(tzinfo=dt_util.get_default_time_zone())


SENSORS: tuple[EvlinkHomeSensorEntityDescription, ...] = (
    EvlinkHomeSensorEntityDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=list(STATUSES.values()),
        value_fn=lambda charger: STATUSES.get(charger.status),
    ),
    EvlinkHomeSensorEntityDescription(
        key="next_scheduled_start",
        translation_key="next_scheduled_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda charger: _home_time(charger.next_scheduled_start),
    ),
    EvlinkHomeSensorEntityDescription(
        key="next_scheduled_end",
        translation_key="next_scheduled_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda charger: _home_time(charger.next_scheduled_end),
    ),
)


SESSION_ENERGY = SensorEntityDescription(
    key="session_energy",
    translation_key="session_energy",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL_INCREASING,
    native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    suggested_display_precision=2,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EvlinkHomeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the sensors of every Wallbox of the account."""
    coordinator = entry.runtime_data

    def sensors_of(device_id: str) -> list[SensorEntity]:
        return [
            *(
                EvlinkHomeSensor(coordinator, device_id, description)
                for description in SENSORS
            ),
            EvlinkHomeSessionEnergySensor(coordinator, device_id, SESSION_ENERGY),
        ]

    async_add_wallbox_entities(entry, async_add_entities, sensors_of)


class EvlinkHomeSensor(EvlinkHomeEntity, SensorEntity):
    """Sensor of one Wallbox."""

    entity_description: EvlinkHomeSensorEntityDescription

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.charger)


class EvlinkHomeSessionEnergySensor(EvlinkHomeEntity, SensorEntity):
    """Energy of the Charge session, kept while the cloud reports none.

    The cloud forgets the total once the car is unplugged. Keeping it lets
    the next session's lower total read as a meter reset.
    """

    def __init__(
        self,
        coordinator: EvlinkHomeCoordinator,
        device_id: str,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, device_id, description)
        self._attr_native_value = self.charger.session_energy_kwh

    @callback
    def _handle_coordinator_update(self) -> None:
        if (
            self.device_id in self.coordinator.data
            and self.charger.session_energy_kwh is not None
        ):
            self._attr_native_value = self.charger.session_energy_kwh
        super()._handle_coordinator_update()
