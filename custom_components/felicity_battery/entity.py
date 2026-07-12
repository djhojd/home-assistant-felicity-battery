"""Base entity for the Felicity FLA48300 integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_MODEL, DOMAIN, MANUFACTURER
from .coordinator import FelicityBatteryCoordinator


class FelicityBatteryEntity(CoordinatorEntity[FelicityBatteryCoordinator]):
    """Common device info and coordinator wiring for all entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FelicityBatteryCoordinator) -> None:
        """Initialize the base entity."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_sn)},
            manufacturer=MANUFACTURER,
            model=coordinator.device_model or DEVICE_MODEL,
            name=coordinator.device_alias or f"Felicity {coordinator.device_sn}",
            serial_number=coordinator.device_sn,
            sw_version=coordinator.device_sw_version,
        )
