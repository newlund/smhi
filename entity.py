"""Support for the Swedish weather institute weather  base entities."""

from __future__ import annotations

from abc import abstractmethod

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SMHIDataUpdateCoordinator


class SmhiWeatherBaseEntity(Entity):
    """Representation of a base weather entity."""

    _attr_attribution = "Swedish weather institute (SMHI)"
    _attr_has_entity_name = True

    def __init__(
        self,
        latitude: str,
        longitude: str,
    ) -> None:
        """Initialize the SMHI base weather entity."""
        lat = round(float(latitude), 6)
        lon = round(float(longitude), 6)
        self._attr_unique_id = f"{lat}, {lon}"
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, f"{lat}, {lon}")},
            manufacturer="SMHI",
            model="snow1g/v1",
            configuration_url="https://opendata.smhi.se/metfcst/snow1gv1/introduction",
        )

    @abstractmethod
    def update_entity_data(self) -> None:
        """Refresh the entity data."""


class SmhiEntity(
    CoordinatorEntity[SMHIDataUpdateCoordinator], SmhiWeatherBaseEntity
):
    """Representation of an entity using the single SMHI coordinator."""

    def __init__(
        self,
        latitude: str,
        longitude: str,
        coordinator: SMHIDataUpdateCoordinator,
    ) -> None:
        """Initialize the SMHI entity."""
        super().__init__(coordinator)
        SmhiWeatherBaseEntity.__init__(self, latitude, longitude)
        if coordinator.data:
            self.update_entity_data()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.update_entity_data()
        super()._handle_coordinator_update()
