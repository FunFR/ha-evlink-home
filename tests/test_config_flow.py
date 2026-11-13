"""Tests for the EVlink Home config, reauth and reconfigure flows."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.evlink_home.api import (
    CannotConnectError,
    InvalidCredentialsError,
    UnexpectedResponseError,
)
from custom_components.evlink_home.const import DOMAIN

ACCOUNT_ID = "account-1"
EMAIL = "user@example.com"
PASSWORD = "secret"


@pytest.fixture
def mock_client() -> Generator[MagicMock]:
    with patch(
        "custom_components.evlink_home.config_flow.WiserHomeClient", autospec=True
    ) as client_class:
        client_class.return_value.login.return_value = ACCOUNT_ID
        yield client_class


@pytest.fixture
def mock_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=EMAIL,
        unique_id=ACCOUNT_ID,
        data={CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture(autouse=True)
def mock_setup_entry() -> Generator[AsyncMock]:
    with patch(
        "custom_components.evlink_home.async_setup_entry", return_value=True
    ) as setup_entry:
        yield setup_entry


async def test_user_creates_entry_for_the_account(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == EMAIL
    assert result["data"] == {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
    assert result["result"].unique_id == ACCOUNT_ID
    assert mock_client.call_args.args[1:] == (EMAIL, PASSWORD)


@pytest.mark.parametrize(
    ("exception", "error"),
    [
        (InvalidCredentialsError, "invalid_auth"),
        (CannotConnectError, "cannot_connect"),
        (UnexpectedResponseError, "unknown"),
        (RuntimeError, "unknown"),
    ],
)
async def test_user_shows_error_then_recovers(
    hass: HomeAssistant, mock_client: MagicMock, exception: Exception, error: str
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    mock_client.return_value.login.side_effect = exception

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_client.return_value.login.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_aborts_when_account_already_configured(
    hass: HomeAssistant, mock_client: MagicMock, mock_entry: MockConfigEntry
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: "alias@example.com", CONF_PASSWORD: PASSWORD}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
