"""Sensor platform for SMHI integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONF_LATITUDE,
    CONF_LOCATION,
    CONF_LONGITUDE,
    PERCENTAGE,
    UnitOfSpeed,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import SMHIConfigEntry, SMHIDataUpdateCoordinator
from .entity import SmhiEntity

PARALLEL_UPDATES = 0

FWI_INDEX_MAP = {
    "1": "very_low",
    "2": "low",
    "3": "moderate",
    "4": "high",
    "5": "very_high",
    "6": "extreme",
}
GRASSFIRE_MAP = {
    "1": "snow_cover",
    "2": "season_over",
    "3": "low",
    "4": "moderate",
    "5": "high",
    "6": "very_high",
}
FORESTDRY_MAP = {
    "1": "very_wet",
    "2": "wet",
    "3": "moderate_wet",
    "4": "dry",
    "5": "very_dry",
    "6": "extremely_dry",
}


def _octas_to_pct(value: float | None) -> int | None:
    """Convert cloud cover from octas (0-8) to percentage."""
    if value is None:
        return None
    return round(value * 100 / 8)


def _frozen_precip(value: float | None) -> int | None:
    """Convert frozen precipitation fraction to percentage."""
    if value is None or value < 0:
        return None
    return round(value * 100)


def _fire_index(entity: SMHISensor, key: str) -> str:
    """Return fire index value as string."""
    value = entity.coordinator.fire_current.get(key)
    if value is not None and value > 0:
        return str(int(value))
    return "0"


@dataclass(frozen=True, kw_only=True)
class SMHISensorDescription(SensorEntityDescription):
    """Describes SMHI sensor entity."""

    value_fn: Callable[[SMHISensor], StateType | datetime]


WEATHER_SENSOR_DESCRIPTIONS: tuple[SMHISensorDescription, ...] = (
    SMHISensorDescription(
        key="thunder",
        translation_key="thunder",
        value_fn=lambda e: e.coordinator.current.get("thunderstorm_probability"),
        native_unit_of_measurement=PERCENTAGE,
    ),
    SMHISensorDescription(
        key="total_cloud",
        translation_key="total_cloud",
        value_fn=lambda e: _octas_to_pct(
            e.coordinator.current.get("cloud_area_fraction")
        ),
        native_unit_of_measurement=PERCENTAGE,
        entity_registry_enabled_default=True,
    ),
    SMHISensorDescription(
        key="low_cloud",
        translation_key="low_cloud",
        value_fn=lambda e: _octas_to_pct(
            e.coordinator.current.get("low_type_cloud_area_fraction")
        ),
        native_unit_of_measurement=PERCENTAGE,
        entity_registry_enabled_default=True,
    ),
    SMHISensorDescription(
        key="medium_cloud",
        translation_key="medium_cloud",
        value_fn=lambda e: _octas_to_pct(
            e.coordinator.current.get("medium_type_cloud_area_fraction")
        ),
        native_unit_of_measurement=PERCENTAGE,
        entity_registry_enabled_default=True,
    ),
    SMHISensorDescription(
        key="high_cloud",
        translation_key="high_cloud",
        value_fn=lambda e: _octas_to_pct(
            e.coordinator.current.get("high_type_cloud_area_fraction")
        ),
        native_unit_of_measurement=PERCENTAGE,
        entity_registry_enabled_default=True,
    ),
    SMHISensorDescription(
        key="precipitation_category",
        translation_key="precipitation_category",
        value_fn=lambda e: str(
            int(
                e.coordinator.current.get(
                    "predominant_precipitation_type_at_surface", 0
                )
            )
        ),
        device_class=SensorDeviceClass.ENUM,
        options=["0", "1", "2", "3", "4", "5", "6"],
    ),
    SMHISensorDescription(
        key="frozen_precipitation",
        translation_key="frozen_precipitation",
        value_fn=lambda e: _frozen_precip(
            e.coordinator.current.get("precipitation_frozen_part")
        ),
        native_unit_of_measurement=PERCENTAGE,
    ),
)

FIRE_SENSOR_DESCRIPTIONS: tuple[SMHISensorDescription, ...] = (
    SMHISensorDescription(
        key="fwiindex",
        translation_key="fwiindex",
        value_fn=lambda e: FWI_INDEX_MAP.get(_fire_index(e, "fwiindex")),
        device_class=SensorDeviceClass.ENUM,
        options=[*FWI_INDEX_MAP.values()],
        entity_registry_enabled_default=True,
    ),
    SMHISensorDescription(
        key="fire_weather_index",
        translation_key="fire_weather_index",
        value_fn=lambda e: e.coordinator.fire_current.get("fwi"),
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
    ),
    SMHISensorDescription(
        key="initial_spread_index",
        translation_key="initial_spread_index",
        value_fn=lambda e: e.coordinator.fire_current.get("isi"),
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
    ),
    SMHISensorDescription(
        key="build_up_index",
        translation_key="build_up_index",
        value_fn=lambda e: e.coordinator.fire_current.get(
            "bui"  # codespell:ignore bui
        ),
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
    ),
    SMHISensorDescription(
        key="fine_fuel_moisture_code",
        translation_key="fine_fuel_moisture_code",
        value_fn=lambda e: e.coordinator.fire_current.get("ffmc"),
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
    ),
    SMHISensorDescription(
        key="duff_moisture_code",
        translation_key="duff_moisture_code",
        value_fn=lambda e: e.coordinator.fire_current.get("dmc"),
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
    ),
    SMHISensorDescription(
        key="drought_code",
        translation_key="drought_code",
        value_fn=lambda e: e.coordinator.fire_current.get("dc"),
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
    ),
    SMHISensorDescription(
        key="grassfire",
        translation_key="grassfire",
        value_fn=lambda e: GRASSFIRE_MAP.get(_fire_index(e, "grassfire")),
        device_class=SensorDeviceClass.ENUM,
        options=[*GRASSFIRE_MAP.values()],
        entity_registry_enabled_default=True,
    ),
    SMHISensorDescription(
        key="rate_of_spread",
        translation_key="rate_of_spread",
        value_fn=lambda e: e.coordinator.fire_current.get("rn"),
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_MINUTE,
        entity_registry_enabled_default=True,
    ),
    SMHISensorDescription(
        key="forestdry",
        translation_key="forestdry",
        value_fn=lambda e: FORESTDRY_MAP.get(_fire_index(e, "forestdry")),
        device_class=SensorDeviceClass.ENUM,
        options=[*FORESTDRY_MAP.values()],
        entity_registry_enabled_default=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SMHIConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up SMHI sensor platform."""
    coordinator = entry.runtime_data
    location = entry.data
    lat = location[CONF_LOCATION][CONF_LATITUDE]
    lon = location[CONF_LOCATION][CONF_LONGITUDE]

    entities: list[SMHISensor] = [
        SMHISensor(lat, lon, coordinator=coordinator, entity_description=desc)
        for desc in (*WEATHER_SENSOR_DESCRIPTIONS, *FIRE_SENSOR_DESCRIPTIONS)
    ]
    async_add_entities(entities)


class SMHISensor(SmhiEntity, SensorEntity):
    """Representation of a SMHI Sensor."""

    entity_description: SMHISensorDescription

    def __init__(
        self,
        latitude: str,
        longitude: str,
        coordinator: SMHIDataUpdateCoordinator,
        entity_description: SMHISensorDescription,
    ) -> None:
        """Initiate SMHI Sensor."""
        self.entity_description = entity_description
        super().__init__(latitude, longitude, coordinator)
        lat = round(float(latitude), 6)
        lon = round(float(longitude), 6)
        self._attr_unique_id = f"{lat}, {lon}-{entity_description.key}"

    def update_entity_data(self) -> None:
        """Refresh the entity data."""
        self._attr_native_value = self.entity_description.value_fn(self)
