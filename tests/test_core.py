import calendar
import time
from zoneinfo import ZoneInfo

import pytest
from energypilot.config import Options, Settings, clean_array
from energypilot.db import Database
from energypilot.ha import HomeAssistant
from energypilot.hub import Hub
from energypilot.solar import Array, Plane, clearsky_hour, pv_hour, sun_position
from energypilot.sources import forecastsolar, openmeteo, prices, solcast

from energypilot import analysis

TZ = ZoneInfo("Europe/Berlin")
LAT, LON = 52.52, 13.4


def utc(*args) -> int:
    return calendar.timegm((*args, 0, 0)[:6])


# ------------------------------------------------------------------- solar
def test_sun_position_noon_summer():
    zen, az = sun_position(utc(2026, 6, 21, 11, 10), LAT, LON)
    assert 28 < zen < 31
    assert 175 < az < 186


def test_sun_below_horizon_at_night():
    zen, _ = sun_position(utc(2026, 6, 21, 23, 0), LAT, LON)
    assert zen > 90


def day_energy(a: Array, month: int) -> float:
    d0 = utc(2026, month, 21, 0, 0)
    return sum(clearsky_hour(d0 + h * 3600, a, LAT, LON) for h in range(24)) / 1000


def test_clearsky_yield_plausible():
    south = Array.single("s", 10, 30, 180)
    assert 60 < day_energy(south, 6) < 80
    assert 15 < day_energy(south, 12) < 30


def test_east_west_are_mirrored():
    east = day_energy(Array.single("e", 10, 30, 90), 6)
    west = day_energy(Array.single("w", 10, 30, 270), 6)
    assert east == pytest.approx(west, rel=0.05)


def test_east_array_peaks_in_the_morning():
    east = Array.single("e", 10, 30, 90)
    morning = pv_hour(utc(2026, 6, 21, 6, 0), 600, 150, 20, east, LAT, LON)
    evening = pv_hour(utc(2026, 6, 21, 15, 0), 600, 150, 20, east, LAT, LON)
    assert morning > evening * 1.5


def test_pv_hour_zero_without_light_and_clipping():
    a = Array.single("x", 10, 30, 180, ac_max_kw=3)
    assert pv_hour(utc(2026, 6, 21, 11, 0), 0, 0, 20, a, LAT, LON) == 0
    assert pv_hour(utc(2026, 6, 21, 11, 0), 900, 100, 20, a, LAT, LON) <= 3000 + 1e-6


# ----------------------------------------------------------------- sources
def test_openmeteo_hours_are_shifted_to_start():
    data = {"hourly": {"time": [7200, 10800], "shortwave_radiation": [100, None],
                       "diffuse_radiation": [50, None], "temperature_2m": [10, 11]}}
    hours = openmeteo.parse(data)
    assert len(hours) == 1 and hours[0].start == 3600 and hours[0].ghi == 100


def test_openmeteo_previous_day_suffix():
    data = {"hourly": {"time": [7200], "shortwave_radiation_previous_day1": [80],
                       "diffuse_radiation_previous_day1": [40]}}
    assert openmeteo.parse(data, "_previous_day1")[0].ghi == 80


def test_forecastsolar_period_binning():
    data = {"result": {"2026-09-29T07:04:15+02:00": 0, "2026-09-29T08:00:00+02:00": 156,
                       "2026-09-29T09:00:00+02:00": 558, "2026-09-29T18:49:11+02:00": 82}}
    hours = forecastsolar.parse(data)
    assert hours[utc(2026, 9, 29, 5, 0)] == 156  # 07:00–08:00 local
    assert hours[utc(2026, 9, 29, 6, 0)] == 558
    assert hours[utc(2026, 9, 29, 16, 0)] == 82  # partial sunset period


def test_solcast_half_hours_summed():
    data = {"forecasts": [
        {"pv_estimate": 2.0, "period_end": "2026-09-29T10:30:00.0000000Z", "period": "PT30M"},
        {"pv_estimate": 3.0, "period_end": "2026-09-29T11:00:00.0000000Z", "period": "PT30M"},
    ]}
    assert solcast.parse(data) == {utc(2026, 9, 29, 10, 0): pytest.approx(2500)}


def test_energy_charts_parse_and_end_price():
    rows = prices.parse_energy_charts({"unix_seconds": [0, 900, 1800], "price": [100.0, None, 50.0]})
    assert rows == [(0, 900, 100.0), (1800, 900, 50.0)]
    assert prices.end_price(100.0, {"markup_ct": 20, "vat": 19}) == pytest.approx(35.7)


# ---------------------------------------------------------------- analysis
def build_dataset():
    start = utc(2026, 9, 1, 0, 0) - 7200  # local midnight
    fc, act = [], []
    for d in range(3):
        for h in range(8, 16):
            t = start + d * 86400 + h * 3600
            act += [("a", t, 1000.0), ("b", t, 500.0)]
            fc += [("good", "a", t, 1050.0), ("good", "b", t, 500.0)]
            fc += [("bad", "a", t, 1500.0), ("bad", "b", t, 800.0)]
    fc.append(("partial", "a", start + 10 * 3600, 900.0))
    return analysis.Dataset(fc, act, ["a", "b"], TZ)


def test_accuracy_ranking_and_bias():
    ds = build_dataset()
    res = analysis.evaluate(ds, analysis.TOTAL)
    assert [r["source"] for r in res[:2]] == ["good", "bad"]
    good = res[0]
    assert good["days"] == 3
    assert good["bias_pct"] == pytest.approx(50 / 1500 * 100)
    assert res[1]["bias_pct"] > 40


def test_total_needs_every_array():
    ds = build_dataset()
    # "partial" only has array a – no total, but a per-array value
    assert not ds.pairs("partial", analysis.TOTAL)
    assert ds.pairs("partial", "a")
    assert not ds.days("partial", "a")  # hours missing -> day not comparable


def test_best_source_needs_enough_days():
    ds = build_dataset()
    res = analysis.evaluate(ds, analysis.TOTAL)
    assert analysis.best_source(res, min_days=3) == "good"
    assert analysis.best_source(res, min_days=5) is None


# -------------------------------------------------------------- settings/hub
def test_clean_array_limits_and_entity(tmp_path):
    a = clean_array({"name": " Ost ", "planes": [{"kwp": "8,4", "tilt": 120, "azimuth": 450}, {"kwp": 0}],
                     "sensor": "bad value"})
    assert a["planes"] == [{"kwp": 8.4, "tilt": 90, "azimuth": 90}] and a["kwp"] == 8.4 and a["sensor"] == ""
    s = Settings(tmp_path / "s.json")
    s.upsert_array({"name": "West", "planes": [{"kwp": 5, "azimuth": 270}], "sensor": "sensor.pv_west"})
    s.update({"sources": {"solcast_key": "secret", "models": ["icon_d2", "nope"]}})
    again = Settings(tmp_path / "s.json")
    assert again.arrays[0]["sensor"] == "sensor.pv_west"
    assert again.data["sources"]["models"] == ["icon_d2"]
    assert "solcast_key" not in again.public()["sources"]
    assert again.public()["sources"]["has_solcast_key"]


def test_settings_of_version_010_are_migrated(tmp_path):
    path = tmp_path / "s.json"
    path.write_text('{"arrays": [{"id": "abc", "name": "Alt", "kwp": 6, "tilt": 25, "azimuth": 200, '
                    '"efficiency": 0.9, "ac_max_kw": 0, "sensor": "sensor.pv", "solcast_id": ""}]}', "utf-8")
    arr = Settings(path).arrays[0]
    assert arr["id"] == "abc" and arr["kwp"] == 6
    assert arr["planes"] == [{"kwp": 6, "tilt": 25, "azimuth": 200}]
    assert "tilt" not in arr and "azimuth" not in arr


def test_east_west_array_has_two_humps():
    ew = Array("ew", (Plane(5, 20, 90), Plane(5, 20, 270)))
    day = utc(2026, 6, 21, 0, 0)
    hours = [clearsky_hour(day + h * 3600, ew, LAT, LON) for h in range(24)]
    south = Array.single("s", 10, 20, 180)
    south_hours = [clearsky_hour(day + h * 3600, south, LAT, LON) for h in range(24)]
    # flatter, wider curve: more in the morning, less at noon than the same kWp facing south
    assert hours[4] > south_hours[4] and hours[11] < south_hours[11]
    east_only = sum(clearsky_hour(day + h * 3600, Array.single("e", 5, 20, 90), LAT, LON) for h in range(24))
    west_only = sum(clearsky_hour(day + h * 3600, Array.single("w", 5, 20, 270), LAT, LON) for h in range(24))
    assert sum(hours) == pytest.approx(east_only + west_only, rel=1e-9)


def test_inverter_limit_applies_to_the_sum():
    ew = Array("ew", (Plane(5, 30, 180), Plane(5, 30, 180)), ac_max_kw=6)
    assert pv_hour(utc(2026, 6, 21, 11, 0), 900, 100, 20, ew, LAT, LON) <= 6000 + 1e-6


def test_horizons(tmp_path):
    hub = Hub(Options(), Settings(tmp_path / "s.json"), Database(tmp_path / "x.db"), HomeAssistant())
    now = time.time()
    midnight = hub.midnight(int(now))
    tomorrow = hub.midnight(midnight + 90000)
    assert hub.horizons(tomorrow + 12 * 3600, now) == ["d0", "d1"]
    later_today = int(now // 3600 * 3600) + 3600
    assert hub.horizons(later_today, now) == (["d0"] if later_today < tomorrow else ["d0", "d1"])
    assert hub.horizons(midnight, now) == []


def test_geometry_fit_finds_rotation():
    from energypilot import geometry

    true = Array.single("t", 8, 35, 205)
    weather, actual = [], {}
    for day in range(10):
        d0 = utc(2026, 6, 10 + day, 0, 0)
        for h in range(24):
            t = d0 + h * 3600
            ghi, _el = geometry._clear_ghi(t, LAT, LON)
            weather.append((t, ghi, 0.15 * ghi, 20.0))
            actual[t] = pv_hour(t, ghi, 0.15 * ghi, 20.0, true, LAT, LON) * 0.9  # losses: scale is fitted away
    res = geometry.fit(Array.single("t", 8, 35, 180), weather, actual, LAT, LON)
    assert res["ok"] and res["suggest"]
    assert res["rotation"] in (20, 25, 30)
    assert res["best_error"] < res["current_error"]
    assert abs(res["planes"][0]["azimuth"] - 205) <= 5


def test_band_is_not_a_source_but_weather_models_are():
    fc = [("om:icon_d2", "a", 0, 100.0), ("ep", "a", 0, 90.0), ("ep:lo", "a", 0, 50.0), ("ep:hi", "a", 0, 120.0)]
    ds = analysis.Dataset(fc, [("a", 0, 95.0)], ["a"], TZ)
    assert ds.sources == ["ep", "om:icon_d2"]


def test_prices_never_overlap(tmp_path):
    from energypilot.db import Database

    db = Database(tmp_path / "p.db")
    db.put_prices([(3600 + q * 900, 900, 100.0 + q) for q in range(4)])  # quarter hours
    db.put_prices([(3600, 3600, 50.0)])  # an hourly fallback price for the same hour
    assert db.prices(0, 10 * 3600) == [(3600, 3600, 50.0)]
    db.put_prices([(3600 + q * 900, 900, 80.0) for q in range(4)])  # quarter hours again
    assert [r[1] for r in db.prices(0, 10 * 3600)] == [900] * 4
