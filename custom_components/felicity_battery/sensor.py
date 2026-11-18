"""Sensor platform for the Felicity FLA48300 battery.

Every meaningful field the FLA48300 reports is exposed as a first-class sensor
(not buried in attributes), plus two derived sensors: an estimated time-to-
empty/full and daily charge/discharge energy integrated from live power.

All value extraction lives in the pure ``helpers`` module so it can be unit-
tested against a real device snapshot without Home Assistant.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from . import FelicityConfigEntry, helpers
from .const import (
    CELL_COUNT,
    CHARGE_STATES,
    DEVICE_STATUSES,
    TEMP_SENSOR_COUNT,
)
from .coordinator import FelicityBatteryCoordinator
from .entity import FelicityBatteryEntity

PARALLEL_UPDATES = 0

UNIT_AMP_HOUR = "Ah"


@dataclass(frozen=True, kw_only=True)
class FelicitySensorDescription(SensorEntityDescription):
    """Describe a Felicity sensor backed by a pure helper function."""

    value_fn: Callable[[dict[str, Any]], StateType | datetime]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _max_cell_attrs(data: dict[str, Any]) -> dict[str, Any]:
    return {"cell_number": helpers.cell_voltage_max_number(data)}


def _min_cell_attrs(data: dict[str, Any]) -> dict[str, Any]:
    return {"cell_number": helpers.cell_voltage_min_number(data)}


SENSOR_DESCRIPTIONS: tuple[FelicitySensorDescription, ...] = (
    # --- Core (enabled) ---
    FelicitySensorDescription(
        key="state_of_charge",
        translation_key="state_of_charge",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=helpers.state_of_charge,
    ),
    FelicitySensorDescription(
        key="state_of_health",
        translation_key="state_of_health",
        icon="mdi:battery-heart-variant",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=helpers.state_of_health,
    ),
    FelicitySensorDescription(
        key="voltage",
        translation_key="voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=helpers.voltage,
    ),
    FelicitySensorDescription(
        key="current",
        translation_key="current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=helpers.current,
    ),
    FelicitySensorDescription(
        key="power",
        translation_key="power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=helpers.power,
    ),
    FelicitySensorDescription(
        key="charge_power",
        translation_key="charge_power",
        icon="mdi:battery-arrow-up",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=helpers.charge_power,
    ),
    FelicitySensorDescription(
        key="discharge_power",
        translation_key="discharge_power",
        icon="mdi:battery-arrow-down",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=helpers.discharge_power,
    ),
    FelicitySensorDescription(
        key="remaining_energy",
        translation_key="remaining_energy",
        icon="mdi:battery-50",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=helpers.remaining_energy_kwh,
    ),
    FelicitySensorDescription(
        key="total_energy",
        translation_key="total_energy",
        icon="mdi:battery-high",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        suggested_display_precision=2,
        value_fn=helpers.total_energy_kwh,
    ),
    FelicitySensorDescription(
        key="temperature",
        translation_key="temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=helpers.temperature_max,
    ),
    FelicitySensorDescription(
        key="temperature_min",
        translation_key="temperature_min",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=helpers.temperature_min,
    ),
    FelicitySensorDescription(
        key="charge_status",
        translation_key="charge_status",
        device_class=SensorDeviceClass.ENUM,
        options=CHARGE_STATES,
        value_fn=helpers.charge_state,
    ),
    FelicitySensorDescription(
        key="time_remaining",
        translation_key="time_remaining",
        icon="mdi:timer-sand",
        native_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        suggested_display_precision=1,
        value_fn=helpers.time_remaining_hours,
    ),
    FelicitySensorDescription(
        key="cell_voltage_delta",
        translation_key="cell_voltage_delta",
        icon="mdi:battery-sync",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        value_fn=helpers.cell_voltage_delta,
    ),
    FelicitySensorDescription(
        key="cell_voltage_max",
        translation_key="cell_voltage_max",
        icon="mdi:battery-plus-variant",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        value_fn=helpers.cell_voltage_max,
        attrs_fn=_max_cell_attrs,
    ),
    FelicitySensorDescription(
        key="cell_voltage_min",
        translation_key="cell_voltage_min",
        icon="mdi:battery-minus-variant",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        value_fn=helpers.cell_voltage_min,
        attrs_fn=_min_cell_attrs,
    ),
    # --- Diagnostic ---
    FelicitySensorDescription(
        key="capacity",
        translation_key="capacity",
        icon="mdi:battery-high",
        native_unit_of_measurement=UNIT_AMP_HOUR,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=helpers.capacity_ah,
    ),
    FelicitySensorDescription(
        key="rated_power",
        translation_key="rated_power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=helpers.rated_power_kw,
    ),
    FelicitySensorDescription(
        key="wifi_signal",
        translation_key="wifi_signal",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=helpers.wifi_signal,
    ),
    FelicitySensorDescription(
        key="device_status",
        translation_key="device_status",
        device_class=SensorDeviceClass.ENUM,
        options=DEVICE_STATUSES,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=helpers.device_status,
    ),
    FelicitySensorDescription(
        key="warning_count",
        translation_key="warning_count",
        icon="mdi:alert-circle-outline",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=helpers.warning_count,
    ),
    FelicitySensorDescription(
        key="bms_state",
        translation_key="bms_state",
        icon="mdi:state-machine",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=helpers.bms_state_code,
    ),
    FelicitySensorDescription(
        key="charge_voltage_limit",
        translation_key="charge_voltage_limit",
        icon="mdi:battery-arrow-up",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=helpers.charge_voltage_limit,
    ),
    FelicitySensorDescription(
        key="discharge_voltage_limit",
        translation_key="discharge_voltage_limit",
        icon="mdi:battery-arrow-down",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=helpers.discharge_voltage_limit,
    ),
    FelicitySensorDescription(
        key="charge_current_limit",
        translation_key="charge_current_limit",
        icon="mdi:battery-arrow-up",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=helpers.charge_current_limit,
    ),
    FelicitySensorDescription(
        key="discharge_current_limit",
        translation_key="discharge_current_limit",
        icon="mdi:battery-arrow-down",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=helpers.discharge_current_limit,
    ),
    FelicitySensorDescription(
        key="last_update",
        translation_key="last_update",
        icon="mdi:clock-check-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=helpers.timestamp,
    ),
)


def _cell_voltage_descriptions() -> tuple[FelicitySensorDescription, ...]:
    """One diagnostic sensor per cell voltage."""
    return tuple(
        FelicitySensorDescription(
            key=f"cell_voltage_{i}",
            name=f"Cell {i} voltage",
            icon="mdi:battery",
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            device_class=SensorDeviceClass.VOLTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=3,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            value_fn=(lambda d, n=i: helpers.cell_voltage(d, n)),
        )
        for i in range(1, CELL_COUNT + 1)
    )


def _cell_temperature_descriptions() -> tuple[FelicitySensorDescription, ...]:
    """One diagnostic sensor per temperature probe."""
    return tuple(
        FelicitySensorDescription(
            key=f"cell_temperature_{i}",
            name=f"Cell temperature {i}",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            value_fn=(lambda d, n=i: helpers.cell_temperature(d, n)),
        )
        for i in range(1, TEMP_SENSOR_COUNT + 1)
    )


@dataclass(frozen=True, kw_only=True)
class FelicityDailyEnergyDescription(SensorEntityDescription):
    """Describe a daily charge/discharge energy sensor."""

    power_fn: Callable[[dict[str, Any]], StateType]


DAILY_ENERGY_DESCRIPTIONS: tuple[FelicityDailyEnergyDescription, ...] = (
    FelicityDailyEnergyDescription(
        key="daily_charge_energy",
        translation_key="daily_charge_energy",
        icon="mdi:battery-plus",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        power_fn=helpers.charge_power,
    ),
    FelicityDailyEnergyDescription(
        key="daily_discharge_energy",
        translation_key="daily_discharge_energy",
        icon="mdi:battery-minus",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        power_fn=helpers.discharge_power,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FelicityConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Felicity Battery sensors."""
    coordinator = entry.runtime_data

    entities: list[SensorEntity] = [
        FelicityBatterySensor(coordinator, desc)
        for desc in (
            *SENSOR_DESCRIPTIONS,
            *_cell_voltage_descriptions(),
            *_cell_temperature_descriptions(),
        )
    ]
    entities.extend(
        FelicityDailyEnergySensor(coordinator, desc)
        for desc in DAILY_ENERGY_DESCRIPTIONS
    )
    async_add_entities(entities)


class FelicityBatterySensor(FelicityBatteryEntity, SensorEntity):
    """A stateless sensor backed by a pure helper function."""

    entity_description: FelicitySensorDescription

    def __init__(
        self,
        coordinator: FelicityBatteryCoordinator,
        description: FelicitySensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_sn}_{description.key}"

    @property
    def native_value(self) -> StateType | datetime:
        """Return the sensor value."""
        data = self.coordinator.data
        if data is None:
            return None
        return self.entity_description.value_fn(data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes for sensors that provide them."""
        data = self.coordinator.data
        if data is None or self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(data)


class FelicityDailyEnergySensor(FelicityBatteryEntity, RestoreEntity, SensorEntity):
    """Daily charge/discharge energy, integrated from live power.

    The FSolar cloud does not expose per-day counters for this battery, so we
    integrate power over time (trapezoidal) and reset at local midnight. The
    integration math lives in ``helpers.integrate_energy_kwh`` and is unit-
    tested; this class only owns the HA state/restore plumbing.
    """

    entity_description: FelicityDailyEnergyDescription

    def __init__(
        self,
        coordinator: FelicityBatteryCoordinator,
        description: FelicityDailyEnergyDescription,
    ) -> None:
        """Initialize the daily energy sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_sn}_{description.key}"
        self._energy = 0.0
        self._last_power = 0.0
        self._last_ts = None
        self._last_reset_date = dt_util.now().date().isoformat()

    async def async_added_to_hass(self) -> None:
        """Restore the accumulated value across restarts."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state not in (None, "unknown", "unavailable"):
            try:
                self._energy = float(last.state)
            except (ValueError, TypeError):
                self._energy = 0.0
            attrs = last.attributes or {}
            self._last_reset_date = attrs.get("last_reset_date", self._last_reset_date)
            try:
                self._last_power = float(attrs.get("last_power", 0) or 0)
            except (ValueError, TypeError):
                self._last_power = 0.0

        # If the stored value is from a previous day, start fresh.
        today = dt_util.now().date().isoformat()
        if self._last_reset_date != today:
            self._energy = 0.0
            self._last_reset_date = today
            self._last_power = 0.0
        self._last_ts = None
        self._attr_native_value = round(self._energy, 3)

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        if data is not None:
            self._accumulate(data)
        super()._handle_coordinator_update()

    def _accumulate(self, data: dict[str, Any]) -> None:
        now = dt_util.now()
        today = now.date().isoformat()
        if self._last_reset_date != today:
            self._energy = 0.0
            self._last_reset_date = today
            self._last_power = 0.0
            self._last_ts = now

        power = self.entity_description.power_fn(data) or 0.0
        if self._last_ts is not None:
            elapsed = (now - self._last_ts).total_seconds()
            self._energy = helpers.integrate_energy_kwh(
                self._energy, self._last_power, float(power), elapsed
            )
        self._last_power = float(power)
        self._last_ts = now
        self._attr_native_value = round(self._energy, 3)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Persist reset date and last power so restarts continue cleanly."""
        return {
            "last_reset_date": self._last_reset_date,
            "last_power": round(self._last_power, 1),
        }
