"""DataUpdateCoordinator for the SMHI integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LOCATION, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, LOGGER, TIMEOUT

type SMHIConfigEntry = ConfigEntry[
    tuple[SMHIDataUpdateCoordinator, SMHIFireDataUpdateCoordinator]
]

WEATHER_BASE_URL = (
    "https://opendata-download-metfcst.smhi.se/api/category/snow1g/version/1"
)
FIRE_BASE_URL = (
    "https://opendata-download-metfcst.smhi.se/api/category/fwif1g/version/1"
)

SMHIForecast = dict
SMHIFireForecast = dict


def _parse_weather_timeseries(data: dict) -> list[SMHIForecast]:
    """Parse weather API response into forecast list."""
    forecasts: list[SMHIForecast] = []
    for ts in data.get("timeSeries", []):
        entry = dict(ts.get("data", {}))
        entry["valid_time"] = datetime.fromisoformat(ts["time"])
        if start := ts.get("intervalParametersStartTime"):
            entry["interval_start"] = datetime.fromisoformat(start)
        forecasts.append(entry)
    return forecasts


def _parse_fire_timeseries(data: dict) -> list[SMHIFireForecast]:
    """Parse fire API response into forecast list."""
    forecasts: list[SMHIFireForecast] = []
    for ts in data.get("timeSeries", []):
        entry: SMHIFireForecast = {
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
    """Dataclass for SMHI data."""

    daily: list[SMHIForecast]
    hourly: list[SMHIForecast]


@dataclass
class SMHIFireForecastData:
    """Dataclass for SMHI fire data."""

    fire_daily: list[SMHIFireForecast]
    fire_hourly: list[SMHIFireForecast]


class SMHIDataUpdateCoordinator(DataUpdateCoordinator[SMHIForecastData]):
    """A SMHI Data Update Coordinator."""

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
        lon = config_entry.data[CONF_LOCATION][CONF_LONGITUDE]
        lat = config_entry.data[CONF_LOCATION][CONF_LATITUDE]
        self._url = (
            f"{WEATHER_BASE_URL}/geotype/point/lon/{lon}/lat/{lat}/data.json"
        )
        self._session = aiohttp_client.async_get_clientsession(hass)

    async def _async_update_data(self) -> SMHIForecastData:
        """Fetch data from SMHI."""
        try:
            async with asyncio.timeout(TIMEOUT):
                data = await _fetch_json(self._session, self._url)
        except (aiohttp.ClientError, TimeoutError) as ex:
            raise UpdateFailed(
                "Failed to retrieve the forecast from the SMHI API"
            ) from ex

        forecasts = _parse_weather_timeseries(data)
        return SMHIForecastData(daily=forecasts, hourly=forecasts)

    @property
    def current(self) -> SMHIForecast:
        """Return the current metrics."""
        return self.data.daily[0]


class SMHIFireDataUpdateCoordinator(DataUpdateCoordinator[SMHIFireForecastData]):
    """A SMHI Fire Data Update Coordinator."""

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
        lon = config_entry.data[CONF_LOCATION][CONF_LONGITUDE]
        lat = config_entry.data[CONF_LOCATION][CONF_LATITUDE]
        base = f"{FIRE_BASE_URL}/{{freq}}/geotype/point/lon/{lon}/lat/{lat}/data.json"
        self._daily_url = base.format(freq="daily")
        self._hourly_url = base.format(freq="hourly")
        self._session = aiohttp_client.async_get_clientsession(hass)

    async def _async_update_data(self) -> SMHIFireForecastData:
        """Fetch data from SMHI."""
        try:
            async with asyncio.timeout(TIMEOUT):
                daily_data, hourly_data = await asyncio.gather(
                    _fetch_json(self._session, self._daily_url),
                    _fetch_json(self._session, self._hourly_url),
                )
        except (aiohttp.ClientError, TimeoutError) as ex:
            raise UpdateFailed(
                "Failed to retrieve the forecast from the SMHI API"
            ) from ex

        return SMHIFireForecastData(
            fire_daily=_parse_fire_timeseries(daily_data),
            fire_hourly=_parse_fire_timeseries(hourly_data),
        )

    @property
    def fire_current(self) -> SMHIFireForecast:
        """Return the current fire metrics."""
        return self.data.fire_daily[0]
