"""Tests for the EVlink Home binary sensors."""

import pytest
from aioresponses import aioresponses
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy.assertion import SnapshotAssertion

from .common import UNPLUGGED, poll_record, snapshot_platform_entities

PLUGGED_IN = "binary_sensor.redacted_name_plugged_in"
ENERGY_FLOWING = "binary_sensor.redacted_name_energy_flowing"


def state_of(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    assert state is not None
    return state.state


async def test_binary_sensors_snapshot(
    hass: HomeAssistant,
    cloud: aioresponses,
    entry: MockConfigEntry,
    snapshot: SnapshotAssertion,
) -> None:
    await snapshot_platform_entities(
        hass, cloud, entry, Platform.BINARY_SENSOR, snapshot
    )


async def test_stopped_wallbox_is_plugged_in_with_no_energy_flowing(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    assert state_of(hass, PLUGGED_IN) == "on"
    assert state_of(hass, ENERGY_FLOWING) == "off"


async def test_unplugged_wallbox_is_not_plugged_in_with_no_energy_flowing(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    cloud: aioresponses,
    freezer: FrozenDateTimeFactory,
) -> None:
    await poll_record(hass, cloud, freezer, UNPLUGGED)

    assert state_of(hass, PLUGGED_IN) == "off"
    assert state_of(hass, ENERGY_FLOWING) == "off"


@pytest.mark.usefixtures("loaded_entry")
@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("Charging", {PLUGGED_IN: "on", ENERGY_FLOWING: "on"}),
        ("SuspendedEv", {PLUGGED_IN: "on", ENERGY_FLOWING: "off"}),
        ("PluggedIn", {PLUGGED_IN: "on", ENERGY_FLOWING: "off"}),
        ("Error", {PLUGGED_IN: "unknown", ENERGY_FLOWING: "off"}),
        ("Offline", {PLUGGED_IN: "unknown", ENERGY_FLOWING: "off"}),
    ],
)
async def test_plugged_in_and_energy_flowing_follow_the_status(
    hass: HomeAssistant,
    cloud: aioresponses,
    freezer: FrozenDateTimeFactory,
    status: str,
    expected: dict[str, str],
) -> None:
    await poll_record(hass, cloud, freezer, {"status": status})

    assert {entity_id: state_of(hass, entity_id) for entity_id in expected} == (
        expected
    )
