"""Tests for the EVlink Home diagnostics, through Home Assistant."""

import json
from collections.abc import Iterator
from typing import Any

from aioresponses import aioresponses
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, load_fixture
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator
from syrupy.assertion import SnapshotAssertion
from syrupy.filters import props

from .common import ACCOUNT_ID, DEVICE_ID, DEVICES_URL, LOGIN_URL, login_body

SECRETS = {
    "user@example.com",
    "secret",
    "access-1",
    "refresh-1",
    ACCOUNT_ID,
    DEVICE_ID,
    123456,
    "REDACTED_EquipmentId",
    "REDACTED_name",
    "REDACTED_serialNumber",
    "REDACTED_productIdentifier",
    "Home network",
    "wifi-secret",
}


def leaves(data: Any) -> Iterator[Any]:
    if isinstance(data, dict):
        for value in data.values():
            yield from leaves(value)
    elif isinstance(data, list):
        for value in data:
            yield from leaves(value)
    else:
        yield data


async def test_diagnostics_hide_the_account_and_the_wallbox_identity(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    cloud: aioresponses,
    entry: MockConfigEntry,
    snapshot: SnapshotAssertion,
) -> None:
    hass.config_entries.async_update_entry(entry, title="user@example.com")
    records = json.loads(load_fixture("clouddevices.json"))
    records[0] |= {"wiFiSsid": "Home network", "wiFiPassword": "wifi-secret"}
    cloud.post(LOGIN_URL, status=200, body=login_body())
    cloud.get(DEVICES_URL, status=200, body=json.dumps(records))
    assert await hass.config_entries.async_setup(entry.entry_id)

    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, entry)

    assert not SECRETS & set(leaves(diagnostics))
    assert diagnostics == snapshot(
        exclude=props("entry_id", "created_at", "modified_at")
    )
