"""Constants for the Felicity Battery (FLA48300) integration.

This module is intentionally free of Home Assistant imports so that the pure
data-extraction helpers can depend on it and be unit-tested without HA.
"""

from __future__ import annotations

DOMAIN = "felicity_battery"

# This integration targets a single Felicity battery model.
DEVICE_MODEL = "FLA48300"
DEVICE_TYPE = "BP"  # battery pack — the only device type FLA48300 reports as
MANUFACTURER = "Felicity Solar"

# --- Config entry keys -----------------------------------------------------
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_DEVICE_SN = "device_sn"

# The FSolar cloud only refreshes a snapshot every `reportFreq` (300 s), so
# polling faster just re-reads stale data.
DEFAULT_SCAN_INTERVAL = 300
MIN_SCAN_INTERVAL = 60

# --- FSolar cloud API ------------------------------------------------------
API_BASE_URL = "https://shine-api.felicitysolar.com"
API_HEADERS = {
    "Content-Type": "application/json",
    "source": "IOS",
    "version": "3.2.3",
    "lang": "en_US",
}
LOGIN_URL = "/app/base/userlogin"
ENDPOINT_DEVICE_LIST = "/app/device/list_device_all_type"
ENDPOINT_DEVICE_SNAPSHOT = "/app/device/get_device_snapshot"
ENDPOINT_PLANT_LIST = "/app/plant/list_plant"

# Public key the FSolar app uses to RSA-encrypt the password on login.
RSA_PUBLIC_KEY = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAnAJE68pjWZmtSg6ZJs9F"
    "ZugJXC6bBSluTW6mJttOLOaljrdErVnM5DNN+YFzpB9pAysTErjY1bnSVuEwQSwptnq"
    "Uji7Ch2qMj2n+0eCp8p6vtSh7/tFr2ul8nDRtkoswLANAIwtUk/G85ipMpmY1W642LI"
    "mnEJmGkkddlbjbjxJTZWR5hc/d9cPWb+AR77LxFFrMik3c+44v1kQlIPFP6EjIbOvt/"
    "Lv7fHWD9JI/YzN4y1gK7C/VQdNGuikQyNg+5W3rg9ecYf9I5uLAQwY/hxeI3lbNs"
    "ErebqKe2EbJ8AwcNIC0lDBz53Sq0ML89QapEuy3fB+upuctxLULVDCbNwIDAQAB"
)

# --- BMS "no reading" sentinels --------------------------------------------
# Absent cells/probes are padded with 0x7FFF (max signed int16): 32767 raw for
# cell voltages (mV), and 3276.7 after the temperature field's 0.1 scaling.
CELL_VOLTAGE_PADDING_MV = 32767
TEMP_PADDING = 3276.7

# FLA48300 is a 16S pack with 4 temperature probes. Bounds guard against a
# malformed/oversized array while still covering the real hardware.
CELL_COUNT = 16
TEMP_SENSOR_COUNT = 4

# --- Enum states -----------------------------------------------------------
CHARGE_STATE_STANDBY = "standby"
CHARGE_STATE_CHARGING = "charging"
CHARGE_STATE_DISCHARGING = "discharging"
CHARGE_STATES = [
    CHARGE_STATE_STANDBY,
    CHARGE_STATE_CHARGING,
    CHARGE_STATE_DISCHARGING,
]
# `bmsChargingState` code -> state string
CHARGE_STATE_MAP = {
    0: CHARGE_STATE_STANDBY,
    1: CHARGE_STATE_CHARGING,
    2: CHARGE_STATE_DISCHARGING,
}

# `status` code -> device status string
DEVICE_STATUS_NORMAL = "normal"
DEVICE_STATUS_ALARM = "alarm"
DEVICE_STATUS_FAULT = "fault"
DEVICE_STATUS_OFFLINE = "offline"
DEVICE_STATUSES = [
    DEVICE_STATUS_NORMAL,
    DEVICE_STATUS_ALARM,
    DEVICE_STATUS_FAULT,
    DEVICE_STATUS_OFFLINE,
]
DEVICE_STATUS_MAP = {
    "NM": DEVICE_STATUS_NORMAL,
    "AL": DEVICE_STATUS_ALARM,
    "FL": DEVICE_STATUS_FAULT,
    "OF": DEVICE_STATUS_OFFLINE,
}
