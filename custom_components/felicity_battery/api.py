"""HTTP client for the FSolar cloud API (login + device listing).

Login requires the password to be RSA-encrypted with the server's public key,
exactly as the FSolar mobile app does it. This module owns that so both the
config flow and the coordinator can reuse it.
"""

from __future__ import annotations

import base64
import ssl

import aiohttp
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .const import (
    API_BASE_URL,
    API_HEADERS,
    ENDPOINT_DEVICE_LIST,
    LOGIN_URL,
    RSA_PUBLIC_KEY,
)


class InvalidAuth(Exception):
    """Raised when the API rejects the supplied credentials."""


def encrypt_password(password: str, public_key_b64: str = RSA_PUBLIC_KEY) -> str:
    """RSA-encrypt (PKCS1v15) the password with the server key, then base64 it."""
    pem = f"-----BEGIN PUBLIC KEY-----\n{public_key_b64}\n-----END PUBLIC KEY-----"
    public_key = serialization.load_pem_public_key(pem.encode())
    encrypted = public_key.encrypt(password.encode(), padding.PKCS1v15())
    return base64.b64encode(encrypted).decode()


async def async_login(
    session: aiohttp.ClientSession,
    username: str,
    password: str,
    ssl_ctx: ssl.SSLContext | None = None,
) -> str:
    """Log in to the FSolar API and return the auth token.

    Raises ``InvalidAuth`` on rejected credentials and ``aiohttp.ClientError``
    on connection problems.
    """
    async with session.post(
        f"{API_BASE_URL}{LOGIN_URL}",
        json={
            "userName": username,
            "password": encrypt_password(password),
            "registrationId": "",
            "version": "1.0",
        },
        headers=API_HEADERS,
        ssl=ssl_ctx,
    ) as resp:
        data = await resp.json()
    if data.get("code") == 200:
        return data["data"]["token"]
    raise InvalidAuth(data.get("message", "Login failed"))


async def async_fetch_devices(
    session: aiohttp.ClientSession,
    token: str,
    ssl_ctx: ssl.SSLContext | None = None,
) -> list[dict]:
    """Fetch all devices on the account."""
    headers = dict(API_HEADERS)
    headers["Authorization"] = token
    async with session.post(
        f"{API_BASE_URL}{ENDPOINT_DEVICE_LIST}",
        json={
            "status": "",
            "alias": "",
            "pageSize": 50,
            "realName": "",
            "deviceType": "",
            "pageNum": 1,
            "deviceSn": "",
            "plantName": "",
            "orgName": "",
            "deviceModel": "",
        },
        headers=headers,
        ssl=ssl_ctx,
    ) as resp:
        data = await resp.json()
    if data.get("code") != 200:
        raise InvalidAuth(data.get("message", "Failed to fetch devices"))
    return data.get("data", {}).get("dataList", [])
