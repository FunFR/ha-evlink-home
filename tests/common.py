"""Cloud answers and constants shared by the EVlink Home tests."""

import json

from pytest_homeassistant_custom_component.common import load_fixture

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
