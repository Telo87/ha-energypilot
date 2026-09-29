"""Forecast accuracy: compare every source with the measured production."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from .solar import Array, clearsky_hour

TOTAL = "_total"
# day classes by clear-sky index (measured / ideal clear day)
CLASSES = (("sunny", 0.6), ("mixed", 0.3), ("cloudy", 0.0))


def day_key(ts: int, tz: ZoneInfo) -> str:
    return datetime.fromtimestamp(ts, tz).strftime("%Y-%m-%d")


def day_start(day: str, tz: ZoneInfo) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=tz).timestamp())


def day_bounds(day: str, tz: ZoneInfo) -> tuple[int, int]:
    d = datetime.strptime(day, "%Y-%m-%d")  # noqa: DTZ007 – tz is attached below
    return (
        int(d.replace(tzinfo=tz).timestamp()),
        int((d + timedelta(days=1)).replace(tzinfo=tz).timestamp()),
    )


@lru_cache(maxsize=20000)
def _clear(start: int, a: Array, lat: float, lon: float) -> float:
    return clearsky_hour(start, a, lat, lon)


class Dataset:
    """Forecasts and actuals of a period, indexed for evaluation."""

    def __init__(
        self,
        forecasts: list[tuple[str, str, int, float]],
        actuals: list[tuple[str, int, float]],
        array_ids: list[str],
        tz: ZoneInfo,
    ) -> None:
        self.tz = tz
        self.arrays = array_ids
        self.act: dict[str, dict[int, float]] = defaultdict(dict)
        for series, t, wh in actuals:
            if series in array_ids:
                self.act[series][t] = max(0.0, wh)
        self.fc: dict[str, dict[str, dict[int, float]]] = defaultdict(lambda: defaultdict(dict))
        for source, arr, t, wh in forecasts:
            if arr in array_ids:
                self.fc[source][arr][t] = wh
        # totals over all arrays – only hours where every array has a value
        if len(array_ids) > 1:
            common = set.intersection(*(set(self.act[a]) for a in array_ids))
            self.act[TOTAL] = {t: sum(self.act[a][t] for a in array_ids) for t in common}
            for source, per in self.fc.items():
                hours = set.intersection(*(set(per.get(a, {})) for a in array_ids))
                per[TOTAL] = {t: sum(per[a][t] for a in array_ids) for t in hours}
        elif array_ids:
            only = array_ids[0]
            self.act[TOTAL] = self.act[only]
            for per in self.fc.values():
                per[TOTAL] = per.get(only, {})

    @property
    def sources(self) -> list[str]:
        return sorted(self.fc)

    def pairs(self, source: str, series: str = TOTAL) -> dict[int, tuple[float, float]]:
        """hour -> (forecast, actual); night hours with both ≈ 0 are skipped."""
        f = self.fc.get(source, {}).get(series, {})
        a = self.act.get(series, {})
        return {t: (f[t], a[t]) for t in f.keys() & a.keys() if f[t] > 1 or a[t] > 1}

    def days(self, source: str, series: str = TOTAL) -> dict[str, tuple[float, float]]:
        """day -> (forecast, actual) for days where the source covers every productive hour."""
        a = self.act.get(series, {})
        f = self.fc.get(source, {}).get(series, {})
        per_day: dict[str, list] = defaultdict(lambda: [0.0, 0.0, True])
        for t, wh in a.items():
            d = per_day[day_key(t, self.tz)]
            if t in f:
                d[0] += f[t]
                d[1] += wh
            elif wh > 1:
                d[2] = False  # hole in the forecast – day not comparable
        return {day: (v[0], v[1]) for day, v in per_day.items() if v[2] and v[1] > 0}


def metrics(pairs: dict[int, tuple[float, float]], days: dict[str, tuple[float, float]]) -> dict | None:
    if not pairs:
        return None
    err = [f - a for f, a in pairs.values()]
    act = sum(a for _, a in pairs.values())
    fc = sum(f for f, _ in pairs.values())
    abs_sum = sum(abs(e) for e in err)
    out = {
        "hours": len(pairs),
        "days": len(days),
        "actual_kwh": act / 1000,
        "forecast_kwh": fc / 1000,
        "bias_pct": (fc - act) / act * 100 if act > 0 else None,
        "mae_wh": abs_sum / len(err),
        "rmse_wh": math.sqrt(sum(e * e for e in err) / len(err)),
        "nmae_pct": abs_sum / act * 100 if act > 0 else None,
        "day_nmae_pct": None,
        "day_max_err_kwh": None,
    }
    if days:
        d_act = sum(a for _, a in days.values())
        d_err = [abs(f - a) for f, a in days.values()]
        out["day_nmae_pct"] = sum(d_err) / d_act * 100 if d_act > 0 else None
        out["day_max_err_kwh"] = max(d_err) / 1000
    out["score"] = max(0.0, 100 - out["nmae_pct"]) if out["nmae_pct"] is not None else None
    return out


def day_classes(
    ds: Dataset, arrays: list[Array], lat: float, lon: float
) -> dict[str, str]:
    """day -> sunny/mixed/cloudy from the measured clear-sky index of all arrays."""
    act = ds.act.get(TOTAL, {})
    per_day: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for t, wh in act.items():
        clear = sum(_clear(t, a, round(lat, 3), round(lon, 3)) for a in arrays)
        d = per_day[day_key(t, ds.tz)]
        d[0] += wh
        d[1] += clear
    out = {}
    for day, (a, c) in per_day.items():
        if c <= 0:
            continue
        k = a / c
        out[day] = next(name for name, lim in CLASSES if k >= lim)
    return out


def evaluate(
    ds: Dataset, series: str, classes: dict[str, str] | None = None, common: bool = False
) -> list[dict]:
    """Metrics per source, best first. ``common``: only hours every source covers."""
    sources = ds.sources
    restrict: set[int] | None = None
    if common and len(sources) > 1:
        sets = [set(ds.pairs(s, series)) for s in sources]
        sets = [s for s in sets if s]
        restrict = set.intersection(*sets) if sets else set()
    out = []
    for source in sources:
        pairs = ds.pairs(source, series)
        days = ds.days(source, series)
        if restrict is not None:
            pairs = {t: v for t, v in pairs.items() if t in restrict}
            keep = {day_key(t, ds.tz) for t in restrict}
            days = {d: v for d, v in days.items() if d in keep}
        m = metrics(pairs, days)
        if not m:
            continue
        m["source"] = source
        if classes:
            m["by_class"] = {}
            for name, _ in CLASSES:
                sel = {d for d, c in classes.items() if c == name}
                cp = {t: v for t, v in pairs.items() if day_key(t, ds.tz) in sel}
                cd = {d: v for d, v in days.items() if d in sel}
                cm = metrics(cp, cd)
                m["by_class"][name] = (
                    {"nmae_pct": cm["nmae_pct"], "bias_pct": cm["bias_pct"], "days": cm["days"]}
                    if cm
                    else None
                )
        out.append(m)
    out.sort(key=lambda m: (m["nmae_pct"] is None, m["nmae_pct"] or 0))
    return out


def daily_series(ds: Dataset, series: str) -> dict:
    """Per day: measured and forecast totals (kWh) of every source."""
    act_days: dict[str, float] = defaultdict(float)
    for t, wh in ds.act.get(series, {}).items():
        act_days[day_key(t, ds.tz)] += wh
    out = {"days": sorted(act_days), "actual": {}, "sources": {}}
    out["actual"] = {d: round(v / 1000, 2) for d, v in act_days.items()}
    for source in ds.sources:
        out["sources"][source] = {d: round(f / 1000, 2) for d, (f, _) in ds.days(source, series).items()}
    return out


def best_source(results: list[dict], min_days: int = 5) -> str | None:
    ranked = [r for r in results if r["days"] >= min_days and r.get("day_nmae_pct") is not None]
    ranked.sort(key=lambda r: r["day_nmae_pct"])
    return ranked[0]["source"] if ranked else None
