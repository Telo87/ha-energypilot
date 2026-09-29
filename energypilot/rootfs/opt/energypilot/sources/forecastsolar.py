"""Forecast.Solar (free public API: 12 calls per hour and IP, today + tomorrow)."""

from __future__ import annotations

from datetime import datetime

import aiohttp

from . import SourceError, get_json

URL = "https://api.forecast.solar/estimate/watthours/period/{lat:.4f}/{lon:.4f}/{dec:g}/{az:g}/{kwp:g}"


def parse(data: dict) -> dict[int, float]:
    """Hour start -> Wh. Each value is the energy of the period *ending* at its time."""
    result = data.get("result")
    if not isinstance(result, dict):
        raise SourceError((data.get("message") or {}).get("text") or "ungültige Antwort")
    hours: dict[int, float] = {}
    for stamp, wh in result.items():
        end = int(datetime.fromisoformat(stamp).timestamp())
        hour = (end - 1) // 3600 * 3600
        hours[hour] = hours.get(hour, 0.0) + float(wh or 0)
    return hours


async def fetch(
    session: aiohttp.ClientSession, lat: float, lon: float, tilt: float, azimuth: float, kwp: float
) -> dict[int, float]:
    # Forecast.Solar: 0 = south, -90 = east, 90 = west
    az = round(((azimuth - 180 + 180) % 360) - 180)
    url = URL.format(lat=lat, lon=lon, dec=round(tilt), az=az, kwp=round(kwp, 2))
    return parse(await get_json(session, url, {"time": "iso8601"}))
