import time

import pytest
from energypilot.config import Options, Settings
from energypilot.db import Database
from energypilot.ha import HomeAssistant
from energypilot.hub import Hub
from energypilot.planner import Battery, Hour, optimize


def day(prices, pv=None, load=0.6):
    pv = pv or [0.0] * len(prices)
    return [Hour(h * 3600, pv[h], load, prices[h]) for h in range(len(prices))]


def test_charges_when_cheap_before_expensive_hours():
    prices = [15.0] * 4 + [50.0] * 6
    plan = optimize(day(prices), 1.1, Battery(), feed_in=8)
    modes = [s.mode for s in plan.steps]
    assert "charge" in modes[:4]
    assert all(m == "normal" for m in modes[4:])
    assert plan.savings > 0
    assert plan.steps[-1].soc_end >= 1.1 - 1e-6  # never below the reserve


def test_no_grid_charging_when_disabled_or_not_worth_it():
    flat = optimize(day([30.0] * 10), 5.0, Battery(), feed_in=8)
    assert "charge" not in [s.mode for s in flat.steps]
    off = optimize(day([15.0] * 4 + [50.0] * 6), 1.1, Battery(grid_charge=False), feed_in=8)
    assert "charge" not in [s.mode for s in off.steps]


def test_holds_battery_for_the_expensive_evening():
    # cheap afternoon, expensive evening, battery can not cover both
    prices = [20.0] * 3 + [60.0] * 3
    plan = optimize(day(prices, load=1.5), 1.1 + 2.0, Battery(grid_charge=False), feed_in=8)
    modes = [s.mode for s in plan.steps]
    assert modes[:3].count("hold") >= 1
    assert plan.cost < plan.cost_baseline


def test_optimized_never_worse_than_doing_nothing():
    import random

    rnd = random.Random(7)
    for _ in range(20):
        prices = [rnd.uniform(5, 60) for _ in range(24)]
        pv = [max(0.0, rnd.gauss(1.5, 1.5)) if 8 <= h <= 17 else 0.0 for h in range(24)]
        plan = optimize(day(prices, pv, load=rnd.uniform(0.3, 1.0)), rnd.uniform(1, 11), Battery(), feed_in=7)
        assert plan.cost <= plan.cost_baseline + 1e-6


def test_battery_runtime(tmp_path):
    hub = Hub(Options(), Settings(tmp_path / "s.json"), Database(tmp_path / "x.db"), HomeAssistant())
    hours = [{"t": 3600 * h, "frac": 1.0, "pv": 0.0, "load": 1.0} for h in range(10)]
    rt = hub.battery_runtime(5.5, hours, 1000, now=0)
    usable = 5.5 - 1.1  # 10 % reserve of 11 kWh
    assert rt["usable_kwh"] == pytest.approx(usable)
    assert rt["now_hours"] == pytest.approx(usable)
    assert rt["empty_at"] is not None and 3 * 3600 < rt["empty_at"] < 5 * 3600  # losses make it a bit shorter
    sunny = [{"t": 3600 * h, "frac": 1.0, "pv": 3.0, "load": 0.5} for h in range(6)]
    rt = hub.battery_runtime(5.5, sunny, 500, now=0)
    assert rt["empty_at"] is None and rt["full_at"] is not None


def test_base_load_subtracts_ev_and_heater(tmp_path):
    settings = Settings(tmp_path / "s.json")
    settings.update({"sensors": {"house": "sensor.haus", "ev": "sensor.auto", "heater": "sensor.heizstab"}})
    hub = Hub(Options(), settings, Database(tmp_path / "x.db"), HomeAssistant())
    acts = {
        "house": {0: 3000.0, 3600: 800.0, 7200: 500.0},
        "ev": {0: 2200.0, 3600: 0.0},  # hour 7200 missing
        "heater": {0: 0.0, 3600: 300.0, 7200: 0.0},
    }
    assert hub.base_load(acts) == {0: 800.0, 3600: 500.0}  # hour without EV value is left out
    negative = {k: {t: -v for t, v in d.items()} if k == "house" else d for k, d in acts.items()}
    assert hub.base_load(negative) == {0: 800.0, 3600: 500.0}  # inverter reports consumption negative


def test_live_values_respect_invert(tmp_path):
    import asyncio

    class FakeHA:
        available = True

        async def state(self, entity):
            return {"state": "-0.74", "attributes": {"unit_of_measurement": "kW"}}

    settings = Settings(tmp_path / "s.json")
    settings.update({"sensors": {"battery_power": "sensor.sonnen_power", "grid": "sensor.netz"},
                     "invert": {"battery_power": True}})
    hub = Hub(Options(), settings, Database(tmp_path / "x.db"), FakeHA())
    asyncio.run(hub.read_live())
    assert hub.live["values"]["battery_power"]["value"] == 740  # sign flipped (-0.74 kW -> +740 W)
    assert hub.live["values"]["grid"]["value"] == -740  # not inverted


def test_simulate_normal_equals_baseline():
    from energypilot.planner import simulate

    hours = day([15.0] * 4 + [50.0] * 6)
    plan = optimize(hours, 1.1, Battery(), feed_in=8)
    assert simulate(hours, 1.1, Battery(), 8).cost == pytest.approx(plan.cost_baseline)
    replay = simulate(hours, 1.1, Battery(), 8, [s.mode for s in plan.steps], [s.soc_end for s in plan.steps])
    assert replay.cost == pytest.approx(plan.cost, abs=1.0)


def test_journal_scores_recommendations(tmp_path):
    import time as _time

    settings = Settings(tmp_path / "s.json")
    arr = settings.upsert_array({"name": "Dach", "planes": [{"kwp": 5}], "sensor": "sensor.pv"})
    hub = Hub(Options(), settings, Database(tmp_path / "x.db"), HomeAssistant())
    start = hub.midnight(int(_time.time())) - 86400  # yesterday
    prices = [15.0] * 4 + [50.0] * 6
    for i, price in enumerate(prices):
        t = start + i * 3600
        mode = "charge" if i == 3 else "normal"
        hub.db.log_plan((t, mode, price, 0.0, 0.6, 10.0, 40.0 if i == 3 else 10.0, 10.0, t))
        hub.db.put_actual([(arr["id"], t, 0.0), ("base", t, 600.0)])
        hub.db.put_prices([(t + q * 900, 900, (price / 1.19) * 10) for q in range(4)])  # end price = spot/10 * 1.19
    j = hub.journal(days=3)
    yesterday = next(d for d in j["days"] if d["complete_hours"])
    assert yesterday["charge_hours"] == 1
    assert yesterday["saved"] > 0  # charging at 15 ct for the 50 ct hours pays off
    assert yesterday["possible"] >= yesterday["saved"] - 0.01


def test_costs_from_grid_energy_and_prices(tmp_path):
    settings = Settings(tmp_path / "s.json")
    settings.update({
        "sensors": {"grid": "sensor.netz", "grid_import": "sensor.bezug", "grid_export": "sensor.einspeisung"},
        "tariff": {"markup_ct": 0, "vat": 0, "feed_in_ct": 8, "base_fee_eur": 3.0,
                   "compare_price_ct": 30, "compare_base_fee_eur": 0},
    })
    hub = Hub(Options(), settings, Database(tmp_path / "x.db"), HomeAssistant())
    start = hub.midnight(1790000000)
    # hour 0: 2 kWh import at 20 ct; hour 1: 1 kWh import at 40 ct and 3 kWh export
    hub.db.put_actual([("grid_in", start, 2000.0), ("grid_out", start, 0.0),
                       ("grid_in", start + 3600, 1000.0), ("grid_out", start + 3600, 3000.0)])
    hub.db.put_prices([(start + q * 900, 900, 200.0) for q in range(4)] + [(start + 3600 + q * 900, 900, 400.0) for q in range(4)])
    res = hub.costs(start, start + 86400)
    day = res["days"][0]
    assert day["import_kwh"] == 3 and day["export_kwh"] == 3
    assert day["energy_eur"] == 0.8  # 2 x 20 ct + 1 x 40 ct
    assert day["feed_in_eur"] == 0.24
    assert day["avg_paid_ct"] == pytest.approx(26.67, abs=0.01)
    assert day["compare_eur"] == 0.9  # 3 kWh at 30 ct, no base fee
    assert res["split"] is True


def test_costs_fall_back_to_signed_grid_value(tmp_path):
    settings = Settings(tmp_path / "s.json")
    settings.update({"sensors": {"grid": "sensor.netz"}, "invert": {"grid": True}})
    hub = Hub(Options(), settings, Database(tmp_path / "x.db"), HomeAssistant())
    start = hub.midnight(1790000000)
    hub.db.put_actual([("grid", start, -1500.0), ("grid", start + 3600, 500.0)])  # inverted: import, then export
    day = hub.costs(start, start + 86400)["days"][0]
    assert day["import_kwh"] == 1.5 and day["export_kwh"] == 0.5


def test_setup_check_finds_wrong_settings(tmp_path):
    import asyncio

    from energypilot import setupcheck

    class FakeHA:
        available = True

        async def states(self):
            unit = {"sensor.pv": "W", "sensor.haus": "W", "sensor.netz": "W", "sensor.soc": "%"}
            return [{"entity_id": e, "state": "100", "attributes": {"unit_of_measurement": u, "state_class": "measurement"}}
                    for e, u in unit.items()]

        async def statistics_metadata(self, ids):
            return {i: {"unit_class": "power"} for i in ids}

    settings = Settings(tmp_path / "s.json")
    arr = settings.upsert_array({"name": "Dach", "planes": [{"kwp": 2}], "sensor": "sensor.pv"})
    settings.update({"location": {"latitude": 52, "longitude": 9},
                     "sensors": {"house": "sensor.haus", "grid": "sensor.netz", "battery_soc": "sensor.soc",
                                 "ev": "sensor.gibt_es_nicht"},
                     "tariff": {"markup_ct": 0}})
    hub = Hub(Options(), settings, Database(tmp_path / "x.db"), FakeHA())
    now = int(time.time()) // 3600 * 3600
    rows = []
    for h in range(1, 11):  # 5 kWh PV per hour on a 2 kWp array, big surplus, grid shows import
        t = now - h * 3600
        rows += [(arr["id"], t, 5000.0), ("house", t, 300.0), ("grid", t, 2000.0)]
    hub.db.put_actual(rows)
    res = asyncio.run(setupcheck.run(hub))
    titles = {c["title"]: c["level"] for g in res["groups"] for c in g["checks"]}
    assert titles["Dach: Messung über der Anlagenleistung"] == "err"
    assert titles["Vorzeichen der Netzleistung vermutlich falsch"] == "err"
    assert titles["Kein Aufschlag eingetragen"] == "warn"
    assert titles["E-Auto / Wallbox: Entität nicht gefunden"] == "err"
    assert res["summary"]["err"] >= 3


def test_journal_counts_night_hours_without_pv_values(tmp_path):
    settings = Settings(tmp_path / "s.json")
    settings.update({"location": {"latitude": 52, "longitude": 9}})
    settings.upsert_array({"name": "Dach", "planes": [{"kwp": 5}], "sensor": "sensor.pv"})
    hub = Hub(Options(), settings, Database(tmp_path / "x.db"), HomeAssistant())
    start = hub.midnight(int(time.time())) - 86400  # yesterday 0-4 o'clock: dark, inverter asleep
    for i in range(4):
        t = start + i * 3600
        hub.db.log_plan((t, "normal", 30.0, 0.0, 0.5, 50.0, 45.0, 50.0, t))
        hub.db.put_actual([("base", t, 500.0)])  # no PV value at all
        hub.db.put_prices([(t + q * 900, 900, 250.0) for q in range(4)])
    day = next(d for d in hub.journal(days=3)["days"] if d["hours"])
    assert day["complete_hours"] == 4
    assert day["pv"] == 0 and day["load"] == 2.0 and day["load_fc"] == 2.0
    assert day["cost_base"] == 0  # battery covers the night: nothing bought, no credit for the energy left


def _hub_with_array(tmp_path):
    settings = Settings(tmp_path / "s.json")
    settings.update({"location": {"latitude": 52, "longitude": 9}})
    settings.upsert_array({"name": "Dach", "planes": [{"kwp": 5}], "sensor": "sensor.pv"})
    return Hub(Options(), settings, Database(tmp_path / "x.db"), HomeAssistant())


def test_day_view_counts_dark_hours_as_zero(tmp_path):
    hub = _hub_with_array(tmp_path)
    day = hub.day_key(time.time() - 86400)
    d = hub.day_view(day, "_total")
    assert d["actual"][2] == 0  # 2 o'clock yesterday: no sensor value, sun down
    assert d["actual"][12] is None  # noon without value stays unknown


def test_nowcast_ignores_energy_counters(tmp_path):
    hub = _hub_with_array(tmp_path)
    aid = hub.settings.arrays[0]["id"]
    hub.live = {"values": {f"pv:{aid}": {"value": 12345.0, "unit": "kWh"}}}
    hub.sample_pv()
    assert not hub._pv_samples
    hub.live = {"values": {f"pv:{aid}": {"value": 1500.0, "unit": "W"}}}
    hub.sample_pv()
    assert len(hub._pv_samples) == 1


def test_nowcast_only_corrects_its_own_source(tmp_path):
    hub = _hub_with_array(tmp_path)
    aid = hub.settings.arrays[0]["id"]
    now = time.time()
    hour = int(now) // 3600 * 3600
    hub.db.put_forecast([("om:best_match", aid, hour + i * 3600, "d0", 1000.0, 0) for i in range(3)])
    hub.nowcast = {"factor": 1.5, "source": "ep"}  # measured against a source the plan does not use
    out, _best, _src = hub.energy_hours(now)
    assert out[1]["pv"] == 1.0
    hub.nowcast = {"factor": 1.5, "source": "om:best_match"}
    out, _best, _src = hub.energy_hours(now)
    assert out[1]["pv"] == pytest.approx(1.0 * (1 + 0.5 * 0.2))


def test_market_average_only_past_quarter_hours(tmp_path):
    settings = Settings(tmp_path / "s.json")
    settings.update({"sensors": {"grid": "sensor.grid"}})
    hub = Hub(Options(), settings, Database(tmp_path / "x.db"), HomeAssistant())
    hour = int(time.time()) // 3600 * 3600 - 3600
    hub.db.put_actual([("grid", hour, 1000.0)])
    hub.db.put_prices([(hour + q * 900, 900, 100.0) for q in range(4)])  # last hour: 10 ct net
    hub.db.put_prices([(hour + 7200 + q * 900, 900, 900.0) for q in range(8)])  # known future: 90 ct net
    res = hub.costs(hour, hour + 5 * 3600)
    assert res["totals"]["avg_market_ct"] == res["totals"]["avg_paid_ct"]
