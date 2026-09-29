"""Solcast rooftop sites (free hobbyist account: API key + up to 2 sites, 10 calls/day)."""

from __future__ import annotations

import re
from datetime import datetime

import aiohttp

from . import SourceError, get_json

URL = "https://api.solcast.com.au/rooftop_sites/{rid}/forecasts"


def _minutes(period: str) -> float:
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?", period or "PT30M")
    return (int(m.group(1) or 0) * 60 + int(m.group(2) or 0)) if m else 30.0


def parse(data: dict) -> dict[int, float]:
    rows = data.get("forecasts")
    if not isinstance(rows, list):
        raise SourceError("ungültige Antwort")
    hours: dict[int, float] = {}
    for r in rows:
        minutes = _minutes(r.get("period"))
        end = int(datetime.fromisoformat(str(r["period_end"])).timestamp())
        hour = (end - int(minutes * 60)) // 3600 * 3600
        hours[hour] = hours.get(hour, 0.0) + float(r.get("pv_estimate") or 0) * 1000 * minutes / 60
    return hours


async def fetch(session: aiohttp.ClientSession, key: str, resource_id: str) -> dict[int, float]:
    return parse(
        await get_json(
            session,
            URL.format(rid=resource_id),
            {"format": "json", "hours": "72"},
            {"Authorization": f"Bearer {key}"},
        )
    )
