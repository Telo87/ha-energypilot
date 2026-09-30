import random
from datetime import date, timedelta

from energypilot import learn


def pv_days(n: int, shade_hour: int | None = None, seed: int = 1, cloudy_bias: float = 1.0):
    """Synthetic days: 'good' is close to the truth, 'bad' is noisy and biased.

    ``shade_hour``: a tree shades the array at that hour - only when the sun shines.
    ``cloudy_bias``: both sources overestimate overcast hours by this factor."""
    rnd = random.Random(seed)
    by_day = {}
    start = date(2026, 6, 1)
    for d in range(n):
        day = (start + timedelta(days=d)).isoformat()
        level = rnd.choice([0.9, 0.45, 0.2])
        rows = []
        for hour in range(6, 20):
            clear = 1000 * max(0.0, 1 - abs(hour - 13) / 7)
            truth = clear * level
            actual = truth * (0.5 if hour == shade_hour and level >= 0.9 else 1.0)
            bias = cloudy_bias if level < 0.3 else 1.0
            fc = {
                "good": max(0.0, truth * bias * (1 + rnd.gauss(0, 0.05))),
                "bad": max(0.0, truth * bias * 1.3 * (1 + rnd.gauss(0, 0.3))),
            }
            rows.append(learn.PVHour(d * 86400 + hour * 3600, hour, clear, actual, fc))
        by_day[day] = rows
    return by_day


def train_model(by_day, n=30):
    days = sorted(by_day)[:n]
    return learn.PVModel([h for d in days for h in by_day[d]])


def test_pv_model_prefers_the_better_source():
    model = train_model(pv_days(40))
    assert model.ready
    assert model.weight_share()["good"] > 0.8


def test_shade_correction_applies_only_in_sunshine():
    model = train_model(pv_days(40, shade_hour=8))
    assert model.factor[8, True] < 0.7  # tree shadow at 8 o'clock learned for sunny hours
    assert model.factor[8, False] > 0.85  # (almost) no shadow without direct sun - shrunk a little towards the joint factor
    assert abs(model.factor[13, True] - 1) < 0.1


def test_cloudy_hours_learn_systematic_overestimate():
    model = train_model(pv_days(40, cloudy_bias=1.4))
    assert model.factor[13, False] < 0.9
    assert abs(model.factor[13, True] - 1) < 0.1


def test_band_contains_most_actual_values():
    by_day = pv_days(60, seed=4)
    res = learn.pv_walk_forward(sorted(by_day), by_day)
    hours = [h for d in sorted(by_day)[30:] for h in by_day[d] if h.t in res.forecast and h.actual > 50]
    assert all(res.lo[h.t] <= res.forecast[h.t] <= res.hi[h.t] for h in hours)
    inside = sum(1 for h in hours if res.lo[h.t] <= h.actual <= res.hi[h.t]) / len(hours)
    assert 0.6 <= inside <= 0.98  # P10-P90 should hold roughly 80 %


def test_walk_forward_uses_only_the_past_and_beats_sources():
    by_day = pv_days(45, shade_hour=8)
    days = sorted(by_day)
    res = learn.pv_walk_forward(days, by_day)
    assert res.model is not None
    first_days = days[: learn.MIN_TRAIN_DAYS]
    assert not any(h.t in res.forecast for d in first_days for h in by_day[d])  # nothing to learn from yet
    eval_hours = [h for d in days[20:] for h in by_day[d]]
    err_ep = sum(abs(res.forecast[h.t] - h.actual) for h in eval_hours)
    err_good = sum(abs(h.fc["good"] - h.actual) for h in eval_hours)
    assert err_ep < err_good


def test_nowcast_factor_bounds():
    assert learn.nowcast_factor(500, 1000) == 0.5
    assert learn.nowcast_factor(5000, 1000) == 1.8
    assert learn.nowcast_factor(50, 100) is None  # too little light to judge


def test_load_model_beats_last_week():
    rnd = random.Random(3)
    by_day, temps = {}, {}
    start = date(2026, 1, 5)  # a Monday
    for d in range(70):
        day = start + timedelta(days=d)
        key = day.isoformat()
        temps[key] = 5 + 8 * rnd.random()
        rows = []
        for hour in range(24):
            base = 300 + (400 if 17 <= hour <= 21 else 0) + (250 if day.weekday() >= 5 and 10 <= hour <= 14 else 0)
            base *= 1 + 0.03 * (10 - temps[key])  # more consumption when it is cold
            rows.append(learn.LoadHour(d * 86400 + hour * 3600, key, hour, learn.daytype(day.weekday()),
                                       base * (1 + rnd.gauss(0, 0.15))))
        by_day[key] = rows
    days = sorted(by_day)[35:]
    model, naive = learn.load_walk_forward(days, by_day, temps)
    hours = [h for d in days for h in by_day[d]]
    err_model = sum(abs(model[h.t] - h.actual) for h in hours)
    err_naive = sum(abs(naive[h.t] - h.actual) for h in hours)
    assert err_model < err_naive * 0.85


def test_hour_factors_for_display():
    model = train_model(pv_days(40, shade_hour=8))
    f = model.hour_factors()
    assert set(f) == {"sunny", "cloudy"}
    assert f["sunny"][8] < 0.7
