"""DataUpdateCoordinator for the SMHI integration."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LOCATION, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, LOGGER, TIMEOUT

type SMHIConfigEntry = ConfigEntry[SMHIDataUpdateCoordinator]

WEATHER_BASE_URL = (
    "https://opendata-download-metfcst.smhi.se/api/category/snow1g/version/1"
)
FIRE_BASE_URL = (
    "https://opendata-download-metfcst.smhi.se/api/category/fwif1g/version/1"
)


def _round_coords(config_entry: ConfigEntry) -> tuple[float, float]:
    """Return rounded (lon, lat) from config entry."""
    lon = round(float(config_entry.data[CONF_LOCATION][CONF_LONGITUDE]), 6)
    lat = round(float(config_entry.data[CONF_LOCATION][CONF_LATITUDE]), 6)
    return lon, lat


def _parse_weather_timeseries(data: dict) -> list[dict]:
    """Parse weather API response into forecast list."""
    forecasts: list[dict] = []
    for ts in data.get("timeSeries", []):
        entry = dict(ts.get("data", {}))
        entry["valid_time"] = datetime.fromisoformat(ts["time"])
        forecasts.append(entry)
    return forecasts


def _aggregate_daily(hourly: list[dict]) -> list[dict]:
    """Aggregate hourly forecasts into one entry per day (noon or first)."""
    by_date: dict[str, list[dict]] = defaultdict(list)
    for entry in hourly:
        by_date[entry["valid_time"].date().isoformat()].append(entry)

    daily: list[dict] = []
    for entries in by_date.values():
        noon = next((e for e in entries if e["valid_time"].hour == 12), entries[0])
        daily.append(noon)
    return daily


def _parse_fire_timeseries(data: dict) -> list[dict]:
    """Parse fire API response into forecast list."""
    forecasts: list[dict] = []
    for ts in data.get("timeSeries", []):
        entry: dict = {
            "valid_time": datetime.fromisoformat(ts["validTime"]),
        }
        for param in ts.get("parameters", []):
            entry[param["name"]] = param["values"][0]
        forecasts.append(entry)
    return forecasts


async def _fetch_json(session: aiohttp.ClientSession, url: str) -> dict:
    """Fetch JSON from URL."""
    async with session.get(url) as resp:
        if resp.status != 200:
            raise UpdateFailed(f"SMHI API returned {resp.status} for {url}")
        return await resp.json()


@dataclass
class SMHIForecastData:
    """Dataclass for SMHI weather data."""

    daily: list[dict]
    hourly: list[dict]


@dataclass
class SMHIFireForecastData:
    """Dataclass for SMHI fire data."""

    fire_daily: list[dict]
    fire_hourly: list[dict]


@dataclass
class SMHIAllData:
    """Combined data from all SMHI APIs."""

    weather: SMHIForecastData
    fire: SMHIFireForecastData


class SMHIDataUpdateCoordinator(DataUpdateCoordinator[SMHIAllData]):
    """A single coordinator for all SMHI data."""

    config_entry: SMHIConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: SMHIConfigEntry) -> None:
        """Initialize the SMHI coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        lon, lat = _round_coords(config_entry)
        self._weather_url = (
            f"{WEATHER_BASE_URL}/geotype/point/lon/{lon}/lat/{lat}/data.json"
        )
        self._fire_daily_url = (
            f"{FIRE_BASE_URL}/daily/geotype/point/lon/{lon}/lat/{lat}/data.json"
        )
        self._fire_hourly_url = (
            f"{FIRE_BASE_URL}/hourly/geotype/point/lon/{lon}/lat/{lat}/data.json"
        )
        self._session = aiohttp_client.async_get_clientsession(hass)

    async def _async_update_data(self) -> SMHIAllData:
        """Fetch data from SMHI.

        Weather data is required; fire data fails gracefully.
        """
        async with asyncio.timeout(TIMEOUT):
            weather_raw = await _fetch_json(self._session, self._weather_url)

        # Fire data is optional — don't block weather updates if it fails
        fire_daily: list[dict] = []
        fire_hourly: list[dict] = []
        try:
            async with asyncio.timeout(TIMEOUT):
                fire_daily_raw, fire_hourly_raw = await asyncio.gather(
                    _fetch_json(self._session, self._fire_daily_url),
                    _fetch_json(self._session, self._fire_hourly_url),
                )
            fire_daily = _parse_fire_timeseries(fire_daily_raw)
            fire_hourly = _parse_fire_timeseries(fire_hourly_raw)
        except Exception:  # noqa: BLE001
            LOGGER.debug("Failed to fetch fire data, skipping")
            if self.data:
                fire_daily = self.data.fire.fire_daily
                fire_hourly = self.data.fire.fire_hourly

        hourly = _parse_weather_timeseries(weather_raw)
        return SMHIAllData(
            weather=SMHIForecastData(
                daily=_aggregate_daily(hourly),
                hourly=hourly,
            ),
            fire=SMHIFireForecastData(
                fire_daily=fire_daily,
                fire_hourly=fire_hourly,
            ),
        )

    @property
    def current(self) -> dict:
        """Return the current weather metrics."""
        return self.data.weather.hourly[0]

    @property
    def fire_current(self) -> dict:
        """Return the current fire metrics."""
        if self.data.fire.fire_daily:
            return self.data.fire.fire_daily[0]
        return {}
