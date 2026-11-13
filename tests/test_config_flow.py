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


async def test_reauth_updates_the_password(
    hass: HomeAssistant, mock_client: MagicMock, mock_entry: MockConfigEntry
) -> None:
    result = await mock_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"][CONF_EMAIL] == EMAIL

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-secret"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_entry.data == {CONF_EMAIL: EMAIL, CONF_PASSWORD: "new-secret"}
    assert mock_client.call_args.args[1:] == (EMAIL, "new-secret")


@pytest.mark.parametrize(
    ("exception", "error"),
    [
        (InvalidCredentialsError, "invalid_auth"),
        (CannotConnectError, "cannot_connect"),
        (RuntimeError, "unknown"),
    ],
)
async def test_reauth_shows_error_then_recovers(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_entry: MockConfigEntry,
    exception: Exception,
    error: str,
) -> None:
    result = await mock_entry.start_reauth_flow(hass)
    mock_client.return_value.login.side_effect = exception

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-secret"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_client.return_value.login.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-secret"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"


async def test_reauth_aborts_on_another_account(
    hass: HomeAssistant, mock_client: MagicMock, mock_entry: MockConfigEntry
) -> None:
    result = await mock_entry.start_reauth_flow(hass)
    mock_client.return_value.login.return_value = "account-2"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-secret"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert mock_entry.data[CONF_PASSWORD] == PASSWORD


async def test_reconfigure_updates_the_credentials(
    hass: HomeAssistant, mock_client: MagicMock, mock_entry: MockConfigEntry
) -> None:
    result = await mock_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    suggested = {
        str(key): key.description["suggested_value"]
        for key in result["data_schema"].schema
        if key.description
    }
    assert suggested == {CONF_EMAIL: EMAIL}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "alias@example.com", CONF_PASSWORD: "new-secret"},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_entry.data == {
        CONF_EMAIL: "alias@example.com",
        CONF_PASSWORD: "new-secret",
    }
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


@pytest.mark.parametrize(
    ("exception", "error"),
    [
        (InvalidCredentialsError, "invalid_auth"),
        (CannotConnectError, "cannot_connect"),
        (RuntimeError, "unknown"),
    ],
)
async def test_reconfigure_shows_error_then_recovers(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_entry: MockConfigEntry,
    exception: Exception,
    error: str,
) -> None:
    result = await mock_entry.start_reconfigure_flow(hass)
    mock_client.return_value.login.side_effect = exception

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: "new-secret"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_client.return_value.login.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: "new-secret"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"


async def test_reconfigure_aborts_on_another_account(
    hass: HomeAssistant, mock_client: MagicMock, mock_entry: MockConfigEntry
) -> None:
    result = await mock_entry.start_reconfigure_flow(hass)
    mock_client.return_value.login.return_value = "account-2"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "other@example.com", CONF_PASSWORD: "other-secret"},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert mock_entry.data == {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
