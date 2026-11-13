"""Base entity shared by the EVlink Home platforms."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Charger
from .const import DOMAIN
from .coordinator import EvlinkHomeCoordinator


class EvlinkHomeEntity(CoordinatorEntity[EvlinkHomeCoordinator]):
    """Entity of one Wallbox, named after its description's translation key."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EvlinkHomeCoordinator,
        device_id: str,
        description: EntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self.device_id = device_id
        self._attr_unique_id = f"{device_id}_{description.key}"
        charger = coordinator.data[device_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=charger.name,
            manufacturer="Schneider Electric",
            model=charger.model,
            sw_version=charger.firmware,
            serial_number=charger.serial_number,
        )

    @property
    def available(self) -> bool:
        return super().available and self.device_id in self.coordinator.data

    @property
    def charger(self) -> Charger:
        """The Wallbox record of the last poll."""
        return self.coordinator.data[self.device_id]
