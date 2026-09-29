"""Day-ahead spot prices (EPEX) – Energy-Charts (Fraunhofer ISE), aWATTar as fallback.

Since October 2025 the day-ahead market trades 15-minute products; both
sources are stored with their own period length.
"""

from __future__ import annotations

import aiohttp

from . import SourceError, get_json

ENERGY_CHARTS = "https://api.energy-charts.info/price"
AWATTAR = {"DE-LU": "https://api.awattar.de/v1/marketdata", "AT": "https://api.awattar.at/v1/marketdata"}


def parse_energy_charts(data: dict) -> list[tuple[int, int, float]]:
    ts = data.get("unix_seconds") or []
    prices = data.get("price") or []
    out = []
    for i, (t, p) in enumerate(zip(ts, prices, strict=False)):
        if p is None:
            continue
        dur = (ts[i + 1] - t) if i + 1 < len(ts) else (t - ts[i - 1] if i else 3600)
        out.append((int(t), int(dur), float(p)))
    return out


def parse_awattar(data: dict) -> list[tuple[int, int, float]]:
    return [
        (int(r["start_timestamp"] // 1000), int((r["end_timestamp"] - r["start_timestamp"]) // 1000), float(r["marketprice"]))
        for r in data.get("data") or []
    ]


async def fetch(
    session: aiohttp.ClientSession, zone: str, start: int, end: int, start_day: str, end_day: str
) -> list[tuple[int, int, float]]:
    """(start, seconds, EUR/MWh) – tries Energy-Charts first."""
    errors = []
    try:
        data = await get_json(session, ENERGY_CHARTS, {"bzn": zone, "start": start_day, "end": end_day})
        rows = parse_energy_charts(data)
        if rows:
            return rows
        errors.append("Energy-Charts: keine Daten")
    except SourceError as err:
        errors.append(f"Energy-Charts: {err}")
    if zone in AWATTAR:
        try:
            data = await get_json(session, AWATTAR[zone], {"start": start * 1000, "end": end * 1000})
            rows = parse_awattar(data)
            if rows:
                return rows
        except SourceError as err:
            errors.append(f"aWATTar: {err}")
    raise SourceError("; ".join(errors))


def end_price(spot_eur_mwh: float, tariff: dict) -> float:
    """Consumer price in ct/kWh: (spot + net surcharge) plus VAT."""
    return (spot_eur_mwh / 10 + float(tariff.get("markup_ct", 0))) * (1 + float(tariff.get("vat", 0)) / 100)
