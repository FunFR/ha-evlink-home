"""Tests for the EVlink Home sensors."""

import json
from typing import Any

from aioresponses import aioresponses
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, State
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    load_fixture,
    mock_restore_cache_with_extra_data,
)
from syrupy.assertion import SnapshotAssertion

from .common import (
    DEVICES_URL,
    LOGIN_URL,
    UNPLUGGED,
    login_body,
    poll_record,
    snapshot_platform_entities,
)


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


SESSION_ENERGY = "sensor.redacted_name_session_energy"


def restore_session_energy(hass: HomeAssistant, kwh: float) -> None:
    """Store the Session energy Home Assistant saved before restarting."""
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(SESSION_ENERGY, str(kwh)),
                {"native_value": kwh, "native_unit_of_measurement": "kWh"},
            )
        ],
    )


async def set_up_with_record(
    hass: HomeAssistant,
    cloud: aioresponses,
    entry: MockConfigEntry,
    changes: dict[str, Any],
) -> None:
    records = json.loads(load_fixture("clouddevices.json"))
    records[0].update(changes)
    cloud.post(LOGIN_URL, status=200, body=login_body())
    cloud.get(DEVICES_URL, status=200, body=json.dumps(records))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_session_energy_restored_after_a_restart_while_unplugged(
    hass: HomeAssistant, cloud: aioresponses, entry: MockConfigEntry
) -> None:
    restore_session_energy(hass, 12.5)

    await set_up_with_record(hass, cloud, entry, UNPLUGGED)

    state = hass.states.get(SESSION_ENERGY)
    assert state is not None
    assert state.state == "12.5"
    assert state.attributes["state_class"] == "total_increasing"


async def test_session_energy_after_a_restart_reads_the_cloud_total_first(
    hass: HomeAssistant, cloud: aioresponses, entry: MockConfigEntry
) -> None:
    restore_session_energy(hass, 12.5)

    await set_up_with_record(hass, cloud, entry, {})

    state = hass.states.get(SESSION_ENERGY)
    assert state is not None
    assert state.state == "33.9"
