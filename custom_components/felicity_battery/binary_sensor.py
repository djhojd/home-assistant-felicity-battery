"""Binary sensor platform for the Felicity FLA48300 battery."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FelicityConfigEntry, helpers
from .coordinator import FelicityBatteryCoordinator
from .entity import FelicityBatteryEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class FelicityBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a Felicity binary sensor."""

    value_fn: Callable[[dict[str, Any]], bool | None]


BINARY_SENSOR_DESCRIPTIONS: tuple[FelicityBinarySensorDescription, ...] = (
    FelicityBinarySensorDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=helpers.is_charging,
    ),
    FelicityBinarySensorDescription(
        key="discharging",
        translation_key="discharging",
        icon="mdi:battery-arrow-down",
        value_fn=helpers.is_discharging,
    ),
    FelicityBinarySensorDescription(
        key="heating",
        translation_key="heating",
        icon="mdi:radiator",
        device_class=BinarySensorDeviceClass.HEAT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=helpers.is_heating,
    ),
    FelicityBinarySensorDescription(
        key="problem",
        translation_key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=helpers.is_problem,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FelicityConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Felicity Battery binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        FelicityBatteryBinarySensor(coordinator, desc)
        for desc in BINARY_SENSOR_DESCRIPTIONS
    )


class FelicityBatteryBinarySensor(FelicityBatteryEntity, BinarySensorEntity):
    """A binary sensor backed by a pure helper function."""

    entity_description: FelicityBinarySensorDescription

    def __init__(
        self,
        coordinator: FelicityBatteryCoordinator,
        description: FelicityBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_sn}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return the binary sensor state."""
        data = self.coordinator.data
        if data is None:
            return None
        return self.entity_description.value_fn(data)
