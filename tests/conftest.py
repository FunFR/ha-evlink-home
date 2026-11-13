"""Shared fixtures for the EVlink Home tests."""

import inspect
from collections.abc import Generator
from typing import Any
from unittest.mock import Mock

import aiohttp
import pytest

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


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    yield
