"""Config flow for the EVlink Home integration."""

import logging
from collections.abc import Mapping
from typing import Any

import probatio
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import CannotConnectError, InvalidCredentialsError, WiserHomeClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_EMAIL_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="email")
)
_PASSWORD_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
)
_CREDENTIALS_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_EMAIL): _EMAIL_SELECTOR,
        probatio.Required(CONF_PASSWORD): _PASSWORD_SELECTOR,
    }
)


class EvlinkHomeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EVlink Home."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the Wiser Home credentials and test them."""
        errors: dict[str, str] = {}
        if user_input is not None:
            account_id = await self._async_login(user_input, errors)
            if account_id is not None:
                await self.async_set_unique_id(account_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_EMAIL], data=user_input
                )
        return self.async_show_form(
            step_id="user", data_schema=_CREDENTIALS_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication after the cloud rejected the password."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the new password of the configured account."""
        entry = self._get_reauth_entry()
        email = entry.data[CONF_EMAIL]
        errors: dict[str, str] = {}
        if user_input is not None:
            credentials = {CONF_EMAIL: email, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            account_id = await self._async_login(credentials, errors)
            if account_id is not None:
                await self.async_set_unique_id(account_id)
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    entry, data_updates=credentials
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=probatio.Schema(
                {probatio.Required(CONF_PASSWORD): _PASSWORD_SELECTOR}
            ),
            description_placeholders={CONF_EMAIL: email},
            errors=errors,
        )

    async def _async_login(
        self, credentials: Mapping[str, Any], errors: dict[str, str]
    ) -> str | None:
        """Return the account id, or fill ``errors`` when the login fails."""
        client = WiserHomeClient(
            async_get_clientsession(self.hass),
            credentials[CONF_EMAIL],
            credentials[CONF_PASSWORD],
        )
        try:
            return await client.login()
        except InvalidCredentialsError:
            errors["base"] = "invalid_auth"
        except CannotConnectError:
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error while logging in to Wiser Home")
            errors["base"] = "unknown"
        return None
