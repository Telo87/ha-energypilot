"""Open-Meteo weather models (free, no key).

Radiation values at time T are means over the *preceding* hour, so the hour
[T-1h, T) is stored with start T-1h. Three endpoints are used:

- forecast API: live forecasts (collected every hour)
- historical forecast API: archived short-term forecasts (≈ ``d0``)
- previous runs API: archived forecasts from the run one day earlier (≈ ``d1``)
"""

from __future__ import annotations

from dataclasses import dataclass

import aiohttp

from . import SourceError, get_json

FORECAST = "https://api.open-meteo.com/v1/forecast"
HISTORICAL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
PREVIOUS = "https://previous-runs-api.open-meteo.com/v1/forecast"
VARS = ("shortwave_radiation", "diffuse_radiation", "temperature_2m", "cloud_cover", "wind_speed_10m")


@dataclass
class WeatherHour:
    start: int
    ghi: float
    dhi: float | None
    temp: float | None
    cloud: float | None
    wind: float | None


def parse(data: dict, suffix: str = "") -> list[WeatherHour]:
    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    cols = [hourly.get(v + suffix) or [None] * len(times) for v in VARS]
    out = []
    for i, t in enumerate(times):
        ghi, dhi, temp, cloud, wind = (c[i] if i < len(c) else None for c in cols)
        if ghi is None:  # beyond the model's range
            continue
        out.append(WeatherHour(int(t) - 3600, float(ghi), dhi, temp, cloud, wind))
    return out


def _params(lat: float, lon: float, model: str, variables: list[str]) -> dict:
    return {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "hourly": ",".join(variables),
        "models": model,
        "timezone": "UTC",
        "timeformat": "unixtime",
    }


async def forecast(
    session: aiohttp.ClientSession, lat: float, lon: float, model: str, days: int = 3
) -> list[WeatherHour]:
    params = _params(lat, lon, model, list(VARS))
    params.update(forecast_days=str(days), past_days="1")
    data = await get_json(session, FORECAST, params)
    if data.get("error"):
        raise SourceError(data.get("reason", "Fehler"))
    return parse(data)


async def archive(
    session: aiohttp.ClientSession, lat: float, lon: float, model: str, start: str, end: str, day1: bool
) -> list[WeatherHour]:
    """Archived forecasts between two dates (YYYY-MM-DD, inclusive)."""
    suffix = "_previous_day1" if day1 else ""
    params = _params(lat, lon, model, [v + suffix for v in VARS])
    params.update(start_date=start, end_date=end)
    data = await get_json(session, PREVIOUS if day1 else HISTORICAL, params)
    if data.get("error"):
        raise SourceError(data.get("reason", "Fehler"))
    return parse(data, suffix)
