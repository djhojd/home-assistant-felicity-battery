"""Config flow for the Felicity FLA48300 battery integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import InvalidAuth, async_fetch_devices, async_login
from .const import (
    CONF_DEVICE_SN,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEFAULT_SCAN_INTERVAL,
    DEVICE_MODEL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .ssl_context import get_ssl_context

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            int, vol.Range(min=MIN_SCAN_INTERVAL)
        ),
    }
)

STEP_REAUTH_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


def _is_fla48300(device: dict) -> bool:
    """Only surface FLA48300 packs — this integration is scoped to that model."""
    return str(device.get("deviceModel", "")).upper() == DEVICE_MODEL


class FelicityBatteryConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Felicity FLA48300 battery."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._devices: list[dict] = []
        self._user_input: dict[str, Any] = {}

    async def _async_login_and_list(
        self, username: str, password: str
    ) -> tuple[list[dict] | None, dict[str, str]]:
        """Log in and return the account's FLA48300 devices (or an error key)."""
        try:
            session = async_get_clientsession(self.hass)
            ssl_ctx = await self.hass.async_add_executor_job(get_ssl_context)
            token = await async_login(session, username, password, ssl_ctx=ssl_ctx)
            devices = await async_fetch_devices(session, token, ssl_ctx=ssl_ctx)
        except InvalidAuth:
            return None, {"base": "invalid_auth"}
        except aiohttp.ClientError:
            return None, {"base": "cannot_connect"}
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error during login")
            return None, {"base": "unknown"}

        felicity = [d for d in devices if _is_fla48300(d) and d.get("deviceSn")]
        if not felicity:
            return None, {"base": "no_devices"}
        return felicity, {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the credentials step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            devices, errors = await self._async_login_and_list(
                user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            if devices is not None:
                self._devices = devices
                self._user_input = user_input
                if len(devices) == 1:
                    return await self._create_entry(devices[0])
                return await self.async_step_device()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick which FLA48300 to add when the account has more than one."""
        if user_input is not None:
            device = next(
                (
                    d
                    for d in self._devices
                    if d["deviceSn"] == user_input[CONF_DEVICE_SN]
                ),
                None,
            )
            if device is not None:
                return await self._create_entry(device)

        options = {
            d["deviceSn"]: f"{d.get('alias', d['deviceSn'])} - {d['deviceSn']}"
            for d in self._devices
        }
        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema({vol.Required(CONF_DEVICE_SN): vol.In(options)}),
        )

    async def _create_entry(self, device: dict) -> ConfigFlowResult:
        """Finalize the entry for the chosen device."""
        device_sn = device["deviceSn"]
        await self.async_set_unique_id(device_sn)
        self._abort_if_unique_id_configured()
        alias = device.get("alias") or device_sn
        return self.async_create_entry(
            title=f"Felicity {alias}",
            data={**self._user_input, CONF_DEVICE_SN: device_sn},
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start re-authentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm re-authentication with new credentials."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            devices, errors = await self._async_login_and_list(
                user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            if devices is not None:
                await self.async_set_unique_id(devices[0]["deviceSn"])
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_DATA_SCHEMA,
            description_placeholders={CONF_USERNAME: reauth_entry.data[CONF_USERNAME]},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure credentials and scan interval."""
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()

        if user_input is not None:
            devices, errors = await self._async_login_and_list(
                user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            if devices is not None:
                await self.async_set_unique_id(devices[0]["deviceSn"])
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    data_updates={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                    },
                )

        data = reconfigure_entry.data
        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME, default=data[CONF_USERNAME]): str,
                vol.Required(CONF_PASSWORD, default=data[CONF_PASSWORD]): str,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(int, vol.Range(min=MIN_SCAN_INTERVAL)),
            }
        )
        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=errors
        )
