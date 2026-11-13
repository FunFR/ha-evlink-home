"""Async client for the Wiser Home cloud API that controls the Wallbox.

The module never imports Home Assistant: it only needs an aiohttp session.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any

import aiohttp

LOGIN_URL = "https://api-nl.wiserair.com/Login"
DEVICES_URL = "https://se-api.wiserhome.com/app/clouddevices/v1.0"
START_URL = "https://se-api.wiserhome.com/app/em/v1.0/data/start"
STOP_URL = "https://se-api.wiserhome.com/app/em/v1.0/data/pause"

_APP_AUTHORIZATION = (
    "Basic "
    "SGs1dXRvMjBhMzVjeFdQOHB6aTRNNnZRVzN6NmlVdkI6aWRvRWhMVk4wbk55VldmZ29oekJSWW90RXR4UWptdkVqbGgwemNkSA=="
)
_VERSION: str = json.loads(
    (Path(__file__).parent / "manifest.json").read_text(encoding="utf-8")
)["version"]
USER_AGENT = f"ha-evlink-home/{_VERSION}"

_RENEW_MARGIN = 60
_TIMEOUT = aiohttp.ClientTimeout(total=30)

_LOGGER = logging.getLogger(__name__)


class WiserHomeError(Exception):
    """The Wiser Home cloud could not serve the request."""


class InvalidCredentialsError(WiserHomeError):
    """The cloud rejected the email or password."""


class CannotConnectError(WiserHomeError):
    """The cloud could not be reached, timed out or is failing."""


class UnexpectedResponseError(WiserHomeError):
    """The cloud answered something the client cannot use."""


class _GrantRejectedError(Exception):
    """The Login endpoint refused the password or the refresh token."""


@dataclass(frozen=True, slots=True)
class _Token:
    access: str
    refresh: str
    renew_at: float
    account_id: str


@dataclass(frozen=True, slots=True)
class Charger:
    """One Wallbox as the cloud reports it."""

    device_id: str
    name: str
    model: str | None
    firmware: str | None
    serial_number: str | None
    status: str
    session_energy_kwh: float | None
    next_scheduled_start: datetime | None
    next_scheduled_end: datetime | None
    raw: Mapping[str, Any]


class WiserHomeClient:
    """Wiser Home cloud account, with its tokens kept in memory.

    Every call logs in on demand and renews the token on its own: with the
    refresh token first, then with the password. Once the cloud rejects the
    password, implicit logins stop and every call raises
    ``InvalidCredentialsError`` so the account is not locked. Calls raise
    ``CannotConnectError`` when the cloud is unreachable, times out or fails,
    and ``UnexpectedResponseError`` on any other unusable answer.
    """

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str):
        self._session = session
        self._email = email
        self._password = password
        self._token: _Token | None = None
        self._password_rejected = False
        self._auth_lock = asyncio.Lock()

    async def login(self) -> str:
        """Log in with the password and return the account id."""
        async with self._auth_lock:
            self._token = await self._password_grant()
            return self._token.account_id

    async def _bearer(self, refused: str | None = None) -> str:
        """Return a usable access token, never the ``refused`` one."""
        async with self._auth_lock:
            if self._password_rejected:
                raise InvalidCredentialsError
            if self._token is None:
                self._token = await self._password_grant()
            elif (
                time.monotonic() >= self._token.renew_at
                or self._token.access == refused
            ):
                self._token = await self._renew(self._token.refresh)
            return self._token.access

    async def _renew(self, refresh_token: str) -> _Token:
        try:
            return await self._grant(
                {"grant_type": "refresh_token", "refresh_token": refresh_token}
            )
        except _GrantRejectedError:
            _LOGGER.debug("Refresh token rejected, logging in with the password")
        return await self._password_grant()

    async def _password_grant(self) -> _Token:
        form = {
            "grant_type": "password",
            "username": self._email,
            "password": self._password,
            "remember": "true",
        }
        try:
            return await self._grant(form)
        except _GrantRejectedError as err:
            self._password_rejected = True
            raise InvalidCredentialsError from err

    async def _grant(self, form: Mapping[str, str]) -> _Token:
        status, text = await self._send(
            "POST", LOGIN_URL, _APP_AUTHORIZATION, form=form
        )
        if status == HTTPStatus.BAD_REQUEST and _error_code(text) == "invalid_grant":
            raise _GrantRejectedError
        if status != HTTPStatus.OK:
            raise UnexpectedResponseError(f"Login answered HTTP {status}")
        try:
            body = json.loads(text)
            return _Token(
                access=str(body["access_token"]),
                refresh=str(body["refresh_token"]),
                renew_at=time.monotonic() + float(body["expires_in"]) - _RENEW_MARGIN,
                account_id=str(body["id"]),
            )
        except (ValueError, KeyError, TypeError) as err:
            raise UnexpectedResponseError("Login answer has no usable token") from err

    async def get_chargers(self) -> list[Charger]:
        """Return every Wallbox of the account."""
        text = await self._api_request("GET", DEVICES_URL)
        try:
            records = json.loads(text)
            if not isinstance(records, list):
                raise TypeError("not a list")
            return [
                _charger(record)
                for record in records
                if record.get("productType") == "EvCharger"
            ]
        except (ValueError, KeyError, TypeError, AttributeError) as err:
            raise UnexpectedResponseError("Unreadable cloud devices answer") from err

    async def start(self, device_id: str) -> None:
        """Make the Wallbox charge the plugged-in car."""
        await self._command(START_URL, device_id)

    async def stop(self, device_id: str) -> None:
        """Interrupt charging while the Charge session goes on."""
        await self._command(STOP_URL, device_id)

    async def _command(self, url: str, device_id: str) -> None:
        await self._api_request(
            "PATCH",
            url,
            {
                "ChargerId": device_id,
                "AuthorisedModeSupported": False,
                "ChargerData": None,
            },
        )

    async def _api_request(
        self, method: str, url: str, payload: Mapping[str, Any] | None = None
    ) -> str:
        """Send an authenticated call, renewing a token the cloud refuses once."""
        token = await self._bearer()
        status, text = await self._send(method, url, f"Bearer {token}", payload=payload)
        if status == HTTPStatus.UNAUTHORIZED:
            token = await self._bearer(refused=token)
            status, text = await self._send(
                method, url, f"Bearer {token}", payload=payload
            )
        if not HTTPStatus.OK <= status < HTTPStatus.MULTIPLE_CHOICES:
            raise UnexpectedResponseError(f"{method} {url} answered HTTP {status}")
        return text

    async def _send(
        self,
        method: str,
        url: str,
        authorization: str,
        *,
        form: Mapping[str, str] | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> tuple[int, str]:
        headers = {
            "Authorization": authorization,
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                data=form,
                json=payload,
                timeout=_TIMEOUT,
            ) as resp:
                status, text = resp.status, await resp.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnectError(f"{method} {url} failed: {err!r}") from err
        if status >= HTTPStatus.INTERNAL_SERVER_ERROR:
            raise CannotConnectError(f"{method} {url} answered HTTP {status}")
        return status, text


def _error_code(text: str) -> object:
    try:
        body = json.loads(text)
    except ValueError:
        return None
    return body.get("error") if isinstance(body, dict) else None


def _charger(record: Mapping[str, Any]) -> Charger:
    energy = record.get("energyUsageKwh")
    return Charger(
        device_id=str(record["deviceId"]),
        name=str(record["name"]),
        model=record.get("modelIdentifier"),
        firmware=record.get("firmwareVersion"),
        serial_number=record.get("serialNumber"),
        status=str(record["status"]),
        session_energy_kwh=None if energy is None else float(energy),
        next_scheduled_start=_local_time(record.get("nextScheduledChargingDate")),
        next_scheduled_end=_local_time(record.get("nextScheduledChargingEndDate")),
        raw=record,
    )


def _local_time(value: str | None) -> datetime | None:
    """Parse a cloud date, a local wall-clock time without offset."""
    return None if value is None else datetime.fromisoformat(value)
