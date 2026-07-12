# Felicity Battery (FLA48300) — Home Assistant

Monitor a **Felicity Solar FLA48300** battery in Home Assistant through the FSolar / Felicity Cloud API. It signs in like the FSolar mobile app (RSA-encrypted password), polls one snapshot per interval, and exposes every meaningful field as a first-class sensor — energy remaining, true nameplate capacity, charge/discharge/standby state, per-cell voltages and temperatures, BMS limits, and health diagnostics.

Cloud polling only (no local/Modbus). Deliberately scoped to the FLA48300, verified against a real 16S / ~15 kWh / 48 V LiFePO₄ pack, so the field mapping is exact and unit-tested rather than a guess across the whole Felicity range.

## Requirements

- Your FLA48300 already reporting to the **FSolar / Felicity Cloud** app.
- Your FSolar account **email and password**.

## Install

**HACS:** add `https://github.com/djhojd/home-assistant-felicity-battery` as a custom **Integration** repository, install, and restart. Then **Settings → Devices & Services → Add Integration → Felicity Battery** and sign in.

**Manual:** copy `custom_components/felicity_battery` into `config/custom_components/` and restart.

## Sensors

**Core (enabled by default)**

| Sensor | Source | Notes |
|---|---|---|
| State of charge / health | `battSoc` / `battSoh` | % |
| Voltage / Current / Power | `battVolt` / `battCurr` / `bmsPower` | negative while discharging |
| Charge power / Discharge power | derived from `bmsPower` | positive-only split |
| Remaining energy | `remainingBatteryEnergy1` | **kWh, reported directly** — no estimation |
| Total energy | `ratedEnergy` | stable nameplate kWh |
| Temperature / Temperature (min) | `tempMax` / `tempMin` | °C |
| Charge status | `bmsChargingState` | Standby / Charging / Discharging |
| Time remaining | derived | hours to empty (discharging) or full (charging) |
| Cell voltage delta / max / min | BMS | max/min expose the cell number |
| Daily charge / discharge energy | integrated | resets at local midnight (see below) |

**Diagnostics** (some disabled by default): capacity (Ah), rated power, WiFi signal, device status, warning count, BMS state, charge/discharge voltage & current limits, last update, plus **16 per-cell voltages** and **4 per-probe temperatures**.

**Daily energy:** the FSolar cloud has no per-day counters, so these are integrated from live power (refreshed ~every 5 min) and reset at local midnight — good estimates, not revenue-grade. For tighter accuracy or the Energy Dashboard, feed **Charge/Discharge power** into HA's built-in **Riemann sum** + **Utility Meter** helpers.
