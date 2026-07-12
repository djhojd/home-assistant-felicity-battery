"""Pure data-extraction helpers for the Felicity FLA48300 snapshot.

Every function here takes the raw ``data`` dict returned by the FSolar
``get_device_snapshot`` endpoint and returns a clean, typed value. There are
deliberately **no Home Assistant imports** in this module so the mapping logic
(field names, unit conversions, padding-sentinel filtering, derived values) can
be unit-tested against a real device fixture without installing HA.

Sign conventions on the FLA48300:
- ``battCurr`` / ``bmsPower`` are negative while discharging, positive while
  charging. ``bmsChargingState`` is the authoritative 0/1/2 standby/charge/
  discharge flag.
- Cell voltages come in millivolts; temperatures in whole degrees Celsius.
"""

from __future__ import annotations

from typing import Any

from .const import (
    CELL_COUNT,
    CELL_VOLTAGE_PADDING_MV,
    CHARGE_STATE_CHARGING,
    CHARGE_STATE_DISCHARGING,
    CHARGE_STATE_MAP,
    DEVICE_STATUS_MAP,
    TEMP_PADDING,
    TEMP_SENSOR_COUNT,
)


def to_float(value: Any) -> float | None:
    """Convert an API value to float, returning None if it can't be parsed."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def to_int(value: Any) -> int | None:
    """Convert an API value to int, returning None if it can't be parsed."""
    f = to_float(value)
    return None if f is None else int(f)


# --- Core electrical readings ---------------------------------------------
def state_of_charge(data: dict[str, Any]) -> float | None:
    """Battery state of charge in percent."""
    return to_float(data.get("battSoc") or data.get("emsSocAvg"))


def state_of_health(data: dict[str, Any]) -> float | None:
    """Battery state of health in percent."""
    return to_float(data.get("battSoh") or data.get("emsSoh"))


def voltage(data: dict[str, Any]) -> float | None:
    """Pack voltage in volts."""
    return to_float(data.get("battVolt") or data.get("emsVoltage"))


def current(data: dict[str, Any]) -> float | None:
    """Pack current in amps (negative = discharging)."""
    return to_float(data.get("battCurr") or data.get("emsCurrent"))


def power(data: dict[str, Any]) -> float | None:
    """Pack power in watts (negative = discharging, positive = charging)."""
    return to_float(data.get("bmsPower") or data.get("emsPower"))


def charge_power(data: dict[str, Any]) -> float | None:
    """Charging power in watts (0 while discharging/standby)."""
    p = power(data)
    if p is None:
        return None
    return p if p > 0 else 0.0


def discharge_power(data: dict[str, Any]) -> float | None:
    """Discharging power in watts as a positive number (0 while charging)."""
    p = power(data)
    if p is None:
        return None
    return -p if p < 0 else 0.0


# --- Energy / capacity -----------------------------------------------------
def remaining_energy_kwh(data: dict[str, Any]) -> float | None:
    """Energy currently stored in the pack, in kWh (reported directly)."""
    return to_float(data.get("remainingBatteryEnergy1"))


def total_energy_kwh(data: dict[str, Any]) -> float | None:
    """Nameplate usable energy in kWh (stable; not derived from live voltage)."""
    return to_float(data.get("ratedEnergy"))


def capacity_ah(data: dict[str, Any]) -> float | None:
    """Rated capacity in amp-hours."""
    return to_float(
        data.get("battCapacity")
        or data.get("emsCapacity")
        or data.get("totalEmsCapacity")
    )


def rated_power_kw(data: dict[str, Any]) -> float | None:
    """Nameplate maximum power in kW."""
    return to_float(data.get("ratedPower"))


# --- Charge state ----------------------------------------------------------
def charge_state(data: dict[str, Any]) -> str | None:
    """Return 'standby' | 'charging' | 'discharging' from bmsChargingState."""
    code = data.get("bmsChargingState")
    if code is None:
        return None
    return CHARGE_STATE_MAP.get(int(code))


def is_charging(data: dict[str, Any]) -> bool | None:
    """True if the pack is charging."""
    state = charge_state(data)
    return None if state is None else state == CHARGE_STATE_CHARGING


def is_discharging(data: dict[str, Any]) -> bool | None:
    """True if the pack is discharging."""
    state = charge_state(data)
    return None if state is None else state == CHARGE_STATE_DISCHARGING


# --- Temperatures ----------------------------------------------------------
def temperature_max(data: dict[str, Any]) -> float | None:
    """Highest pack temperature in Celsius."""
    return to_float(data.get("tempMax"))


def temperature_min(data: dict[str, Any]) -> float | None:
    """Lowest pack temperature in Celsius."""
    return to_float(data.get("tempMin"))


def cell_temperatures(data: dict[str, Any]) -> list[float | None]:
    """Per-probe temperatures in Celsius, padding sentinels -> None.

    Positions are preserved so probe numbering stays stable.
    """
    temps = data.get("cellTempList") or []
    result: list[float | None] = []
    for raw in temps[:TEMP_SENSOR_COUNT]:
        val = to_float(raw)
        result.append(None if val is None or val >= TEMP_PADDING else val)
    return result


def cell_temperature(data: dict[str, Any], index: int) -> float | None:
    """1-based per-probe temperature."""
    temps = cell_temperatures(data)
    if 1 <= index <= len(temps):
        return temps[index - 1]
    return None


# --- Cell voltages ---------------------------------------------------------
def cell_voltages(data: dict[str, Any]) -> list[float | None]:
    """Per-cell voltages in volts (from the mV list), padding -> None."""
    volts = data.get("bmsVoltageList") or []
    result: list[float | None] = []
    for raw in volts[:CELL_COUNT]:
        mv = to_float(raw)
        if mv is None or mv >= CELL_VOLTAGE_PADDING_MV:
            result.append(None)
        else:
            result.append(round(mv / 1000, 3))
    return result


def cell_voltage(data: dict[str, Any], index: int) -> float | None:
    """1-based per-cell voltage in volts."""
    volts = cell_voltages(data)
    if 1 <= index <= len(volts):
        return volts[index - 1]
    return None


def cell_voltage_max(data: dict[str, Any]) -> float | None:
    """Highest cell voltage in volts (reported field, fallback to list max)."""
    mv = to_float(data.get("maxVoltage2bms"))
    if mv is not None:
        return round(mv / 1000, 3)
    volts = [v for v in cell_voltages(data) if v is not None]
    return max(volts) if volts else None


def cell_voltage_min(data: dict[str, Any]) -> float | None:
    """Lowest cell voltage in volts (reported field, fallback to list min)."""
    mv = to_float(data.get("minVoltage2bms"))
    if mv is not None:
        return round(mv / 1000, 3)
    volts = [v for v in cell_voltages(data) if v is not None]
    return min(volts) if volts else None


def cell_voltage_max_number(data: dict[str, Any]) -> int | None:
    """Which cell (1-based) holds the highest voltage."""
    return to_int(data.get("maxVoltageNum2bms"))


def cell_voltage_min_number(data: dict[str, Any]) -> int | None:
    """Which cell (1-based) holds the lowest voltage."""
    return to_int(data.get("minVoltageNum2bms"))


def cell_voltage_delta(data: dict[str, Any]) -> float | None:
    """Difference between highest and lowest cell voltage, in volts."""
    hi = cell_voltage_max(data)
    lo = cell_voltage_min(data)
    if hi is None or lo is None:
        return None
    return round(hi - lo, 3)


# --- BMS limits & diagnostics ---------------------------------------------
def charge_voltage_limit(data: dict[str, Any]) -> float | None:
    """BMS charge voltage limit in volts."""
    return to_float(data.get("BMSLCVolt"))


def discharge_voltage_limit(data: dict[str, Any]) -> float | None:
    """BMS discharge (cut-off) voltage limit in volts."""
    return to_float(data.get("BMSLDVolt"))


def charge_current_limit(data: dict[str, Any]) -> float | None:
    """BMS charge current limit in amps."""
    return to_float(data.get("BMSLCCurr") or data.get("bmslccurr"))


def discharge_current_limit(data: dict[str, Any]) -> float | None:
    """BMS discharge current limit in amps."""
    return to_float(data.get("BMSLDCurr") or data.get("bmsldcurr"))


def wifi_signal(data: dict[str, Any]) -> float | None:
    """Datalogger WiFi signal strength in dBm."""
    return to_float(data.get("wifiSignal"))


def warning_count(data: dict[str, Any]) -> int | None:
    """Number of active warnings/alarms."""
    return to_int(data.get("warningCount"))


def bms_state_code(data: dict[str, Any]) -> int | None:
    """Raw BMS state code."""
    return to_int(data.get("bmsState"))


def device_status(data: dict[str, Any]) -> str | None:
    """Device status: 'normal' | 'alarm' | 'fault' | 'offline'."""
    code = data.get("status")
    if code is None:
        return None
    return DEVICE_STATUS_MAP.get(code, None)


def is_heating(data: dict[str, Any]) -> bool | None:
    """True if the battery heater is active."""
    raw = data.get("heatStatus")
    if raw is None:
        return None
    val = to_int(raw)
    return None if val is None else val != 0


def is_problem(data: dict[str, Any]) -> bool | None:
    """True if the device reports a non-normal status or any warnings."""
    status = device_status(data)
    warnings = warning_count(data)
    if status is None and warnings is None:
        return None
    return (status not in (None, "normal")) or bool(warnings)


def timestamp_str(data: dict[str, Any]) -> str | None:
    """Raw 'YYYY-MM-DD HH:MM:SS' timestamp of this snapshot (device local)."""
    value = data.get("dataTimeStr")
    return value if isinstance(value, str) and value else None


# --- Derived: time remaining ----------------------------------------------
def time_remaining_hours(data: dict[str, Any]) -> float | None:
    """Estimated hours until empty (discharging) or full (charging).

    Uses the directly-reported remaining/total energy and live power, so no
    Ah<->kWh guessing is needed. Returns None in standby or when power is zero.
    """
    state = charge_state(data)
    p = power(data)
    remaining = remaining_energy_kwh(data)
    total = total_energy_kwh(data)
    if state is None or p is None or p == 0 or remaining is None:
        return None

    power_kw = abs(p) / 1000
    if power_kw == 0:
        return None

    if state == CHARGE_STATE_DISCHARGING:
        return round(remaining / power_kw, 2)
    if state == CHARGE_STATE_CHARGING:
        if total is None:
            return None
        return round(max(total - remaining, 0.0) / power_kw, 2)
    return None


# --- Derived: energy integration (for daily charge/discharge sensors) ------
def integrate_energy_kwh(
    prev_energy_kwh: float,
    prev_power_w: float,
    current_power_w: float,
    elapsed_seconds: float,
) -> float:
    """Trapezoidal accumulation of energy (kWh) over one interval.

    Kept pure so the daily-energy sensor's math is unit-tested independently of
    Home Assistant's RestoreEntity plumbing.
    """
    if elapsed_seconds <= 0:
        return prev_energy_kwh
    avg_power_w = (prev_power_w + current_power_w) / 2
    if avg_power_w <= 0:
        return prev_energy_kwh
    return prev_energy_kwh + (avg_power_w * elapsed_seconds / 3600) / 1000
