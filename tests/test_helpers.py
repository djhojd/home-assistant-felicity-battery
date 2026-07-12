"""Unit tests for the pure snapshot helpers, driven by a real FLA48300 capture.

The expected values below are the actual readings from the captured snapshot
(discharging at ~483 W, 89% SOC), so these tests pin the exact field mapping,
unit conversions, padding-sentinel filtering, and derived calculations.
"""

from __future__ import annotations

import pytest
from felicity_battery import helpers


# --- Core electrical readings ---------------------------------------------
def test_state_of_charge(snapshot):
    assert helpers.state_of_charge(snapshot) == 89.0


def test_state_of_health(snapshot):
    assert helpers.state_of_health(snapshot) == 100.0


def test_voltage(snapshot):
    assert helpers.voltage(snapshot) == 53.06


def test_current_is_negative_while_discharging(snapshot):
    assert helpers.current(snapshot) == -9.1


def test_power_is_negative_while_discharging(snapshot):
    assert helpers.power(snapshot) == -482.85


def test_discharge_power_is_positive(snapshot):
    assert helpers.discharge_power(snapshot) == 482.85


def test_charge_power_is_zero_while_discharging(snapshot):
    assert helpers.charge_power(snapshot) == 0.0


# --- Energy / capacity -----------------------------------------------------
def test_remaining_energy_is_reported_directly(snapshot):
    assert helpers.remaining_energy_kwh(snapshot) == 13.35


def test_total_energy_is_stable_nameplate(snapshot):
    assert helpers.total_energy_kwh(snapshot) == 15.0


def test_capacity_ah(snapshot):
    assert helpers.capacity_ah(snapshot) == 300.0


def test_rated_power_kw(snapshot):
    assert helpers.rated_power_kw(snapshot) == 7.5


# --- Charge state ----------------------------------------------------------
def test_charge_state_is_discharging(snapshot):
    assert helpers.charge_state(snapshot) == "discharging"


def test_is_discharging(snapshot):
    assert helpers.is_discharging(snapshot) is True


def test_is_charging(snapshot):
    assert helpers.is_charging(snapshot) is False


@pytest.mark.parametrize(
    ("code", "expected"),
    [(0, "standby"), (1, "charging"), (2, "discharging")],
)
def test_charge_state_map(code, expected):
    assert helpers.charge_state({"bmsChargingState": code}) == expected


def test_charge_state_missing_returns_none():
    assert helpers.charge_state({}) is None


# --- Temperatures ----------------------------------------------------------
def test_temperature_max(snapshot):
    assert helpers.temperature_max(snapshot) == 26.0


def test_temperature_min(snapshot):
    assert helpers.temperature_min(snapshot) == 25.0


def test_cell_temperatures_drops_padding(snapshot):
    # FLA48300 has 4 real probes; the list is padded with 3276.7 sentinels.
    assert helpers.cell_temperatures(snapshot) == [25.0, 25.0, 25.0, 26.0]


def test_cell_temperature_by_index(snapshot):
    assert helpers.cell_temperature(snapshot, 4) == 26.0
    assert helpers.cell_temperature(snapshot, 99) is None


# --- Cell voltages ---------------------------------------------------------
def test_cell_voltages_count_and_units(snapshot):
    volts = helpers.cell_voltages(snapshot)
    assert len(volts) == 16
    assert all(v is not None for v in volts)
    # mV -> V, all cells near 3.32 V
    assert all(3.3 < v < 3.35 for v in volts)


def test_cell_voltage_by_index(snapshot):
    assert helpers.cell_voltage(snapshot, 1) == 3.319


def test_cell_voltage_max_min(snapshot):
    assert helpers.cell_voltage_max(snapshot) == 3.32
    assert helpers.cell_voltage_min(snapshot) == 3.318


def test_cell_voltage_numbers(snapshot):
    assert helpers.cell_voltage_max_number(snapshot) == 4
    assert helpers.cell_voltage_min_number(snapshot) == 12


def test_cell_voltage_delta(snapshot):
    assert helpers.cell_voltage_delta(snapshot) == 0.002


def test_cell_voltage_padding_sentinel_becomes_none():
    # 32767 mV (0x7FFF) is the "no cell" sentinel and must map to None.
    result = helpers.cell_voltages({"bmsVoltageList": ["3300", "32767"]})
    assert result == [3.3, None]


# --- BMS limits & diagnostics ---------------------------------------------
def test_voltage_limits(snapshot):
    assert helpers.charge_voltage_limit(snapshot) == 57.6
    assert helpers.discharge_voltage_limit(snapshot) == 48.0


def test_current_limits(snapshot):
    assert helpers.charge_current_limit(snapshot) == 82.5
    assert helpers.discharge_current_limit(snapshot) == 150.0


def test_wifi_signal(snapshot):
    assert helpers.wifi_signal(snapshot) == -79.0


def test_warning_count(snapshot):
    assert helpers.warning_count(snapshot) == 0


def test_device_status_normal(snapshot):
    assert helpers.device_status(snapshot) == "normal"


def test_is_heating_false(snapshot):
    assert helpers.is_heating(snapshot) is False


def test_is_problem_false_when_normal(snapshot):
    assert helpers.is_problem(snapshot) is False


def test_is_problem_true_on_alarm():
    assert helpers.is_problem({"status": "AL", "warningCount": 0}) is True


def test_is_problem_true_on_warnings():
    assert helpers.is_problem({"status": "NM", "warningCount": 3}) is True


def test_timestamp_str(snapshot):
    assert helpers.timestamp_str(snapshot) == "2026-07-12 02:10:00"


# --- Derived: time remaining ----------------------------------------------
def test_time_remaining_while_discharging(snapshot):
    # 13.35 kWh / 0.48285 kW ~= 27.65 h
    assert helpers.time_remaining_hours(snapshot) == 27.65


def test_time_remaining_while_charging():
    data = {
        "bmsChargingState": 1,
        "bmsPower": "1000",
        "remainingBatteryEnergy1": "10",
        "ratedEnergy": "15",
    }
    # (15 - 10) kWh / 1 kW = 5 h
    assert helpers.time_remaining_hours(data) == 5.0


def test_time_remaining_none_in_standby():
    data = {"bmsChargingState": 0, "bmsPower": "0", "remainingBatteryEnergy1": "10"}
    assert helpers.time_remaining_hours(data) is None


# --- Derived: energy integration ------------------------------------------
def test_integrate_energy_accumulates():
    # 1000 W constant for 3600 s = 1 kWh
    result = helpers.integrate_energy_kwh(0.0, 1000.0, 1000.0, 3600)
    assert result == pytest.approx(1.0)


def test_integrate_energy_ignores_negative_power():
    # discharging (negative avg power) must not add to a charge accumulator
    assert helpers.integrate_energy_kwh(2.0, -500.0, -500.0, 3600) == 2.0


def test_integrate_energy_zero_elapsed():
    assert helpers.integrate_energy_kwh(2.0, 1000.0, 1000.0, 0) == 2.0


# --- Robustness ------------------------------------------------------------
def test_helpers_tolerate_empty_dict():
    empty: dict = {}
    assert helpers.state_of_charge(empty) is None
    assert helpers.power(empty) is None
    assert helpers.cell_voltages(empty) == []
    assert helpers.cell_temperatures(empty) == []
    assert helpers.time_remaining_hours(empty) is None
