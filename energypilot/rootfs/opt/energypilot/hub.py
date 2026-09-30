"""Background work: collect forecasts, prices and measurements, live values, HA sensors."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp

from . import __version__, analysis, geometry, learn, planner
from .config import OPEN_METEO_MODELS, Options, Settings, to_array
from .db import Database
from .ha import HAError, HomeAssistant
from .solar import Array, pv_hour
from .sources import SourceError, forecastsolar, openmeteo, prices, solcast

_LOGGER = logging.getLogger(__name__)

ARCHIVE_CHUNK_DAYS = 92
LIVE_INTERVAL = 15
PLAN_INTERVAL = 300
MODE_LABEL = {"normal": "Eigenverbrauch", "hold": "Akku halten", "charge": "Aus dem Netz laden"}
GEOMETRY_KEYS = ("planes", "efficiency", "ac_max_kw")
POWER_UNITS = {"W": 1.0, "kW": 1000.0, "MW": 1e6}


def source_label(key: str) -> str:
    if key.startswith("om:"):
        return OPEN_METEO_MODELS.get(key[3:], key[3:])
    return {
        "fs": "Forecast.Solar",
        "sc": "Solcast",
        learn.PV_SOURCE: "EnergyPilot (lernend)",
        learn.NOWCAST_SOURCE: "EnergyPilot (live korrigiert)",
        learn.NAIVE_SOURCE: "Wie vor einer Woche",
    }.get(key, key)


class Hub:
    def __init__(self, options: Options, settings: Settings, db: Database, ha: HomeAssistant) -> None:
        self.options = options
        self.settings = settings
        self.db = db
        self.ha = ha
        self.tz = ZoneInfo("Europe/Berlin")
        self.ha_location: tuple[float, float] | None = None
        self.status: dict[str, dict] = {}
        self.live: dict = {"at": None, "values": {}}
        self.backfill = {"running": False, "text": "", "done": 0, "total": 0}
        self.session: aiohttp.ClientSession | None = None
        self._tasks: list[asyncio.Task] = []
        self._wake = asyncio.Event()
        self._busy = asyncio.Lock()
        self._solcast_slots: set[str] = set()
        self._price_slot: int | None = None
        self._acc_cache: dict[tuple, tuple[float, dict]] = {}
        self._midnight: dict[str, int] = {}
        self.model_info: dict[str, dict] = {}
        self.plan: dict = {"ok": False, "reason": "Wird berechnet …"}
        self._pv_samples: deque[tuple[float, float]] = deque(maxlen=1200)  # (time, total PV W)
        self.nowcast: dict | None = None
        self._plan_at = 0.0

    # ------------------------------------------------------------------ basics
    @property
    def location(self) -> tuple[float, float] | None:
        loc = self.settings.data["location"]
        if loc.get("latitude") is not None and loc.get("longitude") is not None:
            return float(loc["latitude"]), float(loc["longitude"])
        return self.ha_location

    def arrays(self) -> list[tuple[dict, Array]]:
        return [(cfg, to_array(cfg)) for cfg in self.settings.arrays if cfg["kwp"] > 0]

    def mark(self, key: str, ok: bool, text: str = "", count: int | None = None) -> None:
        prev = self.status.get(key, {})
        self.status[key] = {
            "ok": ok,
            "at": int(time.time()),
            "text": text,
            "count": count if count is not None else prev.get("count"),
            "last_ok": int(time.time()) if ok else prev.get("last_ok"),
        }
        if not ok:
            _LOGGER.warning("%s: %s", source_label(key), text)

    def day_key(self, ts: float) -> str:
        return datetime.fromtimestamp(ts, self.tz).strftime("%Y-%m-%d")

    def midnight(self, ts: int) -> int:
        """Start (unix) of the local day containing ``ts``."""
        key = self.day_key(ts)
        if key not in self._midnight:
            self._midnight[key] = analysis.day_start(key, self.tz)
        return self._midnight[key]

    def horizons(self, target: int, now: float) -> list[str]:
        """Which stored horizons a forecast issued ``now`` may still update."""
        out = []
        if target > now:
            out.append("d0")
        if self.midnight(target) > now:
            out.append("d1")
        return out

    # --------------------------------------------------------------- lifecycle
    async def start(self) -> None:
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60),
            headers={"User-Agent": f"EnergyPilot/{__version__} (Home Assistant add-on)"},
        )
        if self.options.demo:
            from . import demo

            demo.populate(self)
            self._tasks.append(asyncio.create_task(demo.live_loop(self)))
            return
        await self.load_ha_config()
        self._tasks.append(asyncio.create_task(self._main_loop()))
        self._tasks.append(asyncio.create_task(self._live_loop()))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if self.session:
            await self.session.close()
        await self.ha.close()

    async def load_ha_config(self) -> None:
        if not self.ha.available:
            self.mark("ha", False, "Kein Zugriff auf Home Assistant")
            return
        try:
            cfg = await self.ha.config()
        except HAError as err:
            self.mark("ha", False, str(err))
            return
        if cfg.get("latitude") is not None:
            self.ha_location = (float(cfg["latitude"]), float(cfg["longitude"]))
        try:
            self.tz = ZoneInfo(cfg.get("time_zone") or "Europe/Berlin")
            self._midnight.clear()
        except ZoneInfoNotFoundError:
            pass
        self.mark("ha", True, cfg.get("version", ""))

    def trigger(self) -> None:
        """Run a collection cycle now (after settings changed or on request)."""
        self._wake.set()

    async def _main_loop(self) -> None:
        while True:
            try:
                await self.cycle()
            except Exception:
                _LOGGER.exception("Collection cycle failed")
            now = time.time()
            wait = 3600 - (now % 3600) + 240  # next hh:04
            local = datetime.fromtimestamp(now, self.tz)
            if local.hour >= 13 and not self._has_tomorrow_prices(now):
                wait = min(wait, 900)
            try:
                await asyncio.wait_for(self._wake.wait(), wait)
            except TimeoutError:
                pass
            self._wake.clear()

    async def cycle(self) -> None:
        async with self._busy:
            if not self.ha_location:
                await self.load_ha_config()
            await self.fetch_prices()
            await self.fetch_forecasts()
            await self.update_actuals()
            await self.backfill_archive()
            await self.run_learning()
            self._acc_cache.clear()
            await self.update_plan()
            await self.publish()

    # ------------------------------------------------------------------ prices
    def _has_tomorrow_prices(self, now: float) -> bool:
        last = self.db.last_price_ts()
        tomorrow = self.midnight(self.midnight(int(now)) + 90000)
        return bool(last and last >= tomorrow + 20 * 3600)

    async def fetch_prices(self) -> None:
        tariff = self.settings.data["tariff"]
        now = time.time()
        start = self.midnight(int(now)) - 86400
        today = datetime.fromtimestamp(now, self.tz).date()
        try:
            rows = await prices.fetch(
                self.session,
                tariff["bidding_zone"],
                start,
                start + 4 * 86400,
                (today - timedelta(days=1)).isoformat(),
                (today + timedelta(days=1)).isoformat(),
            )
        except SourceError as err:
            self.mark("price", False, str(err))
            return
        self.db.put_prices(rows)
        self.mark("price", True, count=len(rows))
        await self.backfill_prices()

    async def backfill_prices(self) -> None:
        """Past spot prices (once) so the cost overview can evaluate the backfilled measurements."""
        today = datetime.now(self.tz).date()
        first = today - timedelta(days=int(self.settings.data["backfill_days"]))
        have = self.db.get_meta("prices_from")
        if have and date.fromisoformat(have) <= first:
            return
        end = date.fromisoformat(have) if have else today
        zone = self.settings.data["tariff"]["bidding_zone"]
        cur = first
        while cur < end:
            stop = min(end - timedelta(days=1), cur + timedelta(days=30))
            start_ts = analysis.day_start(cur.isoformat(), self.tz)
            end_ts = analysis.day_start((stop + timedelta(days=1)).isoformat(), self.tz)
            try:
                rows = await prices.fetch(self.session, zone, start_ts, end_ts, cur.isoformat(), stop.isoformat())
            except SourceError as err:
                _LOGGER.info("Price history not available: %s", err)
                return
            self.db.put_prices(rows)
            cur = stop + timedelta(days=1)
        self.db.set_meta("prices_from", first.isoformat())

    # --------------------------------------------------------------- forecasts
    def _pv_rows(
        self, source: str, hours, horizons_for, arrays: list[tuple[dict, Array]], lat: float, lon: float
    ) -> list[tuple]:
        """Forecast rows from weather hours; ``horizons_for(hour)`` gives (horizon, issued) pairs."""
        rows = []
        for h in hours:
            targets = horizons_for(h)
            if not targets:
                continue
            for cfg, arr in arrays:
                wh = pv_hour(h.start, h.ghi, h.dhi, h.temp, arr, lat, lon)
                for horizon, issued in targets:
                    rows.append((source, cfg["id"], h.start, horizon, round(wh, 1), issued))
        return rows

    async def fetch_forecasts(self) -> None:
        loc = self.location
        arrays = self.arrays()
        if not loc or not arrays:
            return
        lat, lon = loc
        src = self.settings.data["sources"]
        now = time.time()
        issued = int(now)

        if src["open_meteo"]:
            for model in src["models"]:
                key = f"om:{model}"
                try:
                    hours = await openmeteo.forecast(self.session, lat, lon, model)
                except SourceError as err:
                    self.mark(key, False, str(err))
                    continue

                def live(h, now=now):
                    return [(hz, issued) for hz in self.horizons(h.start, now)]

                wrows = [
                    (model, h.start, hz, h.ghi, h.dhi, h.temp, h.cloud, h.wind, issued)
                    for h in hours
                    for hz in self.horizons(h.start, now)
                ]
                frows = await asyncio.to_thread(self._pv_rows, key, hours, live, arrays, lat, lon)
                self.db.put_weather(wrows)
                self.db.put_forecast(frows)
                self.mark(key, True, count=len(hours))

        if src["forecast_solar"]:
            errors, count = [], 0
            for cfg, _arr in arrays:
                # one call per plane, summed – a partial sum would look like a bad forecast
                hours: dict[int, float] = {}
                try:
                    for plane in cfg["planes"]:
                        part = await forecastsolar.fetch(
                            self.session, lat, lon, plane["tilt"], plane["azimuth"], plane["kwp"]
                        )
                        for t, wh in part.items():
                            hours[t] = hours.get(t, 0.0) + wh
                except SourceError as err:
                    errors.append(f"{cfg['name']}: {err}")
                    continue
                self.db.put_forecast(self._direct_rows("fs", cfg["id"], hours, now))
                count += len(hours)
            # one status for all arrays: a later success must not hide the failure of another array
            self.mark("fs", not errors, "; ".join(errors), count=count)

        key = src.get("solcast_key")
        slot = datetime.fromtimestamp(now, self.tz).strftime("%Y-%m-%d-%H")
        if key and slot not in self._solcast_slots:
            local_hour = datetime.fromtimestamp(now, self.tz).hour
            if local_hour in src["solcast_hours"] or not self.status.get("sc", {}).get("last_ok"):
                self._solcast_slots.add(slot)
                for cfg, _arr in arrays:
                    if not cfg.get("solcast_id"):
                        continue
                    try:
                        hours = await solcast.fetch(self.session, key, cfg["solcast_id"])
                    except SourceError as err:
                        self.mark("sc", False, f"{cfg['name']}: {err}")
                        continue
                    self.db.put_forecast(self._direct_rows("sc", cfg["id"], hours, now))
                    self.mark("sc", True, count=len(hours))

    def _direct_rows(self, source: str, array_id: str, hours: dict[int, float], now: float) -> list[tuple]:
        return [
            (source, array_id, t, hz, round(wh, 1), int(now))
            for t, wh in hours.items()
            for hz in self.horizons(t, now)
        ]

    async def recompute_array(self, cfg: dict) -> None:
        """Array geometry changed – rebuild its Open-Meteo forecasts from stored weather."""
        loc = self.location
        if not loc or cfg["kwp"] <= 0:
            return
        arr = to_array(cfg)
        models = list(OPEN_METEO_MODELS)

        def work() -> int:
            rows = []
            for model, target, horizon, ghi, dhi, temp, issued in self.db.weather(models):
                wh = pv_hour(target, ghi, dhi, temp, arr, loc[0], loc[1])
                rows.append((f"om:{model}", cfg["id"], target, horizon, round(wh, 1), issued))
            return self.db.put_forecast(rows)

        async with self._busy:
            n = await asyncio.to_thread(work)
        self._acc_cache.clear()
        _LOGGER.info("Recomputed %d forecast hours for %s", n, cfg["name"])

    async def backfill_archive(self) -> None:
        """Archived Open-Meteo forecasts for the backfill period (once, then daily top-up)."""
        loc = self.location
        arrays = self.arrays()
        src = self.settings.data["sources"]
        if not loc or not arrays or not src["open_meteo"]:
            return
        lat, lon = loc
        today = datetime.now(self.tz).date()
        first = today - timedelta(days=int(self.settings.data["backfill_days"]))
        jobs = []
        for model in src["models"]:
            for day1 in (False, True):
                key = f"archive:{model}:{'d1' if day1 else 'd0'}:{lat:.3f},{lon:.3f}"
                last = self.db.get_meta(key)
                if last == today.isoformat():
                    continue
                frm = max(first, date.fromisoformat(last) - timedelta(days=2)) if last else first
                jobs.append((model, day1, key, frm))
        if not jobs:
            return
        self.backfill.update(running=True, done=0, total=len(jobs))
        try:
            for model, day1, key, frm in jobs:
                label = f"{OPEN_METEO_MODELS.get(model, model)} ({'Vortag' if day1 else 'kurzfristig'})"
                self.backfill["text"] = f"Archiv: {label}"
                ok = True
                cur = frm
                while cur <= today:
                    end = min(today, cur + timedelta(days=ARCHIVE_CHUNK_DAYS - 1))
                    try:
                        hours = await openmeteo.archive(
                            self.session, lat, lon, model, cur.isoformat(), end.isoformat(), day1
                        )
                    except SourceError as err:
                        _LOGGER.info("Archive %s not available: %s", label, err)
                        ok = False
                        break
                    horizon = "d1" if day1 else "d0"
                    wrows = [
                        (model, h.start, horizon, h.ghi, h.dhi, h.temp, h.cloud, h.wind, 0)
                        for h in hours
                    ]
                    frows = await asyncio.to_thread(
                        self._pv_rows, f"om:{model}", hours, lambda h, hz=horizon: [(hz, 0)], arrays, lat, lon
                    )
                    self.db.put_weather_if_missing(wrows)
                    self.db.put_forecast_if_missing(frows)
                    cur = end + timedelta(days=1)
                if ok:
                    self.db.set_meta(key, today.isoformat())
                self.backfill["done"] += 1
        finally:
            self.backfill.update(running=False, text="")

    # ------------------------------------------------------------------ actual
    def measured_series(self) -> dict[str, str]:
        out = {cfg["id"]: cfg["sensor"] for cfg in self.settings.arrays if cfg.get("sensor")}
        sensors = self.settings.data["sensors"]
        for key in ("house", "grid", "ev", "heater"):
            if sensors.get(key):
                out[key] = sensors[key]
        for key, series in (("grid_import", "grid_in"), ("grid_export", "grid_out")):
            if sensors.get(key):
                out[series] = sensors[key]
        return out

    async def update_actuals(self) -> None:
        series = self.measured_series()
        if not series or not self.ha.available:
            return
        now = int(time.time())
        ids = sorted(set(series.values()))
        try:
            meta = await self.ha.statistics_metadata(ids)
        except HAError as err:
            self.mark("actual", False, str(err))
            return
        power, energy = [], []
        for sid in ids:
            m = meta.get(sid)
            if not m:
                self.mark(f"act:{sid}", False, "Keine Langzeitstatistik – der Sensor braucht eine state_class")
                continue
            unit_class = m.get("unit_class")
            unit = m.get("statistics_unit_of_measurement")
            if unit_class == "energy" or unit in ("Wh", "kWh", "MWh"):
                energy.append(sid)
            elif unit_class == "power" or unit in POWER_UNITS:
                power.append(sid)
            else:
                self.mark(f"act:{sid}", False, f"Einheit {unit!r} wird nicht unterstützt (W/kW oder Wh/kWh)")
        total = 0
        for sid_list, stat_type in ((power, "mean"), (energy, "change")):
            if not sid_list:
                continue
            # first run per sensor: whole backfill period, afterwards the last 3 days
            backfill = [s for s in sid_list if not self.db.get_meta(f"actual:{s}")]
            groups = [(backfill, int(self.settings.data["backfill_days"]) + 1), ([s for s in sid_list if s not in backfill], 3)]
            for group, days in groups:
                if not group:
                    continue
                try:
                    stats = await self.ha.statistics(group, now - days * 86400, now, [stat_type])
                except HAError as err:
                    self.mark("actual", False, str(err))
                    return
                rows = []
                for name, sid in series.items():
                    for r in stats.get(sid, []):
                        v = r.get(stat_type)
                        if v is not None:
                            rows.append((name, r["ts"], float(v)))
                total += self.db.put_actual(rows)
                for sid in group:
                    self.db.set_meta(f"actual:{sid}", str(now))
                    self.mark(f"act:{sid}", True, count=len(stats.get(sid, [])))
        self.mark("actual", True, count=total)

    # ------------------------------------------------------------------- costs
    def costs(self, start: int, end: int) -> dict:
        """Electricity bill from the measured grid energy and the hourly prices, per local day."""
        s = self.settings.data
        sensors, inv, tariff = s["sensors"], s["invert"], s["tariff"]
        acts: dict[str, dict[int, float]] = defaultdict(dict)
        for series, t, wh in self.db.actuals(start, end):
            acts[series][t] = wh
        ids = [c["id"] for c in s["arrays"] if c["kwp"] > 0 and c.get("sensor")]
        price_h: dict[int, list[float]] = defaultdict(list)
        market: dict[str, list[float]] = defaultdict(list)
        now = time.time()
        for slot in self.price_slots(start, end):
            price_h[slot["ts"] // 3600 * 3600].append(slot["price"])
            if slot["ts"] + slot["dur"] <= now:  # only what could have been bought already
                market[self.day_key(slot["ts"])].append(slot["price"])
        grid_sign = -1.0 if inv.get("grid") else 1.0
        # like the base load: a house sensor with negative consumption is flipped automatically
        house_sign = -1.0 if inv.get("house") or sum(acts.get("house", {}).values()) < 0 else 1.0
        days: dict[str, dict] = {}
        for t in range(start, end, 3600):
            imp = abs(acts["grid_in"][t]) / 1000 if sensors.get("grid_import") and t in acts.get("grid_in", {}) else None
            exp = abs(acts["grid_out"][t]) / 1000 if sensors.get("grid_export") and t in acts.get("grid_out", {}) else None
            if (imp is None or exp is None) and t in acts.get("grid", {}):
                v = acts["grid"][t] * grid_sign / 1000
                imp = max(0.0, v) if imp is None else imp
                exp = max(0.0, -v) if exp is None else exp
            if imp is None and exp is None:
                continue
            imp, exp = imp or 0.0, exp or 0.0
            d = days.setdefault(self.day_key(t), {
                "import_kwh": 0.0, "export_kwh": 0.0, "energy_ct": 0.0, "unpriced_kwh": 0.0,
                "pv_kwh": 0.0, "house_kwh": 0.0, "hours": 0,
            })
            d["hours"] += 1
            d["import_kwh"] += imp
            d["export_kwh"] += exp
            if price_h.get(t):
                d["energy_ct"] += imp * sum(price_h[t]) / len(price_h[t])
            else:
                d["unpriced_kwh"] += imp
            if ids and all(t in acts.get(i, {}) for i in ids):
                d["pv_kwh"] += sum(max(0.0, acts[i][t]) for i in ids) / 1000
            if t in acts.get("house", {}):
                d["house_kwh"] += max(0.0, acts["house"][t] * house_sign) / 1000
        fee_day = float(tariff.get("base_fee_eur", 0)) * 12 / 365
        cmp_fee_day = float(tariff.get("compare_base_fee_eur", 0)) * 12 / 365
        feed = float(tariff.get("feed_in_ct", 0))
        cmp_price = float(tariff.get("compare_price_ct", 0))
        out_days = []
        tot = defaultdict(float)
        for day, d in sorted(days.items()):
            priced = d["import_kwh"] - d["unpriced_kwh"]
            row = {
                "day": day,
                "hours": d["hours"],
                "import_kwh": round(d["import_kwh"], 2),
                "export_kwh": round(d["export_kwh"], 2),
                "pv_kwh": round(d["pv_kwh"], 2),
                "house_kwh": round(d["house_kwh"], 2),
                "energy_eur": round(d["energy_ct"] / 100, 2),
                "fee_eur": round(fee_day, 2),
                "feed_in_eur": round(d["export_kwh"] * feed / 100, 2),
                "avg_paid_ct": round(d["energy_ct"] / priced, 2) if priced > 0.05 else None,
                "avg_market_ct": round(sum(market[day]) / len(market[day]), 2) if market.get(day) else None,
                "unpriced_kwh": round(d["unpriced_kwh"], 2),
                "compare_eur": round((d["import_kwh"] * cmp_price) / 100 + cmp_fee_day, 2),
            }
            row["total_eur"] = round(row["energy_eur"] + row["fee_eur"] - row["feed_in_eur"], 2)
            row["compare_total_eur"] = round(row["compare_eur"] - row["feed_in_eur"], 2)
            out_days.append(row)
            for k in ("import_kwh", "export_kwh", "pv_kwh", "house_kwh", "energy_eur", "fee_eur", "feed_in_eur",
                      "total_eur", "compare_total_eur", "unpriced_kwh"):
                tot[k] += row[k]
            tot["energy_ct"] += d["energy_ct"]
            tot["priced_kwh"] += priced
            tot["market_sum"] += sum(market.get(day, []))
            tot["market_n"] += len(market.get(day, []))
        totals = {k: round(v, 2) for k, v in tot.items() if k not in ("energy_ct", "priced_kwh", "market_sum", "market_n")}
        totals["days"] = len(out_days)
        totals["avg_paid_ct"] = round(tot["energy_ct"] / tot["priced_kwh"], 2) if tot["priced_kwh"] > 0.05 else None
        totals["avg_market_ct"] = round(tot["market_sum"] / tot["market_n"], 2) if tot["market_n"] else None
        totals["savings_eur"] = round(tot["compare_total_eur"] - tot["total_eur"], 2)
        if tot["house_kwh"] > 0:
            totals["autarky_pct"] = round(max(0.0, 1 - tot["import_kwh"] / tot["house_kwh"]) * 100, 1)
        if tot["pv_kwh"] > 0:
            totals["self_use_pct"] = round(max(0.0, 1 - tot["export_kwh"] / tot["pv_kwh"]) * 100, 1)
        return {
            "days": out_days,
            "totals": totals,
            "split": bool(sensors.get("grid_import") and sensors.get("grid_export")),
            "has_grid": bool(sensors.get("grid") or sensors.get("grid_import")),
            "tariff": {k: tariff.get(k) for k in ("base_fee_eur", "compare_price_ct", "compare_base_fee_eur", "feed_in_ct")},
        }

    def cost_months(self, count: int = 12) -> list[dict]:
        """Totals per calendar month, newest first."""
        today = datetime.now(self.tz).date().replace(day=1)
        out = []
        for i in range(count):
            y, m = divmod(today.month - 1 - i, 12)
            first = date(today.year + y, m + 1, 1)
            nxt = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
            res = self.costs(analysis.day_start(first.isoformat(), self.tz), analysis.day_start(nxt.isoformat(), self.tz))
            if res["totals"]["days"]:
                out.append({"month": first.strftime("%Y-%m"), **res["totals"]})
        return out

    # ---------------------------------------------------------------- geometry
    def check_geometry(self, array_id: str) -> dict:
        """Which orientation fits the measured production best (see geometry.py)."""
        cfg = next((c for c in self.settings.arrays if c["id"] == array_id), None)
        if not cfg:
            return {"ok": False, "reason": "Anlage nicht gefunden."}
        if not cfg.get("sensor") or not cfg["planes"]:
            return {"ok": False, "reason": "Die Anlage braucht einen Messsensor und mindestens eine Teilfläche."}
        loc = self.location
        if not loc:
            return {"ok": False, "reason": "Standort unbekannt."}
        models = list(dict.fromkeys(["best_match", *self.settings.data["sources"]["models"]]))
        by_model: dict[str, list[tuple]] = defaultdict(list)
        for model, target, horizon, ghi, dhi, temp, _issued in self.db.weather(models):
            if horizon == "d0" and ghi is not None:
                by_model[model].append((target, ghi, dhi, temp))
        model = next((m for m in models if len(by_model.get(m, [])) >= 200), None)
        if not model:
            return {"ok": False, "reason": "Noch zu wenige Wetterdaten – das Archiv wird nach dem Start im Hintergrund geladen."}
        weather = sorted(by_model[model])
        actual = {t: wh for _s, t, wh in self.db.actuals(weather[0][0], weather[-1][0] + 3600, array_id)}
        res = geometry.fit(to_array(cfg), weather, actual, *loc)
        res["model"] = source_label(f"om:{model}")
        res["efficiency"] = cfg["efficiency"]
        if res.get("ok"):
            res["implied_efficiency"] = round(cfg["efficiency"] * res["scale"], 3)
        return res

    # ---------------------------------------------------------------- learning
    async def run_learning(self) -> None:
        try:
            await asyncio.to_thread(self.learn)
        except Exception as err:
            _LOGGER.exception("Learning failed")
            self.mark("learn", False, f"Lernen fehlgeschlagen: {err}")

    def base_load(self, acts: dict[str, dict[int, float]]) -> dict[int, float]:
        """Household consumption without EV and heating rod (Wh per hour).

        Hours where the EV or heating-rod value is missing are left out – guessing
        0 there would count a charging car as base load. Sensors that report
        consumption as negative values (some inverters do) are flipped."""
        sensors = self.settings.data["sensors"]
        extra = [k for k in ("ev", "heater") if sensors.get(k)]
        sign = {k: -1.0 if sum(acts.get(k, {}).values()) < 0 else 1.0 for k in ("house", *extra)}
        if self.settings.data["invert"].get("house"):
            sign["house"] = -1.0
        out = {}
        for t, house in acts.get("house", {}).items():
            parts = [acts.get(k, {}).get(t) for k in extra]
            if any(v is None for v in parts):
                continue
            parts = [max(0.0, v * sign[k]) for k, v in zip(extra, parts, strict=True)]
            out[t] = max(0.0, house * sign["house"] - sum(parts))
        return out

    def consumption_check(self, days: int = 7) -> dict:
        """Average kWh per day of the consumption series – to verify the sensor choice."""
        end = self.midnight(int(time.time()))
        start = end - days * 86400
        sensors = self.settings.data["sensors"]
        out: dict = {"days": days, "series": {}}
        for key in ("house", "ev", "heater", learn.BASE_SERIES):
            if key != learn.BASE_SERIES and not sensors.get(key):
                continue
            rows = self.db.actuals(start, end, key)
            total = sum(wh for _s, _t, wh in rows)
            out["series"][key] = {
                "kwh_per_day": round(total / 1000 / days, 2),
                "hours": len(rows),
                "negative": total < 0,
            }
        fc = [wh for s, a, t, wh in self.db.forecasts(start, end, "d1") if s == learn.LOAD_SOURCE and a == learn.BASE_SERIES]
        out["forecast_kwh_per_day"] = round(sum(fc) / 1000 / days, 2) if fc else None
        return out

    def daily_temps(self) -> dict[str, float]:
        """Mean temperature per local day from the weather models (short-term forecast)."""
        models = [m for m in ("best_match", *self.settings.data["sources"]["models"]) if m]
        per: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for model, target, horizon, _ghi, _dhi, temp, _issued in self.db.weather(list(dict.fromkeys(models))):
            if horizon == "d0" and temp is not None:
                per[model][self.day_key(target)].append(temp)
        for model in models:  # first model with data wins
            if per.get(model):
                return {d: sum(v) / len(v) for d, v in per[model].items() if len(v) >= 20}
        return {}

    def learn(self) -> None:
        """Walk-forward training of the own PV and base-load forecasts (runs in a thread)."""
        now = int(time.time())
        today = self.midnight(now)
        end = self.midnight(self.midnight(today + 90000) + 90000)  # end of tomorrow
        first = today - int(self.settings.data["backfill_days"]) * 86400
        start = self.midnight(first - learn.TRAIN_DAYS * 86400 - 3600)
        hours = range(start, end, 3600)
        local = {t: datetime.fromtimestamp(t, self.tz) for t in hours}
        days = sorted({local[t].strftime("%Y-%m-%d") for t in hours if t >= first})
        acts: dict[str, dict[int, float]] = defaultdict(dict)
        for series, t, wh in self.db.actuals(start, end):
            acts[series][t] = wh
        rows: list[tuple] = []
        loc = self.location
        info: dict[str, dict] = {}
        if loc:
            lat, lon = round(loc[0], 3), round(loc[1], 3)
            for horizon in ("d1", "d0"):
                fcs: dict[str, dict[int, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
                for source, arr, t, wh in self.db.forecasts(start, end, horizon):
                    if source not in learn.LEARNED_SOURCES:
                        fcs[arr][t][source] = wh
                for cfg, arr in self.arrays():
                    if not cfg.get("sensor"):
                        continue
                    by_day: dict[str, list[learn.PVHour]] = defaultdict(list)
                    for t in hours:
                        fc = fcs[cfg["id"]].get(t)
                        if not fc:
                            continue
                        act = acts[cfg["id"]].get(t)
                        by_day[local[t].strftime("%Y-%m-%d")].append(
                            learn.PVHour(t, local[t].hour, analysis._clear(t, arr, lat, lon),
                                         None if act is None else max(0.0, act), dict(fc))
                        )
                    res = learn.pv_walk_forward(days, by_day)
                    for src, values in ((learn.PV_SOURCE, res.forecast), (learn.BAND_LO, res.lo), (learn.BAND_HI, res.hi)):
                        rows += [(src, cfg["id"], t, horizon, round(v, 1), 0) for t, v in values.items()]
                    model = res.model
                    if horizon == "d1" and model is not None:
                        info[cfg["id"]] = {
                            "days": model.days,
                            "weights": {k: round(v, 3) for k, v in model.weight_share().items()},
                            "factors": model.hour_factors(),
                            "band": {b: [round(x, 3) for x in v] for b, v in model.band.items()},
                        }
        base = self.base_load(acts)
        # rebuild the stored base load completely: rows from an earlier sensor setup must not stay behind
        self.db.delete_actual_range(learn.BASE_SERIES, start, end)
        if base:
            self.db.put_actual([(learn.BASE_SERIES, t, round(v, 1)) for t, v in base.items()])
            by_day_load: dict[str, list[learn.LoadHour]] = defaultdict(list)
            for t in hours:
                d = local[t]
                key = d.strftime("%Y-%m-%d")
                by_day_load[key].append(learn.LoadHour(t, key, d.hour, learn.daytype(d.weekday()), base.get(t)))
            model_out, naive = learn.load_walk_forward(days, by_day_load, self.daily_temps())
            for horizon in ("d1", "d0"):
                rows += [(learn.LOAD_SOURCE, learn.BASE_SERIES, t, horizon, round(v, 1), 0) for t, v in model_out.items()]
                rows += [(learn.NAIVE_SOURCE, learn.BASE_SERIES, t, horizon, round(v, 1), 0) for t, v in naive.items()]
        self.db.put_forecast(rows)
        # up to 0.5.5 the live correction was also copied onto the load forecast
        self.db.delete_forecast_source(learn.NOWCAST_SOURCE, learn.BASE_SERIES)
        self.model_info = info
        self._acc_cache.clear()
        if rows:
            self.mark("learn", True, count=len(rows))

    # ---------------------------------------------------------------- planning
    def battery(self) -> planner.Battery:
        b = self.settings.data["battery"]
        return planner.Battery(**{k: b[k] for k in planner.Battery.__dataclass_fields__})

    def energy_hours(self, now: float) -> tuple[list[dict], str | None, str]:
        """PV and base-load forecast per hour from now to the end of tomorrow (kWh)."""
        start = int(now) // 3600 * 3600
        end = self.midnight(self.midnight(self.midnight(int(now)) + 90000) + 90000)
        ids = [c["id"] for c in self.settings.arrays if c["kwp"] > 0]
        best = self.best_source() if ids else None
        pv: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
        count: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        load: dict[int, float] = {}
        for source, arr, t, wh in self.db.forecasts(start, end, "d0"):
            if arr in ids:
                pv[source][t] += wh
                count[source][t] += 1
            elif source == learn.LOAD_SOURCE and arr == learn.BASE_SERIES:
                load[t] = wh
        # take the most accurate source; hours it does not cover come from the own forecast / Open-Meteo Auto
        order = self.pv_order(best or "")
        caution = float(self.settings.data["battery"].get("pv_caution", 0))
        profile = self.load_profile() if len(load) < (end - start) // 3600 else {}
        out = []
        for t in range(start, end, 3600):
            frac = 1 - (now - t) / 3600 if t == start else 1.0
            src = next((x for x in order if count[x].get(t) == len(ids)), None)
            pv_wh = pv[src][t] if src else 0.0
            if src == learn.PV_SOURCE and caution and count[learn.BAND_LO].get(t) == len(ids):
                pv_wh -= caution * max(0.0, pv_wh - pv[learn.BAND_LO][t])  # towards the pessimistic P10
            load_wh = load.get(t)
            if load_wh is None:
                load_wh = profile.get(datetime.fromtimestamp(t, self.tz).hour, 400.0)
            out.append({"t": t, "frac": frac, "pv": pv_wh / 1000 * frac, "load": load_wh / 1000 * frac, "src": src})
        nc = self.nowcast or {}
        if nc.get("factor"):  # the next hours follow what the panels deliver right now
            f = nc["factor"]
            for i, e in enumerate(out[: len(learn.NOWCAST_WEIGHTS)]):
                if e["src"] == nc.get("source"):  # the factor belongs to this source
                    e["pv"] *= 1 + (f - 1) * learn.NOWCAST_WEIGHTS[i]
        for e in out:
            e.pop("src")
        return out, best, "Verbrauchsprognose" if load else "Durchschnitt der letzten 14 Tage"

    def pv_order(self, best: str | None = None) -> list[str]:
        """PV sources the plan uses, in order of preference."""
        if best is None:
            best = self.best_source()
        return list(dict.fromkeys(x for x in (best, learn.PV_SOURCE, "om:best_match") if x))

    def load_profile(self) -> dict[int, float]:
        """Mean consumption per hour of day over the last 14 days (fallback)."""
        now = int(time.time())
        per: dict[int, list[float]] = defaultdict(list)
        rows = self.db.actuals(now - 14 * 86400, now, learn.BASE_SERIES) or self.db.actuals(now - 14 * 86400, now, "house")
        for _s, t, wh in rows:
            per[datetime.fromtimestamp(t, self.tz).hour].append(max(0.0, wh))
        return {h: sum(v) / len(v) for h, v in per.items() if v}

    def battery_runtime(self, soc_kwh: float, hours: list[dict], house_w: float | None, now: float) -> dict:
        """How long the battery lasts: at today's consumption and along the forecast."""
        b = self.battery()
        lo = b.capacity_kwh * b.min_soc / 100
        usable = max(0.0, soc_kwh - lo)
        out = {"usable_kwh": round(usable, 2), "now_hours": None, "empty_at": None, "full_at": None,
               "until": hours[-1]["t"] + 3600 if hours else None}
        if house_w and house_w > 50:
            out["now_hours"] = round(usable / (house_w / 1000), 2)
        soc = soc_kwh
        eta = b.eta
        for h in hours:
            t0 = now if h["frac"] < 1 else h["t"]
            span = h["frac"] * 3600
            net = h["pv"] - h["load"]
            if net >= 0:
                gain = min(net, b.max_charge_kw * h["frac"]) * eta
                if out["full_at"] is None and soc < b.capacity_kwh - 0.05 <= soc + gain:
                    out["full_at"] = int(t0 + span * (b.capacity_kwh - soc) / gain)
                soc = min(b.capacity_kwh, soc + gain)
            else:
                need = min(-net, b.max_discharge_kw * h["frac"]) / eta
                if soc - need <= lo:
                    if out["empty_at"] is None:
                        out["empty_at"] = int(t0 + span * max(0.0, soc - lo) / need) if need > 0 else int(t0)
                    soc = lo
                else:
                    soc -= need
        return out

    def compute_plan(self) -> dict:
        now = time.time()
        soc_val = (self.live.get("values", {}).get("battery_soc") or {}).get("value")
        if not self.settings.data["sensors"].get("battery_soc"):
            return {"ok": False, "reason": "Für den Plan wird der Ladezustand der Batterie gebraucht – bitte unter Einstellungen › Sensoren auswählen."}
        if soc_val is None:
            return {"ok": False, "reason": "Der Ladezustand der Batterie ist gerade nicht verfügbar."}
        b = self.battery()
        soc_kwh = b.capacity_kwh * float(soc_val) / 100
        energy, best, load_src = self.energy_hours(now)
        house = (self.live.get("values", {}).get("house") or {}).get("value")
        runtime = self.battery_runtime(soc_kwh, energy, house, now)
        prices_h: dict[int, list[float]] = defaultdict(list)
        for slot in self.price_slots(int(now) // 3600 * 3600, energy[-1]["t"] + 3600 if energy else int(now)):
            prices_h[slot["ts"] // 3600 * 3600].append(slot["price"])
        hours = []
        for e in energy:  # the plan ends where known prices end
            if e["t"] not in prices_h:
                break
            hours.append(planner.Hour(e["t"], e["pv"], e["load"], sum(prices_h[e["t"]]) / len(prices_h[e["t"]]), e["frac"]))
        base = {
            "soc": round(float(soc_val), 1),
            "runtime": runtime,
            "pv_source": source_label(best) if best else None,
            "load_source": load_src,
            "battery": self.settings.data["battery"],
            "energy": [{"ts": e["t"], "pv": round(e["pv"], 3), "load": round(e["load"], 3)} for e in energy],
        }
        if not hours:
            return {**base, "ok": False, "reason": "Noch keine Strompreise für die nächsten Stunden."}
        feed_in = float(self.settings.data["tariff"].get("feed_in_ct", 0))
        plan = planner.optimize(hours, soc_kwh, b, feed_in)
        cap = b.capacity_kwh
        steps = [
            {
                "ts": st.start, "mode": st.mode, "label": MODE_LABEL[st.mode], "price": round(h.price, 2),
                "pv": round(h.pv_kwh, 3), "load": round(h.load_kwh, 3),
                "import": round(st.grid_import, 3), "export": round(st.grid_export, 3),
                "soc_start": round(st.soc_start / cap * 100, 1), "soc_end": round(st.soc_end / cap * 100, 1),
                "cost": round(st.cost, 1),
            }
            for st, h in zip(plan.steps, hours, strict=True)
        ]
        first = steps[0]
        return {
            **base,
            "ok": True,
            "at": int(now),
            "decision": first["mode"],
            "label": first["label"],
            "buy_now": first["mode"] == "charge",
            "text": _decision_text(steps, self.tz),
            "steps": steps,
            "cost_eur": round(plan.cost / 100, 2),
            "baseline_eur": round(plan.cost_baseline / 100, 2),
            "savings_eur": round(plan.savings / 100, 2),
            "horizon_end": steps[-1]["ts"] + 3600,
            "first_fraction": hours[0].fraction,
            "nowcast": self.nowcast,
        }

    async def update_plan(self) -> None:
        try:
            self.nowcast = await asyncio.to_thread(self.compute_nowcast)
            await asyncio.to_thread(self.write_nowcast)
            self.plan = await asyncio.to_thread(self.compute_plan)
            self.log_plan()
        except Exception as err:
            _LOGGER.exception("Planning failed")
            self.plan = {"ok": False, "reason": f"Planung fehlgeschlagen: {err}"}
        self._plan_at = time.time()

    def log_plan(self) -> None:
        """Remember the recommendation made at the start of each hour (for the journal)."""
        p = self.plan
        if not p.get("ok"):
            return
        st = p["steps"][0]
        frac = max(0.05, p.get("first_fraction") or 1.0)
        self.db.log_plan((
            st["ts"], st["mode"], st["price"], round(st["pv"] / frac, 3), round(st["load"] / frac, 3),
            st["soc_start"], st["soc_end"], p["soc"], int(time.time()),
        ))

    def journal(self, days: int = 14) -> dict:
        """Recommendations of the past days checked against what really happened.

        Three bills from the real PV production, base load and prices:
        without plan (battery on its own – what actually happened), with the
        recommendations followed, and the best possible plan in hindsight."""
        now = int(time.time())
        end = now // 3600 * 3600  # complete hours only
        start = self.midnight(now) - (days - 1) * 86400
        logs = {r[0]: r for r in self.db.plan_log(start, end)}
        ids = [c["id"] for c in self.settings.arrays if c["kwp"] > 0 and c.get("sensor")]
        pv: dict[int, float] = defaultdict(float)
        pv_n: dict[int, int] = defaultdict(int)
        load: dict[int, float] = {}
        for series, t, wh in self.db.actuals(start, end):
            if series in ids:
                pv[t] += max(0.0, wh)
                pv_n[t] += 1
            elif series == learn.BASE_SERIES:
                load[t] = wh
        price_h: dict[int, list[float]] = defaultdict(list)
        for slot in self.price_slots(start, end):
            price_h[slot["ts"] // 3600 * 3600].append(slot["price"])
        # inverters switch off at night, their sensors then have no value -> 0 when the sun is down
        loc = self.location
        arrays = [arr for cfg, arr in self.arrays() if cfg["id"] in ids]

        def pv_of(t: int) -> float | None:
            if pv_n.get(t) == len(ids):
                return pv[t]
            if loc and arrays and all(analysis._clear(t, a, round(loc[0], 3), round(loc[1], 3)) <= 0 for a in arrays):
                return 0.0
            return None

        b = self.battery()
        feed_in = float(self.settings.data["tariff"].get("feed_in_ct", 0))
        cap = b.capacity_kwh
        per_day: dict[str, list[int]] = defaultdict(list)
        for t in sorted(logs):
            per_day[self.day_key(t)].append(t)
        out_days = []
        totals = {"base": 0.0, "plan": 0.0, "best": 0.0, "bill": 0.0, "hours": 0}
        for day, ts_list in sorted(per_day.items(), reverse=True):
            usable = [t for t in ts_list if pv_of(t) is not None and t in load and t in price_h]
            hours_detail = []
            for t in ts_list:
                r = logs[t]
                ok = t in usable
                hours_detail.append({
                    "ts": t, "mode": r[1], "price": r[2], "pv_fc": r[3], "load_fc": r[4],
                    "soc_plan": r[6],  # planned at the end of the hour
                    # measured at the end of the hour = start of the next logged hour
                    "soc_actual": logs[t + 3600][7] if t + 3600 in logs else None,
                    "pv": round(pv_of(t) / 1000, 3) if pv_of(t) is not None else None,
                    "load": round(load[t] / 1000, 3) if t in load else None,
                    "complete": ok,
                })
            entry = {
                "day": day, "hours": len(ts_list), "complete_hours": len(usable),
                "charge_hours": sum(1 for t in ts_list if logs[t][1] == "charge"),
                "hold_hours": sum(1 for t in ts_list if logs[t][1] == "hold"),
                # forecast and measurement over the same (complete) hours
                "pv_fc": round(sum(logs[t][3] or 0 for t in usable), 2) if usable else None,
                "pv": round(sum(pv_of(t) for t in usable) / 1000, 2) if usable else None,
                "load_fc": round(sum(logs[t][4] or 0 for t in usable), 2) if usable else None,
                "load": round(sum(load[t] for t in usable) / 1000, 2) if usable else None,
                "detail": hours_detail,
            }
            if usable:
                hrs = [planner.Hour(t, pv_of(t) / 1000, max(0.0, load[t]) / 1000, sum(price_h[t]) / len(price_h[t])) for t in usable]
                soc0 = cap * float(logs[usable[0]][7] or 0) / 100
                ev = planner.end_price(hrs, b)
                base = planner.simulate(hrs, soc0, b, feed_in, end_value=ev)
                modes = [logs[t][1] for t in usable]
                targets = [cap * float(logs[t][6] or 0) / 100 for t in usable]
                followed = planner.simulate(hrs, soc0, b, feed_in, modes, targets, end_value=ev)
                best = planner.optimize(hrs, soc0, b, feed_in)
                # shown bills: only what was bought and fed in. The savings also count
                # the energy left in the battery at the end (all three at the same price)
                bill = lambda plan: sum(st.cost for st in plan.steps)
                entry.update(
                    cost_base=round(bill(base) / 100, 2), cost_plan=round(bill(followed) / 100, 2),
                    cost_best=round(bill(best) / 100, 2),
                    saved=round((base.cost - followed.cost) / 100, 2), possible=round((base.cost - best.cost) / 100, 2),
                )
                totals["base"] += base.cost
                totals["plan"] += followed.cost
                totals["best"] += best.cost
                totals["bill"] += bill(base)
                totals["hours"] += len(usable)
            out_days.append(entry)
        return {
            "days": out_days,
            "since": min(logs) if logs else None,
            "totals": {
                "hours": totals["hours"],
                "saved": round((totals["base"] - totals["plan"]) / 100, 2),
                "possible": round((totals["base"] - totals["best"]) / 100, 2),
                "cost_base": round(totals["bill"] / 100, 2),
            },
            "battery": self.settings.data["battery"],
        }

    async def publish_plan(self) -> None:
        if not self.options.publish_sensors or not self.ha.available or self.options.demo:
            return
        p = self.plan
        ok = p.get("ok")
        tz = self.tz
        await self.ha.publish(
            "sensor.energypilot_empfehlung",
            p.get("label") if ok else "unbekannt",
            {
                "friendly_name": "EnergyPilot Empfehlung",
                "icon": "mdi:battery-sync-outline",
                "mode": p.get("decision"),
                "reason": p.get("text") if ok else p.get("reason"),
                "savings_eur": p.get("savings_eur"),
                "plan": [
                    {"start": datetime.fromtimestamp(st["ts"], tz).isoformat(), "mode": st["mode"], "soc": st["soc_end"], "price": st["price"]}
                    for st in p.get("steps", [])
                ],
            },
        )
        for key, on, name, icon in (
            ("netzladen", ok and p["decision"] == "charge", "EnergyPilot Akku aus dem Netz laden", "mdi:transmission-tower-import"),
            ("entladesperre", ok and p["decision"] in ("hold", "charge"), "EnergyPilot Akku-Entladung sperren", "mdi:battery-lock"),
        ):
            await self.ha.publish(f"binary_sensor.energypilot_{key}", "on" if on else "off", {"friendly_name": name, "icon": icon})
        rt = p.get("runtime") or {}
        if rt:
            await self.ha.publish(
                "sensor.energypilot_akku_reichweite",
                rt.get("now_hours"),
                {
                    "friendly_name": "EnergyPilot Akku-Reichweite",
                    "unit_of_measurement": "h",
                    "icon": "mdi:battery-clock-outline",
                    "usable_kwh": rt.get("usable_kwh"),
                    "empty_at": datetime.fromtimestamp(rt["empty_at"], tz).isoformat() if rt.get("empty_at") else None,
                    "full_at": datetime.fromtimestamp(rt["full_at"], tz).isoformat() if rt.get("full_at") else None,
                },
            )

    # -------------------------------------------------------------------- live
    async def _live_loop(self) -> None:
        while True:
            try:
                await self.read_live()
                if time.time() - self._plan_at > PLAN_INTERVAL:
                    await self.update_plan()
                    await self.publish_plan()
                slot = int(time.time()) // 900
                if slot != self._price_slot:
                    self._price_slot = slot
                    await self.publish(price_only=True)
            except Exception:
                _LOGGER.debug("Live update failed", exc_info=True)
            await asyncio.sleep(LIVE_INTERVAL)

    async def read_live(self) -> None:
        wanted = {f"pv:{cfg['id']}": cfg["sensor"] for cfg in self.settings.arrays if cfg.get("sensor")}
        wanted.update({k: v for k, v in self.settings.data["sensors"].items() if v})
        if not wanted or not self.ha.available:
            self.live = {"at": int(time.time()), "values": {}}
            return

        async def one(entity: str):
            try:
                return await self.ha.state(entity)
            except HAError:
                return None

        states = await asyncio.gather(*(one(e) for e in wanted.values()))
        values = {}
        for (key, entity), st in zip(wanted.items(), states, strict=True):
            values[key] = _live_value(key, entity, st)
            if self.settings.data["invert"].get(key) and values[key]["value"] is not None:
                values[key]["value"] = -values[key]["value"]
        self.live = {"at": int(time.time()), "values": values}
        self.sample_pv()

    def sample_pv(self) -> None:
        """Remember the total PV power for the short-term correction (all measured arrays)."""
        ids = [c["id"] for c in self.settings.arrays if c["kwp"] > 0 and c.get("sensor")]
        live = [self.live.get("values", {}).get(f"pv:{i}") or {} for i in ids]
        # only power sensors: the reading of an energy counter (kWh total) is not a power
        vals = [v.get("value") if v.get("unit") == "W" else None for v in live]
        if ids and all(v is not None for v in vals):
            self._pv_samples.append((time.time(), max(0.0, sum(vals))))

    def compute_nowcast(self) -> dict | None:
        """Measured PV power of the last hour against the own forecast for it."""
        now = time.time()
        win = [(t, w) for t, w in self._pv_samples if t >= now - 3600]
        if len(win) < 20 or now - win[0][0] < 1800:
            return None
        ids = [c["id"] for c in self.settings.arrays if c["kwp"] > 0 and c.get("sensor")]
        if not ids:
            return None
        fc: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
        n: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        for source, arr, t, wh in self.db.forecasts(int(win[0][0]) // 3600 * 3600, int(now) + 1, "d0"):
            if arr in ids:
                fc[source][t] += wh  # Wh of an hour = mean W in that hour
                n[source][t] += 1
        # relative to the source the plan uses - the factor is applied to exactly that one
        hours = {int(t) // 3600 * 3600 for t, _w in win}
        source = next((s for s in self.pv_order() if all(n[s].get(h) == len(ids) for h in hours)), None)
        if source is None:
            return None
        forecast_w = sum(fc[source][int(t) // 3600 * 3600] for t, _w in win) / len(win)
        actual_w = sum(w for _t, w in win) / len(win)
        factor = learn.nowcast_factor(actual_w, forecast_w)
        return {"factor": factor, "source": source, "actual_w": round(actual_w), "forecast_w": round(forecast_w), "at": int(now)}

    def write_nowcast(self) -> None:
        """Store the corrected forecast of the next hours as its own source (for the accuracy check)."""
        now = int(time.time())
        hour = now // 3600 * 3600
        f = (self.nowcast or {}).get("factor") or 1.0
        base = (self.nowcast or {}).get("source") or learn.PV_SOURCE
        # PV arrays only: the own load forecast has the same source key ("ep") on the series "base"
        ids = {c["id"] for c in self.settings.arrays if c["kwp"] > 0}
        rows = []
        for source, arr, t, wh in self.db.forecasts(hour + 3600, hour + 3600 * len(learn.NOWCAST_WEIGHTS), "d0"):
            if source == base and arr in ids:
                w = learn.NOWCAST_WEIGHTS[(t - hour) // 3600]
                rows.append((learn.NOWCAST_SOURCE, arr, t, "d0", round(wh * (1 + (f - 1) * w), 1), now))
        self.db.put_forecast(rows)

    # ------------------------------------------------------------------- views
    def price_slots(self, start: int, end: int) -> list[dict]:
        tariff = self.settings.data["tariff"]
        return [
            {"ts": ts, "dur": dur, "spot": round(spot / 10, 3), "price": round(prices.end_price(spot, tariff), 2)}
            for ts, dur, spot in self.db.prices(start, end)
        ]

    def current_price(self, now: float | None = None) -> dict | None:
        now = now or time.time()
        for slot in self.price_slots(int(now) - 3600, int(now) + 1):
            if slot["ts"] <= now < slot["ts"] + slot["dur"]:
                return slot
        return None

    def accuracy(self, days: int, horizon: str, series: str, common: bool) -> dict:
        key = (days, horizon, series, common)
        cached = self._acc_cache.get(key)
        if cached and time.time() - cached[0] < 600:
            return cached[1]
        now = int(time.time())
        end = self.midnight(now)  # complete days only
        start = end - days * 86400
        cfgs = self.settings.arrays
        if series == learn.BASE_SERIES:
            ids = [learn.BASE_SERIES]
        else:
            ids = [c["id"] for c in cfgs if c["kwp"] > 0 and c.get("sensor")]
        ds = analysis.Dataset(self.db.forecasts(start, end, horizon), self.db.actuals(start, end), ids, self.tz)
        if series == learn.BASE_SERIES:
            series = analysis.TOTAL
        classes = {}
        loc = self.location
        if loc and ids and ids != [learn.BASE_SERIES]:
            arrays = [to_array(c) for c in cfgs if c["id"] in ids]
            if series != analysis.TOTAL:
                arrays = [a for a in arrays if a.id == series]
            classes = analysis.day_classes(ds, arrays, *loc) if series == analysis.TOTAL else {}
        results = analysis.evaluate(ds, series, classes, common)
        for r in results:
            r["label"] = source_label(r["source"])
        out = {
            "results": results,
            "daily": analysis.daily_series(ds, series),
            "classes": classes,
            "start": start,
            "end": end,
            "labels": {s: source_label(s) for s in ds.sources},
            "model": self.model_info,
        }
        self._acc_cache[key] = (time.time(), out)
        return out

    def best_source(self) -> str | None:
        acc = self.accuracy(30, "d1", analysis.TOTAL, False)
        return analysis.best_source(acc["results"])

    def day_view(self, day: str, series: str) -> dict:
        start, end = analysis.day_bounds(day, self.tz)
        hours = list(range(start, end, 3600))
        cfgs = [c for c in self.settings.arrays if c["kwp"] > 0]
        ids = [c["id"] for c in cfgs] if series == analysis.TOTAL else [series]
        clamp = series != learn.BASE_SERIES
        act: dict[int, float] = {}
        complete: dict[int, int] = {}
        for s, t, wh in self.db.actuals(start, end):
            if s in ids:
                act[t] = act.get(t, 0.0) + (max(0.0, wh) if clamp else wh)
                complete[t] = complete.get(t, 0) + 1
        actual = [round(act[t]) if complete.get(t) == len(ids) else None for t in hours]
        if clamp:
            # inverters switch off at night and their sensors have no value then -> 0 while the sun is down
            loc = self.location
            arrays = [arr for cfg, arr in self.arrays() if cfg["id"] in ids and cfg.get("sensor")]
            now = time.time()
            if loc and arrays and len(arrays) == len(ids):
                lat, lon = round(loc[0], 3), round(loc[1], 3)
                actual = [
                    0 if v is None and t + 3600 <= now and all(analysis._clear(t, a, lat, lon) <= 0 for a in arrays) else v
                    for t, v in zip(hours, actual, strict=True)
                ]
        fcs: dict[str, dict[str, list]] = {}
        band: dict[str, dict[str, list]] = {}
        for horizon in ("d0", "d1"):
            per: dict[str, dict[int, list]] = {}
            for source, arr, t, wh in self.db.forecasts(start, end, horizon):
                if arr in ids:
                    per.setdefault(source, {}).setdefault(t, []).append(wh)
            for key, src in (("lo", learn.BAND_LO), ("hi", learn.BAND_HI)):
                vals = per.pop(src, {})
                band.setdefault(horizon, {})[key] = [
                    round(sum(vals[t])) if len(vals.get(t, [])) == len(ids) else None for t in hours
                ]
            for source, vals in per.items():
                fcs.setdefault(source, {})[horizon] = [
                    round(sum(vals[t])) if len(vals.get(t, [])) == len(ids) else None for t in hours
                ]
        return {
            "day": day,
            "hours": hours,
            "actual": actual,
            "forecasts": fcs,
            "band": band,
            "labels": {s: source_label(s) for s in fcs},
            "prices": self.price_slots(start, end),
        }

    def overview(self) -> dict:
        now = time.time()
        today = self.midnight(int(now))
        tomorrow = self.midnight(today + 90000)
        cfgs = [c for c in self.settings.arrays if c["kwp"] > 0]
        ids = [c["id"] for c in cfgs]
        totals: dict[str, dict[str, float]] = {}
        for source, arr, t, wh in self.db.forecasts(today, tomorrow + 90000, "d0"):
            if arr not in ids or source == learn.NAIVE_SOURCE:
                continue
            which = "today" if t < tomorrow else "tomorrow"
            totals.setdefault(source, {"today": 0.0, "tomorrow": 0.0, "rest": 0.0})
            totals[source][which] += wh
            if which == "today" and t + 3600 > now:
                totals[source]["rest"] += wh
        produced = sum(max(0.0, wh) for s, _t, wh in self.db.actuals(today, tomorrow) if s in ids)
        load = {"today": 0.0, "tomorrow": 0.0, "measured": 0.0}
        for source, arr, t, wh in self.db.forecasts(today, tomorrow + 90000, "d0"):
            if source == learn.LOAD_SOURCE and arr == learn.BASE_SERIES:
                load["today" if t < tomorrow else "tomorrow"] += wh
        load["measured"] = sum(wh for s, _t, wh in self.db.actuals(today, tomorrow) if s == learn.BASE_SERIES)
        acc = self.accuracy(30, "d1", analysis.TOTAL, False)["results"] if ids else []
        best = analysis.best_source(acc)
        accuracy = [
            {k: r[k] for k in ("source", "label", "score", "nmae_pct", "day_nmae_pct", "bias_pct", "days")} for r in acc
        ]
        forecasts = [
            {"source": s, "label": source_label(s), **{k: round(v / 1000, 2) for k, v in v.items()}}
            for s, v in sorted(totals.items())
            if s not in (learn.BAND_LO, learn.BAND_HI)
        ]
        pv_range = {
            day: [round(totals.get(learn.BAND_LO, {}).get(day, 0) / 1000, 1), round(totals.get(learn.BAND_HI, {}).get(day, 0) / 1000, 1)]
            for day in ("today", "tomorrow")
        } if learn.BAND_LO in totals else None
        return {
            "version": __version__,
            "demo": self.options.demo,
            "now": int(now),
            "timezone": str(self.tz),
            "location": self.location,
            "arrays": cfgs,
            "live": self.live,
            "price": self.current_price(now),
            "prices": self.price_slots(today, tomorrow + 90000),
            "forecasts": forecasts,
            "best": best,
            "best_label": source_label(best) if best else None,
            "ranking": [r["source"] for r in accuracy],
            "accuracy": accuracy,
            "produced_kwh": round(produced / 1000, 2),
            "pv_range": pv_range,
            "load": {k: round(v / 1000, 2) for k, v in load.items()} if any(load.values()) else None,
            "plan": {k: v for k, v in self.plan.items() if k not in ("steps", "energy")},
            "status": {k: {**v, "label": source_label(k) if not k.startswith("act:") else k[4:]} for k, v in self.status.items()},
            "backfill": self.backfill,
            "ha": self.ha.available,
        }

    # ----------------------------------------------------------------- sensors
    async def publish(self, price_only: bool = False) -> None:
        if not price_only:
            await self.publish_plan()
        if not self.options.publish_sensors or not self.ha.available or self.options.demo:
            return
        now = time.time()
        today = self.midnight(int(now))
        tomorrow = self.midnight(today + 90000)
        slot = self.current_price(now)
        if slot:
            upcoming = [
                {"start": datetime.fromtimestamp(s["ts"], self.tz).isoformat(), "price": s["price"]}
                for s in self.price_slots(int(now) - 900, int(now) + 36 * 3600)
            ]
            day_prices = [s["price"] for s in self.price_slots(today, tomorrow)]
            await self.ha.publish(
                "sensor.energypilot_strompreis",
                slot["price"],
                {
                    "friendly_name": "EnergyPilot Strompreis",
                    "unit_of_measurement": "ct/kWh",
                    "icon": "mdi:currency-eur",
                    "state_class": "measurement",
                    "spot_price": slot["spot"],
                    "today_min": min(day_prices) if day_prices else None,
                    "today_max": max(day_prices) if day_prices else None,
                    "today_average": round(sum(day_prices) / len(day_prices), 2) if day_prices else None,
                    "prices": upcoming,
                },
            )
        if price_only:
            return
        best = await asyncio.to_thread(self.best_source) or "om:best_match"
        cfgs = [c["id"] for c in self.settings.arrays if c["kwp"] > 0]
        per_hour: dict[int, float] = {}
        for source, arr, t, wh in self.db.forecasts(today, tomorrow + 90000, "d0"):
            if source == best and arr in cfgs:
                per_hour[t] = per_hour.get(t, 0.0) + wh
        for name, (a, b) in (("heute", (today, tomorrow)), ("morgen", (tomorrow, tomorrow + 90000))):
            hours = {t: v for t, v in per_hour.items() if a <= t < b}
            await self.ha.publish(
                f"sensor.energypilot_pv_prognose_{name}",
                round(sum(hours.values()) / 1000, 2) if hours else None,
                {
                    "friendly_name": f"EnergyPilot PV-Prognose {name}",
                    "unit_of_measurement": "kWh",
                    "device_class": "energy",
                    "icon": "mdi:solar-power-variant",
                    "source": source_label(best),
                    "hourly": [
                        {"start": datetime.fromtimestamp(t, self.tz).isoformat(), "wh": round(v)}
                        for t, v in sorted(hours.items())
                    ],
                },
            )
        load = {
            t: wh
            for source, arr, t, wh in self.db.forecasts(today, tomorrow + 90000, "d0")
            if source == learn.LOAD_SOURCE and arr == learn.BASE_SERIES
        }
        for name, (a, b) in (("heute", (today, tomorrow)), ("morgen", (tomorrow, tomorrow + 90000))):
            hours = {t: v for t, v in load.items() if a <= t < b}
            if not hours:
                continue
            await self.ha.publish(
                f"sensor.energypilot_verbrauch_prognose_{name}",
                round(sum(hours.values()) / 1000, 2),
                {
                    "friendly_name": f"EnergyPilot Verbrauchsprognose {name}",
                    "unit_of_measurement": "kWh",
                    "device_class": "energy",
                    "icon": "mdi:home-lightning-bolt-outline",
                    "description": "Grundverbrauch ohne E-Auto und Heizstab",
                    "hourly": [
                        {"start": datetime.fromtimestamp(t, self.tz).isoformat(), "wh": round(v)}
                        for t, v in sorted(hours.items())
                    ],
                },
            )
        await self.ha.publish(
            "sensor.energypilot_beste_prognosequelle",
            source_label(best),
            {"friendly_name": "EnergyPilot genaueste Prognosequelle", "icon": "mdi:trophy-outline", "source_id": best},
        )


def _live_value(key: str, entity: str, st: dict | None) -> dict:
    out = {"entity": entity, "value": None, "unit": None, "name": entity}
    if not st:
        return out
    attrs = st.get("attributes") or {}
    out["name"] = attrs.get("friendly_name") or entity
    unit = attrs.get("unit_of_measurement")
    try:
        value = float(st.get("state"))
    except (TypeError, ValueError):
        return out
    if key == "battery_soc":
        out.update(value=value, unit="%")
    elif unit in POWER_UNITS:
        out.update(value=value * POWER_UNITS[unit], unit="W")
    else:
        out.update(value=value, unit=unit)
    return out


def _decision_text(steps: list[dict], tz: ZoneInfo) -> str:
    """One sentence why the current hour is planned the way it is."""
    now = steps[0]
    later = [st for st in steps[1:] if st["soc_end"] < st["soc_start"] - 0.5 and st["price"] > now["price"]]
    peak = max(later, key=lambda st: st["price"]) if later else None
    when = datetime.fromtimestamp(later[0]["ts"], tz).strftime("%H:%M") if later else None
    if now["mode"] == "charge":
        if peak:
            return (f"Jetzt aus dem Netz laden: {now['price']:.1f} ct/kWh ist günstig – die Energie ersetzt ab {when} "
                    f"Netzstrom für bis zu {peak['price']:.1f} ct/kWh.")
        return f"Jetzt aus dem Netz laden: {now['price']:.1f} ct/kWh ist einer der günstigsten Preise im Planungszeitraum."
    if now["mode"] == "hold":
        if peak:
            return (f"Akku halten: Netzstrom kostet jetzt {now['price']:.1f} ct/kWh – die gespeicherte Energie wird ab "
                    f"{when} gebraucht, wenn er bis zu {peak['price']:.1f} ct/kWh kostet.")
        return f"Akku halten: Netzstrom ist jetzt mit {now['price']:.1f} ct/kWh vergleichsweise günstig."
    if now["export"] > 0.05:
        return "Eigenverbrauch: Die Sonne liefert mehr als gebraucht wird – der Überschuss lädt den Akku bzw. wird eingespeist."
    if now["import"] > 0.05:
        return f"Eigenverbrauch: Der Akku ist auf der Reserve – der Rest kommt aus dem Netz ({now['price']:.1f} ct/kWh)."
    return "Eigenverbrauch: Der Akku deckt den Verbrauch – Strom kaufen lohnt sich gerade nicht."
