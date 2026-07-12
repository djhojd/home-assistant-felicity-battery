"""DataUpdateCoordinator for the Felicity FLA48300 battery."""

from __future__ import annotations

import logging
import re
import ssl
from datetime import datetime, timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import InvalidAuth, async_login
from .const import (
    API_BASE_URL,
    API_HEADERS,
    DEVICE_TYPE,
    DOMAIN,
    ENDPOINT_DEVICE_LIST,
    ENDPOINT_DEVICE_SNAPSHOT,
    ENDPOINT_PLANT_LIST,
)
from .ssl_context import get_ssl_context

_LOGGER = logging.getLogger(__name__)


class FelicityBatteryCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll the FSolar cloud for a single FLA48300 battery snapshot."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        username: str,
        password: str,
        device_sn: str,
        scan_interval: int,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.username = username
        self.password = password
        self.device_sn = device_sn
        self.token: str | None = None
        self.device_model: str | None = None
        self.device_alias: str | None = None
        self.device_sw_version: str | None = None
        self.device_timezone: timedelta = timedelta(hours=0)
        self._session = async_get_clientsession(hass)
        self._ssl: ssl.SSLContext | None = None

    async def _get_ssl(self) -> ssl.SSLContext:
        """Build the SSL context off the event loop (blocking cert load)."""
        if self._ssl is None:
            self._ssl = await self.hass.async_add_executor_job(get_ssl_context)
        return self._ssl

    def _headers(self) -> dict[str, str]:
        headers = dict(API_HEADERS)
        if self.token:
            headers["Authorization"] = self.token
        return headers

    async def _post(self, url: str, payload: dict) -> aiohttp.ClientResponse:
        return await self._session.post(
            url, json=payload, headers=self._headers(), ssl=await self._get_ssl()
        )

    async def _login(self) -> None:
        try:
            self.token = await async_login(
                self._session,
                self.username,
                self.password,
                ssl_ctx=await self._get_ssl(),
            )
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed(f"Login failed: {err}") from err
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Connection error during login: {err}") from err

    async def _ensure_token(self) -> None:
        if not self.token:
            await self._login()

    @staticmethod
    def _is_auth_error(status: int, data: dict | None = None) -> bool:
        if status in (401, 302):
            return True
        return bool(data and data.get("code") == 401)

    @staticmethod
    def _parse_utc_offset(tz_str: str) -> timedelta:
        """Parse 'UTC+03:00' / 'UTC-03:00' to a timedelta."""
        match = re.match(r"UTC([+-])(\d{2}):(\d{2})", tz_str or "")
        if not match:
            return timedelta(hours=0)
        sign = 1 if match.group(1) == "+" else -1
        return timedelta(
            hours=sign * int(match.group(2)), minutes=sign * int(match.group(3))
        )

    async def fetch_device_info(self) -> None:
        """Fetch model, firmware and timezone metadata for the device."""
        await self._ensure_token()

        payload = {
            "status": "",
            "alias": "",
            "pageSize": 10,
            "realName": "",
            "deviceType": "",
            "pageNum": 1,
            "deviceSn": self.device_sn,
            "plantName": "",
            "orgName": "",
            "deviceModel": "",
        }
        try:
            resp = await self._post(f"{API_BASE_URL}{ENDPOINT_DEVICE_LIST}", payload)
            data = await resp.json()
            if self._is_auth_error(resp.status, data):
                self.token = None
                await self._login()
                resp = await self._post(
                    f"{API_BASE_URL}{ENDPOINT_DEVICE_LIST}", payload
                )
                data = await resp.json()
            if data.get("code") == 200:
                for device in data.get("data", {}).get("dataList", []):
                    if device.get("deviceSn") == self.device_sn:
                        self.device_model = device.get("deviceModel")
                        self.device_alias = device.get("alias")
                        self.device_sw_version = device.get("moduleVersion")
                        break
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Failed to fetch device info: {err}") from err

        # Timezone lives on the plant, used to localize the snapshot timestamp.
        try:
            resp = await self._post(
                f"{API_BASE_URL}{ENDPOINT_PLANT_LIST}",
                {"status": "all", "pageSize": 10, "pageNum": 1},
            )
            data = await resp.json()
            if data.get("code") == 200:
                for plant in data.get("data", {}).get("dataList", []):
                    for dev in plant.get("plantDeviceList", []):
                        if dev.get("deviceSn") == self.device_sn:
                            self.device_timezone = self._parse_utc_offset(
                                plant.get("timeZone", "")
                            )
                            return
        except aiohttp.ClientError as err:
            _LOGGER.warning("Failed to fetch plant timezone: %s", err)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch a fresh snapshot, re-authenticating once if the token expired."""
        await self._ensure_token()
        payload = {
            "collectorSn": "",
            "deviceSn": self.device_sn,
            "dateStr": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "deviceType": DEVICE_TYPE,
        }
        url = f"{API_BASE_URL}{ENDPOINT_DEVICE_SNAPSHOT}"

        try:
            resp = await self._post(url, payload)
            result = await resp.json()
            if self._is_auth_error(resp.status, result):
                self.token = None
                await self._login()
                resp = await self._post(url, payload)
                if resp.status != 200:
                    raise UpdateFailed(
                        f"API returned HTTP {resp.status} after re-login"
                    )
                result = await resp.json()
                if self._is_auth_error(resp.status, result):
                    raise ConfigEntryAuthFailed(
                        "Login succeeded but API still rejected the token"
                    )
            elif resp.status != 200:
                raise UpdateFailed(f"API returned HTTP {resp.status}")
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Connection error: {err}") from err

        code = result.get("code")
        if code == 401:
            raise ConfigEntryAuthFailed("API token expired or invalid")
        if code != 200:
            raise UpdateFailed(f"API returned code {code}: {result.get('message', '')}")

        data = result.get("data")
        if not data:
            raise UpdateFailed("API returned empty data")
        return data
