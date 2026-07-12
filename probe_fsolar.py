# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "cryptography", "python-dotenv"]
# ///
"""Standalone probe for the Felicity Solar (FSolar) cloud API.

Verifies that your account/battery works against shine-api.felicitysolar.com
BEFORE we commit to building a Home Assistant integration. It logs in the same
way the FSolar mobile app does (RSA-encrypted password), lists your devices,
and dumps one live snapshot so we can see exactly which fields your battery
reports.

Run it locally so your credentials never leave your machine. Credentials are
read in this order: a local `.env` file, then real environment variables, then
an interactive prompt.

    # Option A (recommended) - put creds in .env once, then just:
    uv run probe_fsolar.py

    # Option B - one-off environment variables:
    FSOLAR_EMAIL="you@example.com" FSOLAR_PASSWORD='your-password' \
        uv run probe_fsolar.py

    # Option C - no .env, no env vars: type them when prompted.
    uv run probe_fsolar.py

Nothing sensitive is printed: the password and auth token are never echoed.
Device serial numbers and battery readings ARE printed (we need them).
"""

from __future__ import annotations

import base64
import json
import os
import sys
from datetime import datetime
from getpass import getpass

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from dotenv import load_dotenv

BASE_URL = "https://shine-api.felicitysolar.com"
LOGIN_URL = f"{BASE_URL}/app/base/userlogin"
DEVICE_LIST_URL = f"{BASE_URL}/app/device/list_device_all_type"
SNAPSHOT_URL = f"{BASE_URL}/app/device/get_device_snapshot"

# Public key the FSolar app uses to encrypt the password before sending it.
RSA_PUBLIC_KEY = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAnAJE68pjWZmtSg6ZJs9F"
    "ZugJXC6bBSluTW6mJttOLOaljrdErVnM5DNN+YFzpB9pAysTErjY1bnSVuEwQSwptnq"
    "Uji7Ch2qMj2n+0eCp8p6vtSh7/tFr2ul8nDRtkoswLANAIwtUk/G85ipMpmY1W642LI"
    "mnEJmGkkddlbjbjxJTZWR5hc/d9cPWb+AR77LxFFrMik3c+44v1kQlIPFP6EjIbOvt/"
    "Lv7fHWD9JI/YzN4y1gK7C/VQdNGuikQyNg+5W3rg9ecYf9I5uLAQwY/hxeI3lbNs"
    "ErebqKe2EbJ8AwcNIC0lDBz53Sq0ML89QapEuy3fB+upuctxLULVDCbNwIDAQAB"
)

HEADERS = {
    "Content-Type": "application/json",
    "source": "IOS",
    "version": "3.2.3",
    "lang": "en_US",
}


def encrypt_password(password: str) -> str:
    """RSA-encrypt (PKCS1v15) the password with the server key, base64 it."""
    pem = f"-----BEGIN PUBLIC KEY-----\n{RSA_PUBLIC_KEY}\n-----END PUBLIC KEY-----"
    public_key = serialization.load_pem_public_key(pem.encode())
    encrypted = public_key.encrypt(password.encode(), padding.PKCS1v15())
    return base64.b64encode(encrypted).decode()


def make_session() -> requests.Session:
    """Session that tolerates the server's missing intermediate certificate.

    Felicity's server omits the 'Xcc Trust' intermediate, so strict
    verification can fail. We try verified first, and only fall back to
    unverified (with a loud warning) for this throwaway probe.
    """
    return requests.Session()


def post(session: requests.Session, url: str, payload: dict, headers: dict) -> dict:
    """POST JSON, retrying with verification disabled on a TLS chain error."""
    try:
        resp = session.post(url, json=payload, headers=headers, timeout=30)
    except requests.exceptions.SSLError:
        print(
            "  ! TLS verification failed (missing intermediate cert); "
            "retrying WITHOUT verification for this probe only.",
            file=sys.stderr,
        )
        import urllib3

        urllib3.disable_warnings()
        resp = session.post(
            url, json=payload, headers=headers, timeout=30, verify=False
        )
    resp.raise_for_status()
    return resp.json()


# Placeholder values shipped in .env.example / the starter .env. If they are
# still present, treat the credential as unset so we prompt instead of sending
# obviously-fake data to the API.
_PLACEHOLDERS = {"you@example.com", "your-fsolar-password"}


def _cred(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return None if value in _PLACEHOLDERS or not value else value


def main() -> int:
    # Load a local .env if present; real env vars still win over the file.
    load_dotenv(override=False)

    email = _cred("FSOLAR_EMAIL") or input("FSolar email: ").strip()
    password = _cred("FSOLAR_PASSWORD") or getpass("FSolar password: ")
    if not email or not password:
        print("Email and password are required.", file=sys.stderr)
        return 2

    session = make_session()

    # --- 1. Login -----------------------------------------------------------
    print(f"\n[1] Logging in as {email} ...")
    login_resp = post(
        session,
        LOGIN_URL,
        {
            "userName": email,
            "password": encrypt_password(password),
            "registrationId": "",
            "version": "1.0",
        },
        HEADERS,
    )
    if login_resp.get("code") != 200:
        print(
            f"  LOGIN FAILED: code={login_resp.get('code')} "
            f"message={login_resp.get('message')!r}",
            file=sys.stderr,
        )
        print(f"  Full response: {json.dumps(login_resp, indent=2)}", file=sys.stderr)
        return 1
    token = login_resp["data"]["token"]
    print("  OK - authenticated (token received, not printed).")

    auth_headers = dict(HEADERS)
    auth_headers["Authorization"] = token

    # --- 2. List devices ----------------------------------------------------
    print("\n[2] Listing devices ...")
    dev_resp = post(
        session,
        DEVICE_LIST_URL,
        {
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
        auth_headers,
    )
    if dev_resp.get("code") != 200:
        print(
            f"  DEVICE LIST FAILED: {json.dumps(dev_resp, indent=2)}", file=sys.stderr
        )
        return 1
    devices = dev_resp.get("data", {}).get("dataList", [])
    print(f"  Found {len(devices)} device(s).")
    for d in devices:
        print(
            f"    - SN={d.get('deviceSn')} type={d.get('deviceType')} "
            f"model={d.get('deviceModel')} alias={d.get('alias')!r} "
            f"status={d.get('status')}"
        )

    if not devices:
        print("  No devices on this account - nothing to snapshot.")
        return 0

    # --- 3. Snapshot each device -------------------------------------------
    for d in devices:
        sn = d.get("deviceSn")
        dtype = d.get("deviceType", "")
        print(f"\n[3] Snapshot for SN={sn} (type={dtype}) ...")
        snap = post(
            session,
            SNAPSHOT_URL,
            {
                "deviceSn": sn,
                "deviceType": dtype,
                "dateStr": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            auth_headers,
        )
        if snap.get("code") != 200:
            print(f"  SNAPSHOT FAILED: {json.dumps(snap, indent=2)}", file=sys.stderr)
            continue
        data = snap.get("data", {})
        print(f"  {len(data)} fields returned.")

        # Save a local fixture for later test-driven development. Gitignored
        # (contains the serial); the *.local.json suffix keeps it out of git.
        fixtures = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
        os.makedirs(fixtures, exist_ok=True)
        model = d.get("deviceModel", "device")
        out = os.path.join(fixtures, f"snapshot_{model}_{sn[-4:]}.local.json")
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False, default=str)
        print(f"  Saved fixture -> {os.path.relpath(out)}")

        # Print only the fields that carry a real (non-null) value, so the
        # signal isn't buried in ~500 nulls this battery-only device returns.
        live = {k: v for k, v in data.items() if v not in (None, "", "-")}
        print(f"  {len(live)} non-empty fields:")
        print(json.dumps(live, indent=2, ensure_ascii=False, default=str))

    print("\nDone. This confirms the FSolar cloud API works for your account.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
