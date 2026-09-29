"""Learning forecasts: EnergyPilot's own PV forecast and the household base load.

Both are trained walk-forward: the forecast for a day only uses data from the
days before it. The results are stored like any other source, so the accuracy
check compares them honestly with the weather services.

PV ("ep"), per array:
1. Every source is weighted by its past error (inverse mean squared error),
   separately for the expected weather situation (sunny / mixed / cloudy,
   judged from the sources' own forecast relative to a clear sky).
2. The weighted mean is multiplied by a correction factor per hour of day.
   It learns what no weather model knows: shading in the morning, a tree in
   the evening, clipping, soiling, snow.

Base load ("ep" on series "base"): household consumption without EV and
heating rod – profile per hour and day type with recent weeks weighted more,
corrected by the day's mean temperature if consumption depends on it.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

PV_SOURCE = "ep"
LOAD_SOURCE = "ep"
NAIVE_SOURCE = "lw"  # "like last week" – the benchmark for the load forecast
BASE_SERIES = "base"
LEARNED_SOURCES = (PV_SOURCE, NAIVE_SOURCE)

TRAIN_DAYS = 30
MIN_TRAIN_DAYS = 5
MIN_SOURCE_HOURS = 30
SHRINK_ERR = 24  # hours of "prior" per weather bucket (pulls towards the overall error)
SHRINK_FACTOR = 8  # hours of "prior" per hour-of-day factor (pulls towards 1)
FACTOR_RANGE = (0.3, 1.6)
CLEAR_MARGIN = 1.2  # a forecast never exceeds the clear-sky value by more than this
LOAD_TRAIN_DAYS = 28
LOAD_HALF_LIFE = 14.0  # days


def bucket(k: float) -> str:
    return "sunny" if k >= 0.6 else "mixed" if k >= 0.3 else "cloudy"


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


class PVModel:
    """Weighted ensemble + hour-of-day correction, fitted on past hours."""

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
            for b in ("sunny", "mixed", "cloudy"):
                shrunk = (se_b[s, b] + SHRINK_ERR * mse) / (n_b[s, b] + SHRINK_ERR)
                self.weights[s, b] = 1.0 / (shrunk + 1.0)
        # hour-of-day correction of the ensemble
        a_sum: dict[int, float] = defaultdict(float)
        e_sum: dict[int, float] = defaultdict(float)
        n_h: dict[int, int] = defaultdict(int)
        for h in rows:
            e = self._ensemble(h)
            if e is None:
                continue
            a_sum[h.hour] += h.actual
            e_sum[h.hour] += e
            n_h[h.hour] += 1
        self.factor: dict[int, float] = {}
        for hour, n in n_h.items():
            if e_sum[hour] < 50:  # too little energy in this hour to learn from
                continue
            raw = a_sum[hour] / e_sum[hour]
            f = (n * raw + SHRINK_FACTOR) / (n + SHRINK_FACTOR)
            self.factor[hour] = min(FACTOR_RANGE[1], max(FACTOR_RANGE[0], f))
        self.days = len({h.t // 86400 for h in rows})

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

    def predict(self, h: PVHour) -> float | None:
        if h.clear <= 0:
            return 0.0
        e = self._ensemble(h)
        if e is None:
            return None
        return max(0.0, min(h.clear * CLEAR_MARGIN, e * self.factor.get(h.hour, 1.0)))

    def weight_share(self) -> dict[str, float]:
        """Mean weight share per source (for display)."""
        tot = defaultdict(float)
        for b in ("sunny", "mixed", "cloudy"):
            den = sum(self.weights[s, b] for s in self.sources)
            for s in self.sources:
                tot[s] += self.weights[s, b] / den / 3 if den else 0
        return dict(tot)


def pv_walk_forward(
    days: list[str], by_day: dict[str, list[PVHour]], train_days: int = TRAIN_DAYS
) -> tuple[dict[int, float], PVModel | None]:
    """Forecast every day in ``days`` from the ``train_days`` days before it.

    Returns the forecasts and the model of the last day (the one in use now)."""
    ordered = sorted(by_day)
    out: dict[int, float] = {}
    model = None
    for day in sorted(days):
        past = [d for d in ordered if d < day][-train_days:]
        model = PVModel([h for d in past for h in by_day[d]])
        if not model.ready:
            continue
        for h in by_day.get(day, []):
            v = model.predict(h)
            if v is not None:
                out[h.t] = v
    return out, model if model is not None and model.ready else None


# --------------------------------------------------------------- base load
@dataclass
class LoadHour:
    t: int
    day: str
    hour: int
    daytype: int  # 0 = Mon–Fri, 1 = Sat, 2 = Sun
    actual: float | None


def daytype(weekday: int) -> int:
    return 0 if weekday < 5 else 1 if weekday == 5 else 2


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
        for h in by_day.get(day, []):
            if model.ready:
                v = model.predict(h, temps.get(day))
                if v is not None:
                    model_out[h.t] = v
            week_ago = actual.get(h.t - 7 * 86400)
            if week_ago is not None:
                naive_out[h.t] = week_ago
    return model_out, naive_out
