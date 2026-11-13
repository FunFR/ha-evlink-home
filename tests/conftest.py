"""Shared fixtures for the EVlink Home tests."""

import inspect
from collections.abc import Generator
from typing import Any
from unittest.mock import Mock

import aiohttp
import pytest
from aioresponses import aioresponses
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, load_fixture
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from syrupy.assertion import SnapshotAssertion

from custom_components.evlink_home.const import DOMAIN

from .common import ACCOUNT_ID, DEVICES_URL, LOGIN_URL, login_body

pytest_plugins = "pytest_homeassistant_custom_component"

# aiohttp 3.14 made ``stream_writer`` a required keyword-only argument of
# ``ClientResponse.__init__``, and aioresponses 0.7.9 builds its mocked responses
# without it. aiohttp only reads ``stream_writer.output_size``, so a mock exposing
# that is enough. Tracked upstream in
# https://github.com/pnuckowski/aioresponses/issues/289; the signature guard
# turns this into a no-op once a release supplies the argument.
_response_init = aiohttp.ClientResponse.__init__
if "stream_writer" in inspect.signature(_response_init).parameters:

    def _patched_response_init(
        self: aiohttp.ClientResponse, *args: Any, **kwargs: Any
    ) -> None:
        kwargs.setdefault("stream_writer", Mock(output_size=0))
        _response_init(self, *args, **kwargs)

    aiohttp.ClientResponse.__init__ = _patched_response_init  # type: ignore[method-assign]


# syrupy and the Home Assistant plugin both define ``snapshot``; which one wins
# depends on plugin load order, which differs between file systems. Defining it
# here pins the Home Assistant extension, as Home Assistant core does.
@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Return the snapshot assertion with the Home Assistant extension."""
    return snapshot.use_extension(HomeAssistantSnapshotExtension)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    yield


@pytest.fixture
def cloud() -> Generator[aioresponses]:
    """Mocked cloud that lets the test client reach the local Home Assistant."""
    with aioresponses(passthrough=["http://127.0.0.1"]) as mock:
        yield mock


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=ACCOUNT_ID,
        data={CONF_EMAIL: "user@example.com", CONF_PASSWORD: "secret"},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def loaded_entry(
    hass: HomeAssistant,
    cloud: aioresponses,
    entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> MockConfigEntry:
    """Entry set up once time is frozen, so ticking it never expires the token."""
    cloud.post(LOGIN_URL, status=200, body=login_body())
    cloud.get(DEVICES_URL, status=200, body=load_fixture("clouddevices.json"))
    assert await hass.config_entries.async_setup(entry.entry_id)
    return entry
