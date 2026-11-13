"""Tests for the base entity the EVlink Home platforms share."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.evlink_home.const import DOMAIN
from custom_components.evlink_home.entity import EvlinkHomeEntity

from .common import DEVICE_ID


def status_entity(entry: MockConfigEntry) -> EvlinkHomeEntity:
    return EvlinkHomeEntity(
        entry.runtime_data, DEVICE_ID, EntityDescription(key="status")
    )


async def test_entity_belongs_to_its_wallbox_device(
    loaded_entry: MockConfigEntry,
) -> None:
    entity = status_entity(loaded_entry)

    assert entity.has_entity_name
    assert entity.unique_id == f"{DEVICE_ID}_status"
    assert entity.device_info == DeviceInfo(
        identifiers={(DOMAIN, DEVICE_ID)},
        name="REDACTED_name",
        manufacturer="Schneider Electric",
        model="EVH4A07N400F",
        sw_version="2.0.7.0.0_f135",
        serial_number="REDACTED_serialNumber",
    )
    assert entity.wallbox.status == "SchedulePaused"
    assert entity.available


async def test_entity_of_a_wallbox_gone_from_the_cloud_is_unavailable(
    loaded_entry: MockConfigEntry,
) -> None:
    entity = status_entity(loaded_entry)

    loaded_entry.runtime_data.async_set_updated_data({})

    assert not entity.available
