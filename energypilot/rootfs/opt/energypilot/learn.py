"""Learning forecasts: EnergyPilot's own PV forecast and the household base load.

Both are trained walk-forward: the forecast for a day only uses data from the
days before it. The results are stored like any other source, so the accuracy
check compares them honestly with the weather services.

PV ("ep"), per array:
1. Every source is weighted by its past error (inverse mean squared error),
   separately for the expected weather situation (sunny / mixed / cloudy,
   judged from the sources' own forecast relative to a clear sky).
2. The weighted mean is multiplied by a correction factor per hour of day,
   learned separately for sunny and for cloudy hours: shade from a tree or a
   neighbouring house only matters when the sun shines, a systematic bias of
   the weather models also shows under clouds. It learns what no weather
   model knows - shading, clipping, soiling, snow. (A shading map by sun
   position was tried as well; on real data it was not more accurate than
   this, as long as the history covers less than a year.)
3. An uncertainty band (about 80 %) from the distribution of past errors in the
   same weather situation.

Base load ("ep" on series "base"): household consumption without EV and
heating rod - profile per hour for working days and for weekends/public
holidays with recent weeks weighted more, corrected by the day's mean
temperature if consumption depends on it, and pulled half-way towards the
level of the last three days (tuned on real data: both lowered the error).
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

PV_SOURCE = "ep"
LOAD_SOURCE = "ep"
NAIVE_SOURCE = "lw"  # "like last week" - the benchmark for the load forecast
NOWCAST_SOURCE = "nc"  # own forecast corrected with the live production of the last hour
BAND_LO = "ep:lo"  # P10 of the own forecast
BAND_HI = "ep:hi"  # P90
BASE_SERIES = "base"
# never used as input for learning (own results, benchmarks, bands)
LEARNED_SOURCES = (PV_SOURCE, NAIVE_SOURCE, NOWCAST_SOURCE, BAND_LO, BAND_HI)

TRAIN_DAYS = 30
MIN_TRAIN_DAYS = 5
MIN_SOURCE_HOURS = 30
SHRINK_ERR = 24  # hours of "prior" per weather bucket (pulls towards the overall error)
SHRINK_FACTOR = 8  # hours of "prior" per hour-of-day factor (pulls towards 1)
SHRINK_SPLIT = 12  # hours of "prior" for the sunny / cloudy factor (pulls towards the joint one)
SUNNY_K = 0.6  # expected clear-sky index from which an hour counts as sunny
FACTOR_RANGE = (0.3, 1.6)
CLEAR_MARGIN = 1.2  # a forecast never exceeds the clear-sky value by more than this
# quantiles of the past errors for the band; on real data P10/P90 of the training errors contained
# the next days only in ~72 % of the hours (errors vary more than the past suggests) - P7/P93 gives ~80 %
BAND_Q = (0.07, 0.93)
LOAD_TRAIN_DAYS = 28
LOAD_HALF_LIFE = 14.0  # days
LOAD_LEVEL = 0.5  # share of the recent level taken over (1 = fully)
LOAD_LEVEL_DAYS = 3
LOAD_LEVEL_RANGE = (0.7, 1.4)
BUCKETS = ("sunny", "mixed", "cloudy")


def bucket(k: float) -> str:
    return "sunny" if k >= SUNNY_K else "mixed" if k >= 0.3 else "cloudy"


def _quantile(values: list[float], q: float) -> float:
    v = sorted(values)
    if not v:
        return 1.0
    pos = (len(v) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def _bounded(n: int, raw: float, prior: float, strength: float) -> float:
    f = (n * raw + strength * prior) / (n + strength)
    return min(FACTOR_RANGE[1], max(FACTOR_RANGE[0], f))


@dataclass
class PVHour:
    t: int
    hour: int  # local hour of day
    clear: float  # clear-sky energy of this array (Wh)
    actual: float | None
    fc: dict[str, float] = field(default_factory=dict)

    @property
    def expected_k(self) -> float:
        vals = sorted(self.fc.values())
        med = vals[len(vals) // 2] if len(vals) % 2 else (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2
        return med / self.clear if self.clear > 0 else 0.0

    @property
    def sunny(self) -> bool:
        return self.expected_k >= SUNNY_K


class PVModel:
    """Weighted ensemble + hour-of-day correction (sunny / cloudy) + error band."""

    def __init__(self, train: list[PVHour]) -> None:
        rows = [h for h in train if h.actual is not None and h.clear > 0 and h.fc]
        se_all: dict[str, float] = defaultdict(float)
        n_all: dict[str, int] = defaultdict(int)
        se_b: dict[tuple[str, str], float] = defaultdict(float)
        n_b: dict[tuple[str, str], int] = defaultdict(int)
        for h in rows:
            b = bucket(h.expected_k)
            for s, f in h.fc.items():
                e = (f - h.actual) ** 2
                se_all[s] += e
                n_all[s] += 1
                se_b[s, b] += e
                n_b[s, b] += 1
        self.sources = [s for s in n_all if n_all[s] >= MIN_SOURCE_HOURS]
        self.weights: dict[tuple[str, str], float] = {}
        for s in self.sources:
            mse = se_all[s] / n_all[s] + 1.0
            for b in BUCKETS:
                shrunk = (se_b[s, b] + SHRINK_ERR * mse) / (n_b[s, b] + SHRINK_ERR)
                self.weights[s, b] = 1.0 / (shrunk + 1.0)
        self.days = len({h.t // 86400 for h in rows})

        # correction per hour of day: first over all hours, then split into sunny / cloudy
        acc: dict[tuple[int, bool | None], list[float]] = defaultdict(lambda: [0.0, 0.0, 0])
        ens: list[tuple[PVHour, float]] = []
        for h in rows:
            e = self._ensemble(h)
            if e is None:
                continue
            ens.append((h, e))
            for key in ((h.hour, None), (h.hour, h.sunny)):
                acc[key][0] += h.actual
                acc[key][1] += e
                acc[key][2] += 1
        self.factor: dict[tuple[int, bool | None], float] = {}
        for (hour, kind), (a, e, n) in acc.items():
            if kind is None and e >= 50:  # too little energy in this hour to learn from otherwise
                self.factor[hour, None] = _bounded(int(n), a / e, 1.0, SHRINK_FACTOR)
        for (hour, kind), (a, e, n) in acc.items():
            if kind is not None and e >= 50:
                self.factor[hour, kind] = _bounded(int(n), a / e, self.factor.get((hour, None), 1.0), SHRINK_SPLIT)

        # error band: spread of actual / forecast in the same weather situation
        ratios: dict[str, list[float]] = defaultdict(list)
        for h, e in ens:
            pred = e * self._hour_factor(h)
            if pred >= 50:
                ratios[bucket(h.expected_k)].append(h.actual / pred)
        all_r = [r for v in ratios.values() for r in v]
        self.band: dict[str, tuple[float, float]] = {}
        for b in BUCKETS:
            src = ratios[b] if len(ratios.get(b, [])) >= 20 else all_r
            self.band[b] = (_quantile(src, BAND_Q[0]), _quantile(src, BAND_Q[1])) if src else (0.7, 1.2)

    @property
    def ready(self) -> bool:
        return bool(self.sources) and self.days >= MIN_TRAIN_DAYS

    def _ensemble(self, h: PVHour) -> float | None:
        b = bucket(h.expected_k)
        num = den = 0.0
        for s in self.sources:
            if s in h.fc:
                w = self.weights[s, b]
                num += w * h.fc[s]
                den += w
        return num / den if den > 0 else None

    def _hour_factor(self, h: PVHour) -> float:
        return self.factor.get((h.hour, h.sunny), self.factor.get((h.hour, None), 1.0))

    def predict(self, h: PVHour) -> float | None:
        if h.clear <= 0:
            return 0.0
        e = self._ensemble(h)
        if e is None:
            return None
        return max(0.0, min(h.clear * CLEAR_MARGIN, e * self._hour_factor(h)))

    def predict_band(self, h: PVHour) -> tuple[float, float, float] | None:
        """(P10, forecast, P90)"""
        v = self.predict(h)
        if v is None:
            return None
        lo, hi = self.band[bucket(h.expected_k)]
        cap = h.clear * CLEAR_MARGIN
        return max(0.0, min(v, v * lo)), v, (min(max(v, v * hi), cap) if cap > 0 else v)

    def weight_share(self) -> dict[str, float]:
        """Mean weight share per source (for display)."""
        tot: dict[str, float] = defaultdict(float)
        for b in BUCKETS:
            den = sum(self.weights[s, b] for s in self.sources)
            for s in self.sources:
                tot[s] += self.weights[s, b] / den / 3 if den else 0
        return dict(tot)

    def hour_factors(self) -> dict[str, dict[int, float]]:
        """Correction per hour for sunny and cloudy hours (for display)."""
        out: dict[str, dict[int, float]] = {"sunny": {}, "cloudy": {}}
        for (hour, kind), f in sorted(self.factor.items(), key=lambda kv: kv[0][0]):
            if kind is not None:
                out["sunny" if kind else "cloudy"][hour] = round(f, 3)
        return out


@dataclass
class PVResult:
    forecast: dict[int, float] = field(default_factory=dict)
    lo: dict[int, float] = field(default_factory=dict)
    hi: dict[int, float] = field(default_factory=dict)
    model: PVModel | None = None


def pv_walk_forward(days: list[str], by_day: dict[str, list[PVHour]], train_days: int = TRAIN_DAYS) -> PVResult:
    """Forecast every day in ``days`` from the ``train_days`` days before it.

    ``model`` is the one of the last day (the one in use now)."""
    ordered = sorted(by_day)
    out = PVResult()
    model = None
    for day in sorted(days):
        past = [d for d in ordered if d < day][-train_days:]
        model = PVModel([h for d in past for h in by_day[d]])
        if not model.ready:
            continue
        for h in by_day.get(day, []):
            band = model.predict_band(h)
            if band is not None:
                out.lo[h.t], out.forecast[h.t], out.hi[h.t] = band
    out.model = model if model is not None and model.ready else None
    return out


def nowcast_factor(actual_w: float, forecast_w: float) -> float | None:
    """Ratio of the measured to the forecast power of the last hour, bounded."""
    if forecast_w < 150 or actual_w < 0:
        return None
    return min(1.8, max(0.3, actual_w / forecast_w))


# weight of the last hour's deviation for the current hour, +1 h, +2 h - tuned on real data:
# higher weights overreact to passing clouds and made the next hours worse
NOWCAST_WEIGHTS = (0.4, 0.2, 0.1)


# --------------------------------------------------------------- base load
@dataclass
class LoadHour:
    t: int
    day: str
    hour: int
    daytype: int  # 0 = working day, 1 = weekend or public holiday
    actual: float | None


def daytype(weekday: int, holiday: bool = False) -> int:
    """Two day types: separate Saturday / Sunday profiles had too little data and were less accurate."""
    return 1 if holiday or weekday >= 5 else 0


def _easter(y: int) -> date:
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    g = (b - (b + 8) // 25 + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    return date(y, (h + l - 7 * m + 114) // 31, (h + l - 7 * m + 114) % 31 + 1)


def public_holidays(country: str | None, years: list[int]) -> set[date]:
    """Nationwide public holidays (regional ones differ too much to guess)."""
    out: set[date] = set()
    for y in years:
        e = _easter(y)
        if country == "DE":
            out |= {date(y, 1, 1), e - timedelta(2), e + timedelta(1), date(y, 5, 1), e + timedelta(39),
                    e + timedelta(50), date(y, 10, 3), date(y, 12, 25), date(y, 12, 26)}
        elif country == "AT":
            out |= {date(y, 1, 1), date(y, 1, 6), e + timedelta(1), date(y, 5, 1), e + timedelta(39), e + timedelta(50),
                    e + timedelta(60), date(y, 8, 15), date(y, 10, 26), date(y, 11, 1), date(y, 12, 8),
                    date(y, 12, 25), date(y, 12, 26)}
        elif country == "CH":
            out |= {date(y, 1, 1), e + timedelta(39), date(y, 8, 1), date(y, 12, 25)}
    return out


class LoadModel:
    def __init__(self, train: list[LoadHour], temps: dict[str, float], today_index: dict[str, int]) -> None:
        rows = [h for h in train if h.actual is not None]
        self.days = len({h.day for h in rows})
        last = max((today_index[h.day] for h in rows), default=0)
        num: dict[tuple[int, int], float] = defaultdict(float)
        den: dict[tuple[int, int], float] = defaultdict(float)
        num_h: dict[int, float] = defaultdict(float)
        den_h: dict[int, float] = defaultdict(float)
        day_tot: dict[str, float] = defaultdict(float)
        day_w: dict[str, float] = {}
        for h in rows:
            w = 0.5 ** ((last - today_index[h.day]) / LOAD_HALF_LIFE)
            num[h.daytype, h.hour] += w * h.actual
            den[h.daytype, h.hour] += w
            num_h[h.hour] += w * h.actual
            den_h[h.hour] += w
            day_tot[h.day] += h.actual
            day_w[h.day] = w
        self.profile = {k: num[k] / den[k] for k in num if den[k] > 0}
        self.fallback = {k: num_h[k] / den_h[k] for k in num_h if den_h[k] > 0}
        # temperature dependency of the daily total (weighted least squares)
        full = [d for d in day_tot if d in temps]
        self.slope = 0.0
        self.t_ref = 0.0
        self.mean_day = sum(day_tot.values()) / len(day_tot) if day_tot else 0.0
        if len(full) >= 14 and self.mean_day > 0:
            w = [day_w[d] for d in full]
            x = [temps[d] for d in full]
            y = [day_tot[d] for d in full]
            sw = sum(w)
            mx = sum(wi * xi for wi, xi in zip(w, x, strict=True)) / sw
            my = sum(wi * yi for wi, yi in zip(w, y, strict=True)) / sw
            sxx = sum(wi * (xi - mx) ** 2 for wi, xi in zip(w, x, strict=True))
            sxy = sum(wi * (xi - mx) * (yi - my) for wi, xi, yi in zip(w, x, y, strict=True))
            if sxx > 0 and (max(x) - min(x)) >= 3:
                slope = sxy / sxx
                # keep it only if it explains something (|r| >= 0.3)
                syy = sum(wi * (yi - my) ** 2 for wi, yi in zip(w, y, strict=True))
                r = sxy / math.sqrt(sxx * syy) if syy > 0 else 0
                if abs(r) >= 0.3:
                    self.slope, self.t_ref = slope, mx

    @property
    def ready(self) -> bool:
        return self.days >= MIN_TRAIN_DAYS

    def predict(self, h: LoadHour, temp: float | None) -> float | None:
        base = self.profile.get((h.daytype, h.hour), self.fallback.get(h.hour))
        if base is None:
            return None
        if self.slope and temp is not None and self.mean_day > 0:
            f = 1 + self.slope * (temp - self.t_ref) / self.mean_day
            base *= min(1.5, max(0.7, f))
        return max(0.0, base)


def load_walk_forward(
    days: list[str], by_day: dict[str, list[LoadHour]], temps: dict[str, float]
) -> tuple[dict[int, float], dict[int, float]]:
    """(model forecast, "like last week") for every hour of ``days``."""
    ordered = sorted(set(by_day) | set(days))
    index = {d: i for i, d in enumerate(ordered)}
    actual = {h.t: h.actual for hs in by_day.values() for h in hs if h.actual is not None}
    model_out: dict[int, float] = {}
    naive_out: dict[int, float] = {}
    for day in days:
        past = [d for d in ordered if d < day and d in by_day][-LOAD_TRAIN_DAYS:]
        model = LoadModel([h for d in past for h in by_day[d]], temps, index)
        # how the last days ran compared with the model (a guest, holidays, a new appliance ...)
        level = 1.0
        if model.ready:
            act = pred = 0.0
            for d in past[-LOAD_LEVEL_DAYS:]:
                for h in by_day[d]:
                    v = model.predict(h, temps.get(d)) if h.actual is not None else None
                    if v is not None:
                        act += h.actual
                        pred += v
            if pred > 0:
                level = 1 + LOAD_LEVEL * (min(LOAD_LEVEL_RANGE[1], max(LOAD_LEVEL_RANGE[0], act / pred)) - 1)
        for h in by_day.get(day, []):
            if model.ready:
                v = model.predict(h, temps.get(day))
                if v is not None:
                    model_out[h.t] = v * level
            week_ago = actual.get(h.t - 7 * 86400)
            if week_ago is not None:
                naive_out[h.t] = week_ago
    return model_out, naive_out
