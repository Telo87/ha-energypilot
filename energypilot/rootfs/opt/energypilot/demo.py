"""Demo mode (ENERGYPILOT_DEMO=1): synthetic data for UI development, no network."""

from __future__ import annotations

import asyncio
import math
import random
import time

from .solar import clearsky_hour

LAT, LON = 51.0, 10.0  # centre of Germany
DAYS_BACK = 75
# source: (bias, hourly noise d0, extra noise d1)
SOURCES = {
    "om:best_match": (0.02, 0.16, 0.10),
    "om:icon_d2": (-0.03, 0.12, 0.08),
    "om:icon_eu": (0.04, 0.17, 0.10),
    "om:ecmwf_ifs025": (0.06, 0.19, 0.08),
    "om:gfs_seamless": (0.12, 0.27, 0.12),
    "om:meteofrance_seamless": (-0.07, 0.21, 0.10),
    "fs": (0.15, 0.25, 0.10),
}
LIVE_SOURCES = {"fs"}  # only collected live: starts 10 days ago


def demo_entities(hub=None) -> list[dict]:
    rows = [
        ("sensor.wechselrichter_1_ac_leistung", "Wechselrichter 1 AC-Leistung", "W", "power"),
        ("sensor.wechselrichter_2_ac_leistung", "Wechselrichter 2 AC-Leistung", "W", "power"),
        ("sensor.wechselrichter_2_energie_gesamt", "Wechselrichter 2 Energie gesamt", "kWh", "energy"),
        ("sensor.hausverbrauch", "Hausverbrauch", "W", "power"),
        ("sensor.netzleistung", "Netzleistung", "W", "power"),
        ("sensor.batterie_ladezustand", "Batterie Ladezustand", "%", "percent"),
        ("sensor.batterie_leistung", "Batterie Leistung", "W", "power"),
    ]
    live = {v["entity"]: v["value"] for v in ((hub.live if hub else {}).get("values") or {}).values()}
    return [
        {"entity_id": e, "name": n, "unit": u, "kind": k, "state": str(live.get(e, 0)), "statistics": True}
        for e, n, u, k in rows
    ]


def _cloud_series(start: int, hours: int, rnd: random.Random) -> list[float]:
    """Clear-sky fraction per hour: day weather regimes + passing clouds."""
    out = []
    day_level = 0.7
    for i in range(hours):
        if i % 24 == 0:
            day_level = rnd.choice([0.95, 0.9, 0.8, 0.6, 0.45, 0.3, 0.15])
        wobble = 0.25 * math.sin(i / 3.1 + rnd.random()) * (1 - day_level)
        out.append(max(0.05, min(1.0, day_level + wobble + rnd.gauss(0, 0.07))))
    return out


def populate(hub) -> None:
    settings, db = hub.settings, hub.db
    if not settings.arrays:
        settings.upsert_array({"name": "Hausdach Süd", "planes": [{"kwp": 6.5, "tilt": 35, "azimuth": 185}],
                               "sensor": "sensor.wechselrichter_1_ac_leistung"})
        settings.upsert_array({"name": "Garage Ost-West", "sensor": "sensor.wechselrichter_2_ac_leistung",
                               "planes": [{"kwp": 2.6, "tilt": 15, "azimuth": 95},
                                          {"kwp": 2.6, "tilt": 15, "azimuth": 275}]})
        settings.update({"sensors": {"house": "sensor.hausverbrauch", "grid": "sensor.netzleistung",
                                     "battery_soc": "sensor.batterie_ladezustand",
                                     "battery_power": "sensor.batterie_leistung"},
                         "tariff": {"markup_ct": 18.5, "vat": 19, "feed_in_ct": 7.9}})
    hub.ha_location = (LAT, LON)
    from .config import to_array

    arrays = [(c, to_array(c)) for c in settings.arrays if c["kwp"] > 0]
    now = int(time.time())
    today = hub.midnight(now)
    start = today - DAYS_BACK * 86400
    end = today + 2 * 86400
    hours = (end - start) // 3600
    rnd = random.Random(42)
    cloud = _cloud_series(start, hours, rnd)

    actual, fc = [], []
    for i in range(hours):
        t = start + i * 3600
        for cfg, arr in arrays:
            clear = clearsky_hour(t, arr, LAT, LON)
            truth = clear * cloud[i]
            if t + 3600 <= now:
                actual.append((cfg["id"], t, round(truth * rnd.uniform(0.97, 1.02), 1)))
            for src, (bias, noise, extra) in SOURCES.items():
                if src in LIVE_SOURCES and t < today - 10 * 86400:
                    continue
                for hz, n in (("d0", noise), ("d1", noise + extra)):
                    if clear <= 0:
                        wh = 0.0
                    else:
                        wh = min(clear * 1.05, max(0.0, truth * (1 + bias) + clear * rnd.gauss(0, n) * 0.6))
                    fc.append((src, cfg["id"], t, hz, round(wh, 1), 0))
        house = 350 + 250 * math.sin((t % 86400) / 86400 * 2 * math.pi - 2) ** 2 + rnd.uniform(0, 400)
        if t + 3600 <= now:
            actual.append(("house", t, round(house, 1)))
    db.put_actual(actual)
    db.put_forecast(fc)

    prices = []
    for q in range((end - start) // 900):
        t = start + q * 900
        h = ((t + 3600) % 86400) / 3600
        base = 95 + 45 * math.cos((h - 19) / 24 * 2 * math.pi) - 70 * math.exp(-((h - 13) ** 2) / 8)
        prices.append((t, 900, round(base + rnd.gauss(0, 8), 2)))
    db.put_prices([p for p in prices if p[0] < today + 86400 + (86400 if time.localtime().tm_hour >= 13 else 0)])
    hub._demo = {"cloud": cloud, "start": start, "arrays": arrays}
    for key in ["price", *SOURCES]:
        hub.mark(key, True, count=48)
    hub.mark("ha", True, "Demo")
    hub.mark("actual", True, count=len(actual))
    hub.learn()


async def live_loop(hub) -> None:
    rnd = random.Random()
    soc = 62.0
    while True:
        d = hub._demo
        now = int(time.time())
        i = min(len(d["cloud"]) - 1, (now - d["start"]) // 3600)
        values = {}
        pv_total = 0.0
        for cfg, arr in d["arrays"]:
            w = clearsky_hour(now // 3600 * 3600, arr, LAT, LON) * d["cloud"][i] * rnd.uniform(0.9, 1.05)
            pv_total += w
            values[f"pv:{cfg['id']}"] = {"entity": cfg["sensor"], "name": cfg["name"], "value": round(w), "unit": "W"}
        house = 420 + rnd.uniform(0, 600)
        batt = max(-3000, min(3000, pv_total - house))
        soc = max(5, min(100, soc + batt / 11000 * LIVE_STEP_H * 100))
        grid = house - pv_total + batt
        values.update({
            "house": {"entity": "sensor.hausverbrauch", "name": "Hausverbrauch", "value": round(house), "unit": "W"},
            "grid": {"entity": "sensor.netzleistung", "name": "Netzleistung", "value": round(grid), "unit": "W"},
            "battery_soc": {"entity": "sensor.batterie_ladezustand", "name": "Batterie", "value": round(soc, 1), "unit": "%"},
            "battery_power": {"entity": "sensor.batterie_leistung", "name": "Batterie Leistung", "value": round(batt), "unit": "W"},
        })
        hub.live = {"at": now, "values": values}
        if now - hub._plan_at > 60:
            await hub.update_plan()
        await asyncio.sleep(5)


LIVE_STEP_H = 5 / 3600
