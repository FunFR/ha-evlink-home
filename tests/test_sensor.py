"""Tests for the EVlink Home sensors."""

from aioresponses import aioresponses
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy.assertion import SnapshotAssertion

from .common import UNPLUGGED, poll_record, snapshot_platform_entities


async def test_sensors_snapshot(
    hass: HomeAssistant,
    cloud: aioresponses,
    entry: MockConfigEntry,
    snapshot: SnapshotAssertion,
) -> None:
    await snapshot_platform_entities(hass, cloud, entry, Platform.SENSOR, snapshot)


async def test_status_reads_the_cloud_status_in_snake_case(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    state = hass.states.get("sensor.redacted_name_status")

    assert state is not None
    assert state.state == "schedule_paused"


async def test_status_reads_unplugged(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    cloud: aioresponses,
    freezer: FrozenDateTimeFactory,
) -> None:
    await poll_record(hass, cloud, freezer, UNPLUGGED)

    state = hass.states.get("sensor.redacted_name_status")
    assert state is not None
    assert state.state == "unplugged"


async def test_status_is_unknown_for_a_status_the_cloud_never_announced(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    cloud: aioresponses,
    freezer: FrozenDateTimeFactory,
) -> None:
    await poll_record(hass, cloud, freezer, {"status": "Overheated"})

    state = hass.states.get("sensor.redacted_name_status")
    assert state is not None
    assert state.state == "unknown"


async def test_next_schedule_reads_the_local_times_in_the_home_time_zone(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    assert hass.config.time_zone == "US/Pacific"
    start = hass.states.get("sensor.redacted_name_next_scheduled_start")
    end = hass.states.get("sensor.redacted_name_next_scheduled_end")

    assert start is not None
    assert start.state == "2026-11-14T06:00:00+00:00"
    assert start.attributes["device_class"] == "timestamp"
    assert end is not None
    assert end.state == "2026-11-14T14:00:00+00:00"


async def test_next_schedule_is_unknown_without_a_schedule(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    cloud: aioresponses,
    freezer: FrozenDateTimeFactory,
) -> None:
    await poll_record(
        hass,
        cloud,
        freezer,
        {"nextScheduledChargingDate": None, "nextScheduledChargingEndDate": None},
    )

    for entity_id in (
        "sensor.redacted_name_next_scheduled_start",
        "sensor.redacted_name_next_scheduled_end",
    ):
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == "unknown"


async def test_session_energy_reads_the_session_total_in_kwh(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    state = hass.states.get("sensor.redacted_name_session_energy")

    assert state is not None
    assert state.state == "33.9"
    assert state.attributes["unit_of_measurement"] == "kWh"
    assert state.attributes["device_class"] == "energy"
    assert state.attributes["state_class"] == "total_increasing"


async def test_session_energy_keeps_its_last_value_once_unplugged(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    cloud: aioresponses,
    freezer: FrozenDateTimeFactory,
) -> None:
    await poll_record(hass, cloud, freezer, UNPLUGGED)

    state = hass.states.get("sensor.redacted_name_session_energy")
    assert state is not None
    assert state.state == "33.9"


async def test_session_energy_follows_the_next_session(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    cloud: aioresponses,
    freezer: FrozenDateTimeFactory,
) -> None:
    await poll_record(hass, cloud, freezer, UNPLUGGED)
    await poll_record(
        hass, cloud, freezer, {"status": "Charging", "energyUsageKwh": 0.05}
    )

    state = hass.states.get("sensor.redacted_name_session_energy")
    assert state is not None
    assert state.state == "0.05"
