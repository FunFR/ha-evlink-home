"""Tests for the Charging switch, through Home Assistant's switch actions."""

import json
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import aiohttp
import pytest
from aioresponses import aioresponses
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    load_fixture,
)

from .common import DEVICE_ID, DEVICES_URL, LOGIN_URL, error_fixture, login_body

START_URL = "https://se-api.wiserhome.com/app/em/v1.0/data/start"
STOP_URL = "https://se-api.wiserhome.com/app/em/v1.0/data/pause"


def command_body() -> dict[str, Any]:
    return {
        "ChargerId": DEVICE_ID,
        "AuthorisedModeSupported": False,
        "ChargerData": None,
    }


def sent_commands(cloud: aioresponses) -> list[tuple[str, Any]]:
    return [
        (str(url), call.kwargs["json"])
        for (method, url), calls in cloud.requests.items()
        if method == "PATCH"
        for call in calls
    ]


def request_counts(cloud: aioresponses) -> dict[str, int]:
    return {
        f"{method} {url}": len(sent) for (method, url), sent in cloud.requests.items()
    }


def devices_body(status: str, energy: float = 33.9) -> str:
    records = json.loads(load_fixture("clouddevices.json"))
    for record in records:
        if record.get("productType") == "EvCharger":
            record["status"] = status
            record["energyUsageKwh"] = energy
    return json.dumps(records)


async def set_up(
    hass: HomeAssistant, cloud: aioresponses, entry: MockConfigEntry, status: str
) -> str:
    """Load the entry with the Wallbox in ``status``; return the switch id."""
    cloud.post(LOGIN_URL, status=200, body=login_body())
    cloud.get(DEVICES_URL, status=200, body=devices_body(status))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id(
        "switch", "evlink_home", f"{DEVICE_ID}_charging"
    )
    assert entity_id is not None
    return entity_id


@pytest.mark.parametrize(
    ("status", "state"),
    [
        ("Charging", STATE_ON),
        ("SuspendedEv", STATE_ON),
        ("SchedulePaused", STATE_OFF),
        ("PluggedIn", STATE_OFF),
        ("Unplugged", STATE_OFF),
        ("Error", STATE_OFF),
    ],
)
async def test_switch_is_on_while_the_wallbox_charges(
    hass: HomeAssistant,
    cloud: aioresponses,
    entry: MockConfigEntry,
    status: str,
    state: str,
) -> None:
    entity_id = await set_up(hass, cloud, entry, status)

    assert hass.states.get(entity_id).state == state


async def test_turning_on_starts_charging_then_polls(
    hass: HomeAssistant, cloud: aioresponses, entry: MockConfigEntry
) -> None:
    entity_id = await set_up(hass, cloud, entry, "SchedulePaused")
    cloud.patch(START_URL, status=204)
    cloud.get(DEVICES_URL, status=200, body=devices_body("SchedulePaused"))

    await hass.services.async_call(
        "switch", SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )

    assert sent_commands(cloud) == [(START_URL, command_body())]
    assert request_counts(cloud) == {
        f"POST {LOGIN_URL}": 1,
        f"GET {DEVICES_URL}": 2,
        f"PATCH {START_URL}": 1,
    }
    assert hass.states.get(entity_id).state == STATE_ON


async def test_turning_off_stops_charging_then_polls(
    hass: HomeAssistant, cloud: aioresponses, entry: MockConfigEntry
) -> None:
    entity_id = await set_up(hass, cloud, entry, "Charging")
    cloud.patch(STOP_URL, status=204)
    cloud.get(DEVICES_URL, status=200, body=devices_body("Charging"))

    await hass.services.async_call(
        "switch", SERVICE_TURN_OFF, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )

    assert sent_commands(cloud) == [(STOP_URL, command_body())]
    assert request_counts(cloud) == {
        f"POST {LOGIN_URL}": 1,
        f"GET {DEVICES_URL}": 2,
        f"PATCH {STOP_URL}": 1,
    }
    assert hass.states.get(entity_id).state == STATE_OFF


async def test_requested_state_holds_through_the_refresh_after_the_command(
    hass: HomeAssistant, cloud: aioresponses, entry: MockConfigEntry
) -> None:
    entity_id = await set_up(hass, cloud, entry, "Charging")
    cloud.patch(STOP_URL, status=204)
    cloud.get(DEVICES_URL, status=200, body=devices_body("Charging", energy=34.0))

    await hass.services.async_call(
        "switch", SERVICE_TURN_OFF, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )

    assert hass.states.get(entity_id).state == STATE_OFF


async def test_next_poll_shows_the_cloud_state_again(
    hass: HomeAssistant,
    cloud: aioresponses,
    entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    entity_id = await set_up(hass, cloud, entry, "SchedulePaused")
    cloud.patch(START_URL, status=204)
    cloud.get(DEVICES_URL, status=200, body=devices_body("SchedulePaused"), repeat=2)
    await hass.services.async_call(
        "switch", SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    assert hass.states.get(entity_id).state == STATE_ON

    freezer.tick(timedelta(seconds=30))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert request_counts(cloud) == {
        f"POST {LOGIN_URL}": 1,
        f"GET {DEVICES_URL}": 3,
        f"PATCH {START_URL}": 1,
    }
    assert hass.states.get(entity_id).state == STATE_OFF


async def test_turning_on_without_a_car_is_refused_without_a_command(
    hass: HomeAssistant, cloud: aioresponses, entry: MockConfigEntry
) -> None:
    entity_id = await set_up(hass, cloud, entry, "Unplugged")

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            "switch", SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity_id}, blocking=True
        )

    assert err.value.translation_key == "no_car_plugged_in"
    assert str(err.value) == "No car is plugged into the Wallbox"
    assert request_counts(cloud) == {f"POST {LOGIN_URL}": 1, f"GET {DEVICES_URL}": 1}
    assert hass.states.get(entity_id).state == STATE_OFF


def unreachable(cloud: aioresponses) -> None:
    cloud.patch(STOP_URL, exception=aiohttp.ClientConnectionError("down"))


def refused(cloud: aioresponses) -> None:
    cloud.patch(STOP_URL, status=400, body="")


def password_rejected(cloud: aioresponses) -> None:
    cloud.patch(STOP_URL, status=401, body="")
    for fixture in ("login_bad_refresh.json", "login_bad_credentials.json"):
        status, body = error_fixture(fixture)
        cloud.post(LOGIN_URL, status=status, body=body)


@pytest.mark.parametrize(
    ("failure", "error"),
    [
        (unreachable, ("cannot_connect", "The Wiser Home cloud is unreachable")),
        (
            refused,
            ("unexpected_response", "The Wiser Home cloud sent an unexpected answer"),
        ),
        (
            password_rejected,
            (
                "invalid_credentials",
                "The Wiser Home cloud rejected the email or password",
            ),
        ),
    ],
)
async def test_failed_command_raises_and_keeps_the_cloud_state(
    hass: HomeAssistant,
    cloud: aioresponses,
    entry: MockConfigEntry,
    failure: Callable[[aioresponses], None],
    error: tuple[str, str],
) -> None:
    entity_id = await set_up(hass, cloud, entry, "Charging")
    failure(cloud)

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            "switch", SERVICE_TURN_OFF, {ATTR_ENTITY_ID: entity_id}, blocking=True
        )

    assert not isinstance(err.value, ServiceValidationError)
    assert (err.value.translation_key, str(err.value)) == error
    assert request_counts(cloud)[f"GET {DEVICES_URL}"] == 1
    assert hass.states.get(entity_id).state == STATE_ON


async def test_switch_is_named_charging(
    hass: HomeAssistant, cloud: aioresponses, entry: MockConfigEntry
) -> None:
    entity_id = await set_up(hass, cloud, entry, "Charging")

    assert hass.states.get(entity_id).name == "REDACTED_name Charging"
