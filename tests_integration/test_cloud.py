"""Read-only checks against the real Wiser Home cloud service.

They catch a change on the cloud side that recorded answers cannot show. They
only log in and read the Wallboxes; they never send Start or Stop. Run them
with the credentials of an account that holds a Wallbox:

    uv run --env-file .env pytest tests_integration -p no:homeassistant --no-cov
"""

import os
from collections.abc import AsyncGenerator

import aiohttp
import pytest

from custom_components.evlink_home.api import WiserHomeClient

# Keys the client reads from each Wallbox record; a rename shows up here first.
RECORD_KEYS = {
    "deviceId",
    "name",
    "status",
    "productType",
    "modelIdentifier",
    "firmwareVersion",
    "serialNumber",
    "energyUsageKwh",
    "nextScheduledChargingDate",
    "nextScheduledChargingEndDate",
}


@pytest.fixture
async def client() -> AsyncGenerator[WiserHomeClient]:
    email = os.environ.get("WISER_HOME_USERNAME")
    password = os.environ.get("WISER_HOME_PASSWORD")
    if not email or not password:
        pytest.skip("WISER_HOME_USERNAME and WISER_HOME_PASSWORD are not set")
    async with aiohttp.ClientSession() as session:
        yield WiserHomeClient(session, email, password)


async def test_login_returns_the_account_id(client: WiserHomeClient) -> None:
    assert await client.login()


async def test_every_wallbox_record_still_reads(client: WiserHomeClient) -> None:
    wallboxes = await client.get_wallboxes()

    assert wallboxes, "the account holds no Wallbox"
    for wallbox in wallboxes:
        assert RECORD_KEYS <= wallbox.raw.keys()
        assert wallbox.status is not None, "the cloud sent a status the client lacks"
        assert wallbox.model
        assert wallbox.firmware
        assert wallbox.session_energy_kwh is None or wallbox.session_energy_kwh >= 0
