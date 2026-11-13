"""Tests for the EVlink Home config entry lifecycle, through Home Assistant."""

import json
from datetime import timedelta
from typing import Any

import aiohttp
import pytest
from aioresponses import aioresponses
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    load_fixture,
)
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.evlink_home.api import WallboxStatus
from custom_components.evlink_home.const import DOMAIN

from .common import DEVICE_ID, DEVICES_URL, LOGIN_URL, error_fixture, login_body


async def poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(timedelta(seconds=30))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def request_counts(cloud: aioresponses) -> dict[str, int]:
    return {
        f"{method} {url}": len(sent) for (method, url), sent in cloud.requests.items()
    }


def reauth_flows(hass: HomeAssistant, entry: MockConfigEntry) -> list[str]:
    return [
        flow["step_id"] for flow in entry.async_get_active_flows(hass, {SOURCE_REAUTH})
    ]


def keep_polling(entry: MockConfigEntry) -> None:
    """Subscribe like an entity would, since the coordinator only polls for one."""
    entry.async_on_unload(entry.runtime_data.async_add_listener(lambda: None))


async def test_entry_loads_the_wallboxes_and_unloads(
    hass: HomeAssistant, cloud: aioresponses, entry: MockConfigEntry
) -> None:
    cloud.post(LOGIN_URL, status=200, body=login_body())
    cloud.get(DEVICES_URL, status=200, body=load_fixture("clouddevices.json"))

    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.LOADED
    wallbox = entry.runtime_data.data[DEVICE_ID]
    assert wallbox.status is WallboxStatus.SCHEDULE_PAUSED
    assert wallbox.model == "EVH4A07N400F"

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_rejected_password_at_setup_asks_to_reauthenticate(
    hass: HomeAssistant, cloud: aioresponses, entry: MockConfigEntry
) -> None:
    status, body = error_fixture("login_bad_credentials.json")
    cloud.post(LOGIN_URL, status=status, body=body)

    await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert entry.reason == "The Wiser Home cloud rejected the email or password"
    assert reauth_flows(hass, entry) == ["reauth_confirm"]
    assert request_counts(cloud) == {f"POST {LOGIN_URL}": 1}


async def test_unreachable_cloud_at_setup_retries_later(
    hass: HomeAssistant, cloud: aioresponses, entry: MockConfigEntry
) -> None:
    cloud.post(LOGIN_URL, exception=aiohttp.ClientConnectionError("down"))

    await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert entry.reason == "The Wiser Home cloud is unreachable"


async def test_unexpected_cloud_answer_at_setup_retries_later(
    hass: HomeAssistant, cloud: aioresponses, entry: MockConfigEntry
) -> None:
    cloud.post(LOGIN_URL, status=200, body=login_body())
    cloud.get(DEVICES_URL, status=200, body="{}")

    await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert entry.reason == "The Wiser Home cloud sent an unexpected answer"


async def test_cloud_outage_is_logged_once_and_its_recovery_once(
    hass: HomeAssistant,
    cloud: aioresponses,
    loaded_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    keep_polling(loaded_entry)
    coordinator = loaded_entry.runtime_data

    cloud.get(DEVICES_URL, exception=aiohttp.ClientConnectionError("down"))
    cloud.get(DEVICES_URL, exception=aiohttp.ClientConnectionError("down"))
    await poll(hass, freezer)
    await poll(hass, freezer)
    assert not coordinator.last_update_success

    cloud.get(DEVICES_URL, status=200, body=load_fixture("clouddevices.json"))
    await poll(hass, freezer)
    assert coordinator.last_update_success

    messages = [record.getMessage() for record in caplog.records]
    assert (
        messages.count(
            "Error fetching evlink_home data: The Wiser Home cloud is unreachable"
        )
        == 1
    )
    assert messages.count("Fetching evlink_home data recovered") == 1
    assert request_counts(cloud) == {f"POST {LOGIN_URL}": 1, f"GET {DEVICES_URL}": 4}


async def test_password_rejected_while_polling_asks_to_reauthenticate(
    hass: HomeAssistant,
    cloud: aioresponses,
    loaded_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    keep_polling(loaded_entry)

    cloud.get(DEVICES_URL, status=401)
    status, body = error_fixture("login_bad_refresh.json")
    cloud.post(LOGIN_URL, status=status, body=body)
    status, body = error_fixture("login_bad_credentials.json")
    cloud.post(LOGIN_URL, status=status, body=body)
    await poll(hass, freezer)
    await poll(hass, freezer)

    assert not loaded_entry.runtime_data.last_update_success
    assert reauth_flows(hass, loaded_entry) == ["reauth_confirm"]
    assert (
        "Authentication failed while fetching evlink_home data: "
        "The Wiser Home cloud rejected the email or password"
    ) in caplog.text
    assert request_counts(cloud) == {f"POST {LOGIN_URL}": 3, f"GET {DEVICES_URL}": 2}


SECOND_DEVICE_ID = "11111111-1111-4111-8111-111111111111"


def second_wallbox_records() -> str:
    records = json.loads(load_fixture("clouddevices.json"))
    second = {**records[0], "deviceId": SECOND_DEVICE_ID, "name": "Garage"}
    return json.dumps([*records, second])


async def test_wallbox_added_to_the_account_gets_its_device_and_entities(
    hass: HomeAssistant,
    cloud: aioresponses,
    loaded_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    cloud.get(DEVICES_URL, status=200, body=second_wallbox_records())
    await poll(hass, freezer)

    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, SECOND_DEVICE_ID), loaded_entry.entry_id
    )
    assert device is not None
    assert device.name == "Garage"
    entities = er.async_entries_for_device(er.async_get(hass), device.id)
    assert sorted(entity.entity_id for entity in entities) == [
        "binary_sensor.garage_energy_flowing",
        "binary_sensor.garage_plugged_in",
        "sensor.garage_next_scheduled_end",
        "sensor.garage_next_scheduled_start",
        "sensor.garage_session_energy",
        "sensor.garage_status",
        "switch.garage_charging",
    ]


async def remove_wallbox_device(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, entry: MockConfigEntry
) -> dict[str, Any]:
    """Ask, as the device page's delete button does, to remove the Wallbox."""
    assert await async_setup_component(hass, "config", {})
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, DEVICE_ID), entry.entry_id
    )
    assert device is not None
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {"type": "config/device_registry/remove", "device_id": device.id}
    )
    response: dict[str, Any] = await client.receive_json()
    return response


def wallbox_device_exists(hass: HomeAssistant, entry: MockConfigEntry) -> bool:
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, DEVICE_ID), entry.entry_id
    )
    return device is not None


async def test_wallbox_still_on_the_account_cannot_be_removed(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    response = await remove_wallbox_device(hass, hass_ws_client, loaded_entry)

    assert not response["success"]
    assert wallbox_device_exists(hass, loaded_entry)


async def test_wallbox_gone_from_the_account_can_be_removed(
    hass: HomeAssistant,
    cloud: aioresponses,
    loaded_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    hass_ws_client: WebSocketGenerator,
) -> None:
    cloud.get(DEVICES_URL, status=200, body="[]")
    await poll(hass, freezer)

    response = await remove_wallbox_device(hass, hass_ws_client, loaded_entry)

    assert response["success"]
    assert not wallbox_device_exists(hass, loaded_entry)
