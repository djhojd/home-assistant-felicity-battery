"""Config flow test against a real Home Assistant core (`uv sync --group ha`)."""

from unittest.mock import patch

import pytest

# HA has Linux-only build deps, so the default (Windows) dev env skips this file.
pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.config_entries import SOURCE_USER  # noqa: E402
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402

from custom_components.felicity_battery.const import (  # noqa: E402
    CONF_DEVICE_SN,
    DOMAIN,
)

FLOW = "custom_components.felicity_battery.config_flow"
USER_INPUT = {
    "username": "user@example.com",
    "password": "secret",
    "scan_interval": 300,
}
DEVICE = {"deviceSn": "0123456789ABCDEF", "deviceModel": "FLA48300", "alias": "Garage"}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def test_user_flow_creates_entry(hass) -> None:
    with (
        patch(f"{FLOW}.async_login", return_value="token"),
        patch(f"{FLOW}.async_fetch_devices", return_value=[DEVICE]),
        patch(f"{FLOW}.get_ssl_context", return_value=None),
        # Stop the new entry from setting up, which would poll the real cloud.
        patch(
            "custom_components.felicity_battery.async_setup_entry", return_value=True
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Felicity Garage"
    assert result["data"] == {**USER_INPUT, CONF_DEVICE_SN: "0123456789ABCDEF"}
