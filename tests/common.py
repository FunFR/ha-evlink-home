"""Cloud answers and constants shared by the EVlink Home tests."""

import json
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from aioresponses import aioresponses
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    load_fixture,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

LOGIN_URL = "https://api-nl.wiserair.com/Login"
DEVICES_URL = "https://se-api.wiserhome.com/app/clouddevices/v1.0"

ACCOUNT_ID = "REDACTED_id"
DEVICE_ID = "00000000-0000-4000-8000-000000000000"


def login_body() -> str:
    body = json.loads(load_fixture("login.json"))
    body["access_token"] = "access-1"
    body["refresh_token"] = "refresh-1"
    return json.dumps(body)


def error_fixture(name: str) -> tuple[int, str]:
    data = json.loads(load_fixture(name))
    return data["status"], data["body"]


UNPLUGGED: dict[str, Any] = {
    "status": "Unplugged",
    "chargingStartedDate": None,
    "chargingFinishedDate": None,
    "energyUsageKwh": None,
    "cost": None,
    "currency": None,
}
"""Changes the cloud makes to the Wallbox record once the car is unplugged."""


async def poll_record(
    hass: HomeAssistant,
    cloud: aioresponses,
    freezer: FrozenDateTimeFactory,
    changes: dict[str, Any],
) -> None:
    """Let the coordinator poll the fixture record with ``changes`` applied."""
    records = json.loads(load_fixture("clouddevices.json"))
    records[0].update(changes)
    cloud.get(DEVICES_URL, status=200, body=json.dumps(records))
    freezer.tick(timedelta(seconds=30))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def snapshot_platform_entities(
    hass: HomeAssistant,
    cloud: aioresponses,
    entry: MockConfigEntry,
    platform: Platform,
    snapshot: SnapshotAssertion,
) -> None:
    """Set up ``entry`` with ``platform`` alone and snapshot its entities."""
    cloud.post(LOGIN_URL, status=200, body=login_body())
    cloud.get(DEVICES_URL, status=200, body=load_fixture("clouddevices.json"))
    with patch("custom_components.evlink_home.PLATFORMS", [platform]):
        assert await hass.config_entries.async_setup(entry.entry_id)
    await snapshot_platform(hass, er.async_get(hass), snapshot, entry.entry_id)
