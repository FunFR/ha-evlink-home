"""Base entity shared by the EVlink Home platforms."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Wallbox
from .const import DOMAIN
from .coordinator import EvlinkHomeConfigEntry, EvlinkHomeCoordinator


@callback
def async_add_wallbox_entities(
    entry: EvlinkHomeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    entities_of: Callable[[str], Iterable[Entity]],
) -> None:
    """Add the entities of each Wallbox, now and whenever the account gains one."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def add_new_wallboxes() -> None:
        new = coordinator.data.keys() - known
        if not new:
            return
        known.update(new)
        async_add_entities(
            entity for device_id in new for entity in entities_of(device_id)
        )

    add_new_wallboxes()
    entry.async_on_unload(coordinator.async_add_listener(add_new_wallboxes))


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
        wallbox = coordinator.data[device_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=wallbox.name,
            manufacturer="Schneider Electric",
            model=wallbox.model,
            sw_version=wallbox.firmware,
            serial_number=wallbox.serial_number,
        )

    @property
    def available(self) -> bool:
        return super().available and self.device_id in self.coordinator.data

    @property
    def wallbox(self) -> Wallbox:
        """The Wallbox record of the last poll."""
        return self.coordinator.data[self.device_id]
