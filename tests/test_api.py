"""Tests for the Wiser Home cloud client, at its HTTP boundary."""

import asyncio
import json
from collections.abc import AsyncGenerator, Generator
from datetime import datetime
from typing import Any

import aiohttp
import pytest
from aioresponses import CallbackResult, aioresponses
from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import load_fixture
from yarl import URL

from custom_components.evlink_home.api import (
    CannotConnectError,
    InvalidCredentialsError,
    UnexpectedResponseError,
    Wallbox,
    WiserHomeClient,
)

LOGIN_URL = "https://api-nl.wiserair.com/Login"
DEVICES_URL = "https://se-api.wiserhome.com/app/clouddevices/v1.0"
START_URL = "https://se-api.wiserhome.com/app/em/v1.0/data/start"
STOP_URL = "https://se-api.wiserhome.com/app/em/v1.0/data/pause"

EMAIL = "user@example.com"
PASSWORD = "secret"


def login_body(access: str = "access-1", refresh: str = "refresh-1") -> str:
    body: dict[str, Any] = json.loads(load_fixture("login.json"))
    body["access_token"] = access
    body["refresh_token"] = refresh
    return json.dumps(body)


def error_fixture(name: str) -> tuple[int, str]:
    data = json.loads(load_fixture(name))
    return data["status"], data["body"]


def calls(mock: aioresponses, method: str, url: str) -> list[Any]:
    return list(mock.requests.get((method, URL(url)), []))


@pytest.fixture
def cloud() -> Generator[aioresponses]:
    with aioresponses() as mock:
        yield mock


@pytest.fixture
async def client() -> AsyncGenerator[WiserHomeClient]:
    async with aiohttp.ClientSession() as session:
        yield WiserHomeClient(session, EMAIL, PASSWORD)


async def test_login_returns_the_account_id(
    cloud: aioresponses, client: WiserHomeClient
) -> None:
    cloud.post(LOGIN_URL, status=200, body=login_body())

    assert await client.login() == "REDACTED_id"

    [call] = calls(cloud, "POST", LOGIN_URL)
    assert call.kwargs["data"] == {
        "grant_type": "password",
        "username": EMAIL,
        "password": PASSWORD,
        "remember": "true",
    }
    headers = call.kwargs["headers"]
    assert headers["Authorization"].startswith("Basic ")
    assert headers["Accept"] == "application/json"
    assert headers["User-Agent"] == "ha-evlink-home/0.0.0"


async def test_get_wallboxes_logs_in_on_demand_and_returns_the_wallbox(
    cloud: aioresponses, client: WiserHomeClient
) -> None:
    cloud.post(LOGIN_URL, status=200, body=login_body(access="access-1"))
    cloud.get(DEVICES_URL, status=200, body=load_fixture("clouddevices.json"))

    [wallbox] = await client.get_wallboxes()

    assert wallbox == Wallbox(
        device_id="00000000-0000-4000-8000-000000000000",
        name="REDACTED_name",
        model="EVH4A07N400F",
        firmware="2.0.7.0.0_f135",
        serial_number="REDACTED_serialNumber",
        status="SchedulePaused",
        session_energy_kwh=33.9,
        next_scheduled_start=datetime(2026, 11, 13, 22, 0),
        next_scheduled_end=datetime(2026, 11, 14, 6, 0),
        raw=json.loads(load_fixture("clouddevices.json"))[0],
    )
    [call] = calls(cloud, "GET", DEVICES_URL)
    assert call.kwargs["headers"]["Authorization"] == "Bearer access-1"
    assert call.kwargs["headers"]["User-Agent"] == "ha-evlink-home/0.0.0"


@pytest.mark.parametrize(("command", "url"), [("start", START_URL), ("stop", STOP_URL)])
async def test_command_patches_the_wallbox(
    cloud: aioresponses, client: WiserHomeClient, command: str, url: str
) -> None:
    cloud.post(LOGIN_URL, status=200, body=login_body(access="access-1"))
    cloud.patch(url, status=204)

    await getattr(client, command)("device-1")

    [call] = calls(cloud, "PATCH", url)
    assert call.kwargs["json"] == {
        "ChargerId": "device-1",
        "AuthorisedModeSupported": False,
        "ChargerData": None,
    }
    assert call.kwargs["headers"]["Authorization"] == "Bearer access-1"


async def test_rejected_password_raises_and_is_never_sent_again(
    cloud: aioresponses, client: WiserHomeClient
) -> None:
    status, body = error_fixture("login_bad_credentials.json")
    cloud.post(LOGIN_URL, status=status, body=body, repeat=True)

    with pytest.raises(InvalidCredentialsError):
        await client.login()
    with pytest.raises(InvalidCredentialsError):
        await client.get_wallboxes()

    assert len(calls(cloud, "POST", LOGIN_URL)) == 1


async def test_token_is_reused_then_refreshed_before_expiry(
    cloud: aioresponses, client: WiserHomeClient, freezer: FrozenDateTimeFactory
) -> None:
    cloud.post(LOGIN_URL, status=200, body=login_body("access-1", "refresh-1"))
    cloud.post(LOGIN_URL, status=200, body=login_body("access-2", "refresh-2"))
    cloud.post(LOGIN_URL, status=200, body=login_body("access-3", "refresh-3"))
    cloud.get(DEVICES_URL, status=200, body="[]", repeat=True)

    await client.get_wallboxes()
    freezer.tick(3000)
    await client.get_wallboxes()
    freezer.tick(560)
    await client.get_wallboxes()
    freezer.tick(3560)
    await client.get_wallboxes()

    logins = calls(cloud, "POST", LOGIN_URL)
    assert [c.kwargs["data"] for c in logins[1:]] == [
        {"grant_type": "refresh_token", "refresh_token": "refresh-1"},
        {"grant_type": "refresh_token", "refresh_token": "refresh-2"},
    ]
    assert logins[1].kwargs["headers"]["Authorization"].startswith("Basic ")
    bearers = [
        c.kwargs["headers"]["Authorization"] for c in calls(cloud, "GET", DEVICES_URL)
    ]
    assert bearers == [
        "Bearer access-1",
        "Bearer access-1",
        "Bearer access-2",
        "Bearer access-3",
    ]


async def test_rejected_refresh_token_falls_back_to_the_password(
    cloud: aioresponses, client: WiserHomeClient, freezer: FrozenDateTimeFactory
) -> None:
    status, body = error_fixture("login_bad_refresh.json")
    cloud.post(LOGIN_URL, status=200, body=login_body("access-1", "refresh-1"))
    cloud.post(LOGIN_URL, status=status, body=body)
    cloud.post(LOGIN_URL, status=200, body=login_body("access-2", "refresh-2"))
    cloud.get(DEVICES_URL, status=200, body="[]", repeat=True)

    await client.get_wallboxes()
    freezer.tick(3600)
    await client.get_wallboxes()

    grants = [c.kwargs["data"]["grant_type"] for c in calls(cloud, "POST", LOGIN_URL)]
    assert grants == ["password", "refresh_token", "password"]
    [_, call] = calls(cloud, "GET", DEVICES_URL)
    assert call.kwargs["headers"]["Authorization"] == "Bearer access-2"


async def test_token_refused_by_the_api_is_renewed_and_the_call_retried_once(
    cloud: aioresponses, client: WiserHomeClient
) -> None:
    status, body = error_fixture("clouddevices_bad_token.json")
    cloud.post(LOGIN_URL, status=200, body=login_body("access-1", "refresh-1"))
    cloud.post(LOGIN_URL, status=200, body=login_body("access-2", "refresh-2"))
    cloud.get(DEVICES_URL, status=status, body=body)
    cloud.get(DEVICES_URL, status=200, body=load_fixture("clouddevices.json"))

    assert len(await client.get_wallboxes()) == 1

    grants = [c.kwargs["data"]["grant_type"] for c in calls(cloud, "POST", LOGIN_URL)]
    assert grants == ["password", "refresh_token"]
    bearers = [
        c.kwargs["headers"]["Authorization"] for c in calls(cloud, "GET", DEVICES_URL)
    ]
    assert bearers == ["Bearer access-1", "Bearer access-2"]


async def test_concurrent_calls_share_one_login(
    cloud: aioresponses, client: WiserHomeClient
) -> None:
    async def slow_login(url: URL, **kwargs: Any) -> CallbackResult:
        await asyncio.sleep(0.01)
        return CallbackResult(status=200, body=login_body())

    cloud.post(LOGIN_URL, callback=slow_login, repeat=True)
    cloud.get(DEVICES_URL, status=200, body="[]")
    cloud.patch(START_URL, status=204)

    await asyncio.gather(client.get_wallboxes(), client.start("device-1"))

    assert len(calls(cloud, "POST", LOGIN_URL)) == 1


@pytest.mark.parametrize(
    "login",
    [
        {"status": 200, "body": "<html>maintenance</html>"},
        {"status": 200, "body": '{"token_type": "bearer"}'},
        {"status": 400, "body": '{"error": "unsupported_grant_type"}'},
        {"status": 400, "body": "Bad Request"},
        {"status": 403, "body": ""},
    ],
    ids=["not-json", "no-token", "other-error", "plain-error", "forbidden"],
)
async def test_unexpected_login_answer_raises_without_blaming_the_password(
    cloud: aioresponses, client: WiserHomeClient, login: dict[str, Any]
) -> None:
    cloud.post(LOGIN_URL, **login)
    cloud.post(LOGIN_URL, status=200, body=login_body())

    with pytest.raises(UnexpectedResponseError):
        await client.login()
    assert await client.login() == "REDACTED_id"


@pytest.mark.parametrize(
    "devices",
    [
        {"status": 200, "body": "<html>maintenance</html>"},
        {"status": 200, "body": '{"items": []}'},
        {"status": 200, "body": '[{"productType": "EvCharger"}]'},
        {
            "status": 200,
            "body": '[{"productType": "EvCharger", "deviceId": "d", '
            '"name": "n", "status": "Charging", "energyUsageKwh": "lots"}]',
        },
        {"status": 404, "body": ""},
    ],
    ids=["not-json", "not-a-list", "missing-keys", "bad-energy", "not-found"],
)
async def test_unexpected_devices_answer_raises(
    cloud: aioresponses, client: WiserHomeClient, devices: dict[str, Any]
) -> None:
    cloud.post(LOGIN_URL, status=200, body=login_body())
    cloud.get(DEVICES_URL, **devices)

    with pytest.raises(UnexpectedResponseError):
        await client.get_wallboxes()


async def test_token_refused_twice_raises(
    cloud: aioresponses, client: WiserHomeClient
) -> None:
    cloud.post(LOGIN_URL, status=200, body=login_body("access-1", "refresh-1"))
    cloud.post(LOGIN_URL, status=200, body=login_body("access-2", "refresh-2"))
    cloud.get(DEVICES_URL, status=401, repeat=True)

    with pytest.raises(UnexpectedResponseError):
        await client.get_wallboxes()

    bearers = [
        c.kwargs["headers"]["Authorization"] for c in calls(cloud, "GET", DEVICES_URL)
    ]
    assert bearers == ["Bearer access-1", "Bearer access-2"]


async def test_refused_command_raises(
    cloud: aioresponses, client: WiserHomeClient
) -> None:
    cloud.post(LOGIN_URL, status=200, body=login_body())
    cloud.patch(START_URL, status=400, body='{"message": "bad wallbox"}')

    with pytest.raises(UnexpectedResponseError):
        await client.start("device-1")


async def test_get_wallboxes_ignores_other_devices(
    cloud: aioresponses, client: WiserHomeClient
) -> None:
    records = json.loads(load_fixture("clouddevices.json"))
    records.insert(0, {"productType": "Hub", "deviceId": "hub-1"})
    cloud.post(LOGIN_URL, status=200, body=login_body())
    cloud.get(DEVICES_URL, status=200, body=json.dumps(records))

    wallboxes = await client.get_wallboxes()

    assert [c.device_id for c in wallboxes] == ["00000000-0000-4000-8000-000000000000"]


async def test_unplugged_wallbox_has_no_session_values(
    cloud: aioresponses, client: WiserHomeClient
) -> None:
    [record] = json.loads(load_fixture("clouddevices.json"))
    record.update(
        status="Unplugged",
        energyUsageKwh=None,
        nextScheduledChargingDate=None,
        nextScheduledChargingEndDate=None,
    )
    cloud.post(LOGIN_URL, status=200, body=login_body())
    cloud.get(DEVICES_URL, status=200, body=json.dumps([record]))

    [wallbox] = await client.get_wallboxes()

    assert wallbox.status == "Unplugged"
    assert wallbox.session_energy_kwh is None
    assert wallbox.next_scheduled_start is None
    assert wallbox.next_scheduled_end is None


@pytest.mark.parametrize(
    "failure",
    [
        {"exception": aiohttp.ClientConnectionError("unreachable")},
        {"exception": TimeoutError()},
        {"status": 503, "body": "Service Unavailable"},
    ],
    ids=["connection", "timeout", "server-error"],
)
@pytest.mark.parametrize("url", [LOGIN_URL, DEVICES_URL], ids=["login", "devices"])
async def test_unreachable_cloud_raises_cannot_connect(
    cloud: aioresponses, client: WiserHomeClient, url: str, failure: dict[str, Any]
) -> None:
    if url != LOGIN_URL:
        cloud.post(LOGIN_URL, status=200, body=login_body())
    cloud.add(url, "POST" if url == LOGIN_URL else "GET", **failure)

    with pytest.raises(CannotConnectError):
        await client.get_wallboxes()


async def test_requests_carry_a_30_second_timeout(
    cloud: aioresponses, client: WiserHomeClient
) -> None:
    cloud.post(LOGIN_URL, status=200, body=login_body())
    cloud.get(DEVICES_URL, status=200, body="[]")

    await client.get_wallboxes()

    for method, url in (("POST", LOGIN_URL), ("GET", DEVICES_URL)):
        [call] = calls(cloud, method, url)
        assert call.kwargs["timeout"] == aiohttp.ClientTimeout(total=30)
