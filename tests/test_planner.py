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


def test_nowcast_leaves_the_load_forecast_alone(tmp_path):
    hub = _hub_with_array(tmp_path)
    aid = hub.settings.arrays[0]["id"]
    hour = int(time.time()) // 3600 * 3600
    hub.db.put_forecast([("ep", s, hour + 3600, "d0", 800.0, 0) for s in (aid, "base")])
    hub.nowcast = {"factor": 1.5, "source": "ep"}
    hub.write_nowcast()
    rows = {(src, arr) for src, arr, _t, _wh in hub.db.forecasts(hour, hour + 7200, "d0")}
    assert ("nc", aid) in rows and ("nc", "base") not in rows


def test_battery_range_only_while_discharging(tmp_path):
    hub = Hub(Options(), Settings(tmp_path / "s.json"), Database(tmp_path / "x.db"), HomeAssistant())
    hours = [{"t": 3600 * h, "frac": 1.0, "pv": 0.0, "load": 1.0} for h in range(4)]
    usable = 5.5 - 1.1
    rt = hub.battery_runtime(5.5, hours, 3420, now=0, battery_w=2000)  # charging
    assert rt["state"] == "charging" and rt["now_hours"] is None
    rt = hub.battery_runtime(5.5, hours, 3420, now=0, battery_w=10)
    assert rt["state"] == "idle" and rt["now_hours"] is None
    rt = hub.battery_runtime(5.5, hours, 3420, now=0, battery_w=-2200)  # PV covers part of the house
    assert rt["state"] == "discharging" and rt["now_hours"] == pytest.approx(usable / 2.2, abs=0.01)


def test_journal_uses_whole_house_and_measured_grid(tmp_path):
    settings = Settings(tmp_path / "s.json")
    settings.update({"location": {"latitude": 52, "longitude": 9}, "tariff": {"feed_in_ct": 8},
                     "sensors": {"house": "sensor.house", "heater": "sensor.heater", "grid": "sensor.grid"}})
    settings.upsert_array({"name": "Dach", "planes": [{"kwp": 5}], "sensor": "sensor.pv"})
    hub = Hub(Options(), settings, Database(tmp_path / "x.db"), HomeAssistant())
    aid = hub.settings.arrays[0]["id"]
    start = hub.midnight(int(time.time())) - 86400 + 11 * 3600  # yesterday noon
    for i in range(2):
        t = start + i * 3600
        hub.db.log_plan((t, "normal", 30.0, 3.0, 0.5, 100.0, 100.0, 100.0, t))
        hub.db.put_actual([(aid, t, 3000.0), ("house", t, 2500.0), ("heater", t, 2000.0), ("base", t, 500.0),
                           ("grid", t, -500.0)])  # full battery, heater eats the surplus
        hub.db.put_prices([(t + q * 900, 900, 100.0) for q in range(4)])
    day = next(d for d in hub.journal(days=3)["days"] if d["hours"])
    assert day["house"] == 5.0 and day["heater"] == 4.0 and day["load"] == 1.0
    real, base = day["bills"]["real"], day["bills"]["base"]
    assert real["export_kwh"] == 1.0 and real["import_kwh"] == 0
    assert base["export_kwh"] == pytest.approx(1.0)  # the simulation now sees the heater, too
    assert day["cost_real"] == pytest.approx(-0.08)


def test_surplus_heater_never_empties_the_battery(tmp_path):
    settings = Settings(tmp_path / "s.json")
    settings.update({"location": {"latitude": 52, "longitude": 9}, "tariff": {"feed_in_ct": 8},
                     "sensors": {"house": "sensor.house", "heater": "sensor.heater", "grid": "sensor.grid"}})
    settings.upsert_array({"name": "Dach", "planes": [{"kwp": 5}], "sensor": "sensor.pv"})
    hub = Hub(Options(), settings, Database(tmp_path / "x.db"), HomeAssistant())
    aid = hub.settings.arrays[0]["id"]
    t = hub.midnight(int(time.time())) - 86400 + 12 * 3600
    # half-full battery, 3 kWh PV, 0.5 kWh house plus 2 kWh heating rod that took the export
    hub.db.log_plan((t, "normal", 30.0, 3.0, 0.5, 50.0, 50.0, 50.0, t))
    hub.db.put_actual([(aid, t, 3000.0), ("house", t, 2500.0), ("heater", t, 2000.0), ("base", t, 500.0), ("grid", t, 0.0)])
    hub.db.put_prices([(t + q * 900, 900, 100.0) for q in range(4)])
    base = next(d for d in hub.journal(days=3)["days"] if d["hours"])["bills"]["base"]
    # the battery takes the surplus first (up to 3.3 kW); the rod only gets what would have been exported
    assert base["heater_kwh"] == 0 and base["export_kwh"] == 0 and base["import_kwh"] == 0
    hub.settings.update({"devices": {"heater_surplus": False}})
    base = next(d for d in hub.journal(days=3)["days"] if d["hours"])["bills"]["base"]
    assert "heater_kwh" in base and base["import_kwh"] == 0  # as a normal load it eats into the surplus instead


def test_flat_tariff_uses_free_amount_from_the_billing_year_start(tmp_path):
    settings = Settings(tmp_path / "s.json")
    settings.update({"sensors": {"grid": "sensor.grid"}, "tariff": {
        "compare_type": "flat", "flat_fee_eur": 30.0, "flat_free_kwh": 3650.0, "flat_price_ct": 40.0,
        "flat_feed_in_ct": 5.0, "flat_year_start": 1, "feed_in_ct": 8.0}})
    hub = Hub(Options(), settings, Database(tmp_path / "x.db"), HomeAssistant())
    # three measured days: 5.75 kWh import, 1 kWh export each; billing year starts in their month
    first = hub.midnight(hub.midnight(int(time.time())) - 3 * 86400)
    hub.settings.update({"tariff": {"flat_year_start": int(hub.day_key(first)[5:7])}})
    for d in range(3):
        day0 = hub.midnight(first + d * 86400 + 7200)
        hub.db.put_actual([("grid", day0 + h * 3600, 250.0) for h in range(24)])
        hub.db.put_actual([("grid", day0 + 12 * 3600, -1000.0)])  # noon: export instead
    res = hub.costs(first, hub.midnight(first + 3 * 86400 + 7200))
    fl = res["flat"]
    # days before the recording used their share (10 kWh/day), measured days add their import
    assert fl["estimated_kwh"] > 0 and fl["remaining_kwh"] < 3650
    day = res["days"][0]
    assert day["import_kwh"] == 5.75 and day["export_kwh"] == 1.0
    assert fl["remaining_kwh"] > 0  # nothing above the free amount: fee minus the flat's own feed-in
    assert day["compare_total_eur"] == round(30 * 12 / 365 - 1.0 * 0.05, 2)
    # without free energy every kWh costs the price above it
    hub.settings.update({"tariff": {"flat_free_kwh": 0}})
    day = hub.costs(first, hub.midnight(first + 3 * 86400 + 7200))["days"][0]
    assert day["compare_total_eur"] == round(30 * 12 / 365 + 5.75 * 0.40 - 1.0 * 0.05, 2)


def test_feed_in_per_array_split_by_kwp_or_production(tmp_path):
    settings = Settings(tmp_path / "s.json")
    settings.update({"sensors": {"grid": "sensor.grid"}, "tariff": {"feed_in_ct": 8.0}})
    settings.upsert_array({"name": "Dach", "planes": [{"kwp": 6}], "sensor": "sensor.a"})
    settings.upsert_array({"name": "Garage", "planes": [{"kwp": 2}], "sensor": "sensor.b", "feed_in_ct": 12.0})
    hub = Hub(Options(), settings, Database(tmp_path / "x.db"), HomeAssistant())
    a, b = (c["id"] for c in hub.settings.arrays)
    assert hub.feed_in_avg() == pytest.approx((6 * 8 + 2 * 12) / 8)  # 9 ct by kWp
    t = int(time.time()) // 3600 * 3600 - 7200
    hub.db.put_actual([("grid", t, -1000.0), (a, t, 1000.0), (b, t, 3000.0)])  # 1 kWh export, garage produced 3/4
    by_kwp = hub.costs(t, t + 3600)["days"][0]["feed_in_eur"]
    hub.settings.update({"tariff": {"feed_in_split": "production"}})
    by_prod = hub.costs(t, t + 3600)["days"][0]["feed_in_eur"]
    assert by_kwp == pytest.approx(0.09) and by_prod == pytest.approx(0.11)  # 1/4 * 8 + 3/4 * 12
    hub.settings.upsert_array({"id": b, "feed_in_ct": ""})  # back to the tariff's payment
    assert hub.settings.arrays[1]["feed_in_ct"] is None and hub.feed_in_avg() == 8.0


def test_comparison_can_be_switched_off(tmp_path):
    settings = Settings(tmp_path / "s.json")
    settings.update({"sensors": {"grid": "sensor.grid"}, "tariff": {"compare_enabled": False, "compare_type": "flat"}})
    hub = Hub(Options(), settings, Database(tmp_path / "x.db"), HomeAssistant())
    t = int(time.time()) // 3600 * 3600 - 7200
    hub.db.put_actual([("grid", t, 1000.0)])
    res = hub.costs(t, t + 3600)
    assert res["totals"]["savings_eur"] is None and res["flat"] is None
    assert res["tariff"]["compare_enabled"] is False


def test_energy_balance_finds_a_missing_consumer(tmp_path):
    settings = Settings(tmp_path / "s.json")
    settings.update({"sensors": {"house": "sensor.house", "grid": "sensor.grid"}})
    settings.upsert_array({"name": "Dach", "planes": [{"kwp": 5}], "sensor": "sensor.pv"})
    hub = Hub(Options(), settings, Database(tmp_path / "x.db"), HomeAssistant())
    aid = hub.settings.arrays[0]["id"]
    end = hub.midnight(int(time.time()))
    rows = []
    for d in range(7):
        day0 = hub.midnight(end - (d + 1) * 86400 + 7200)
        for h in range(24):
            t = day0 + h * 3600
            pv = 2000.0 if 10 <= h < 16 else 0.0
            rows += [(aid, t, pv), ("house", t, 500.0), ("grid", t, 500.0 - pv)]  # no battery: balances exactly
    hub.db.put_actual(rows)
    bal = hub.energy_balance(7)
    assert len(bal["days"]) == 7 and abs(bal["mean_rest"]) < 0.01
    hub.db.put_actual([("house", t, 300.0) for _a, t, _v in rows[::3]])  # house sensor now misses 200 W
    assert hub.energy_balance(7)["mean_rest"] == pytest.approx(4.8, abs=0.01)


def test_journal_restarts_the_battery_after_a_gap(tmp_path):
    settings = Settings(tmp_path / "s.json")
    settings.update({"location": {"latitude": 52, "longitude": 9}, "sensors": {"house": "sensor.house", "grid": "sensor.grid"}})
    settings.upsert_array({"name": "Dach", "planes": [{"kwp": 8}], "sensor": "sensor.pv"})
    hub = Hub(Options(), settings, Database(tmp_path / "x.db"), HomeAssistant())
    aid = hub.settings.arrays[0]["id"]
    day0 = hub.midnight(int(time.time())) - 86400
    # 9-10 o'clock with an empty battery, gap (restart), 13-14 o'clock: battery measured full
    for h, soc in ((9, 10.0), (10, 30.0), (13, 100.0), (14, 100.0)):
        t = day0 + h * 3600
        hub.db.log_plan((t, "normal", 30.0, 3.0, 0.5, soc, soc, soc, t))
        hub.db.put_actual([(aid, t, 3500.0), ("house", t, 500.0), ("grid", t, -3000.0 if soc == 100.0 else 0.0)])
        hub.db.put_prices([(t + q * 900, 900, 100.0) for q in range(4)])
    day = next(d for d in hub.journal(days=3)["days"] if d["hours"])
    assert day["segments"] == 2
    # the full battery after the gap cannot take the surplus: it is fed in, like measured
    assert day["bills"]["base"]["export_kwh"] == pytest.approx(6.0, abs=0.01)


def test_setup_check_accepts_sleeping_inverters(tmp_path):
    import asyncio

    from energypilot import setupcheck

    settings = Settings(tmp_path / "s.json")
    settings.update({"location": {"latitude": 52, "longitude": 9}})
    settings.upsert_array({"name": "Dach", "planes": [{"kwp": 5}], "sensor": "sensor.pv"})

    class FakeHA(HomeAssistant):
        available = True

        async def states(self):
            return [{"entity_id": "sensor.pv", "state": "unavailable", "attributes": {"unit_of_measurement": "W"}}]

        async def statistics_metadata(self, ids):
            return {i: {"unit_class": "power"} for i in ids}

    hub = Hub(Options(), settings, Database(tmp_path / "x.db"), FakeHA())
    cfg = hub.settings.arrays[0]
    night = hub.midnight(int(time.time())) + 2 * 3600
    noon = hub.midnight(int(time.time())) + 12 * 3600
    assert not hub.daylight(night, cfg) and hub.daylight(noon, cfg)
    real_time = time.time
    try:
        time.time = lambda: night + 600  # 2 o'clock: the inverter sleeps
        rep = asyncio.run(setupcheck.run(hub))
    finally:
        time.time = real_time
    pv = next(g for g in rep["groups"] if g["key"] == "arrays")["checks"]
    assert not any(c["level"] == "warn" and "nicht verfügbar" in c["title"] for c in pv)
    assert any("keine Sonne" in c["text"] for c in pv)


def test_explanation_traces_held_energy_to_the_expensive_hours():
    from energypilot import explain
    from energypilot.planner import simulate

    b = Battery(grid_charge=False)
    hours = day([20.0] * 3 + [60.0] * 3, load=1.5)
    plan = optimize(hours, 1.1 + 2.0, b, feed_in=8)
    why = explain.explain(hours, plan, simulate(hours, 1.1 + 2.0, b, 8), b)
    hold = next(i for i in why["items"] if i["mode"] == "hold")
    assert hold["price_now"] == 20.0 and hold["price_use"] == 60.0 and hold["use_start"] >= 3 * 3600
    assert hold["gain_ct_per_kwh"] == 40.0
    assert why["reason"] == "plan" and why["baseline"]["empty_at"] is not None


def test_explanation_without_intervention():
    from energypilot import explain
    from energypilot.planner import simulate

    b = Battery()
    hours = day([30.0] * 6, load=0.5)  # full battery, flat prices: nothing to gain
    plan = optimize(hours, 11.0, b, feed_in=8)
    why = explain.explain(hours, plan, simulate(hours, 11.0, b, 8), b)
    assert why["items"] == [] and why["reason"] == "enough"
    charge = optimize(day([15.0] * 4 + [50.0] * 6), 1.1, b, feed_in=8)
    why = explain.explain(day([15.0] * 4 + [50.0] * 6), charge, simulate(day([15.0] * 4 + [50.0] * 6), 1.1, b, 8), b)
    item = next(i for i in why["items"] if i["mode"] == "charge")
    assert item["energy_kwh"] > 0.2 and item["price_use"] == 50.0 and item["gain_ct_per_kwh"] == round(50 * 0.92 - 15, 1)


def test_plan_is_stale_after_the_hour_changes(tmp_path):
    hub = Hub(Options(), Settings(tmp_path / "s.json"), Database(tmp_path / "x.db"), HomeAssistant())
    hour = int(time.time()) // 3600 * 3600
    hub._plan_at = time.time()
    assert not hub.plan_stale(60)
    hub._plan_at = hour - 30  # made 30 s before the current hour began
    assert hub.plan_stale(3600)


def test_forecast_solar_once_per_hour_and_pause_after_rate_limit(tmp_path, monkeypatch):
    import asyncio

    from energypilot.sources import SourceError, forecastsolar

    settings = Settings(tmp_path / "s.json")
    settings.update({"location": {"latitude": 52, "longitude": 9}, "sources": {"open_meteo": False, "forecast_solar": True}})
    settings.upsert_array({"name": "Garage", "planes": [{"kwp": 2.6, "azimuth": 90}, {"kwp": 2.6, "azimuth": 270}]})
    hub = Hub(Options(), settings, Database(tmp_path / "x.db"), HomeAssistant())
    calls = []

    async def fake(session, lat, lon, tilt, az, kwp):
        calls.append(az)
        if fake.limit:
            raise SourceError("Abruflimit erreicht", 429)
        return {int(time.time()) // 3600 * 3600 + 3600: 500.0}

    fake.limit = False
    monkeypatch.setattr(forecastsolar, "fetch", fake)
    asyncio.run(hub.fetch_forecasts())
    asyncio.run(hub.fetch_forecasts())  # e.g. a price retry 15 minutes later
    assert len(calls) == 2  # two planes, one fetch in this hour
    hub._fs_last.clear()
    hub.db.set_meta(f"fs_last:{hub.settings.arrays[0]['id']}", "0")
    fake.limit = True
    asyncio.run(hub.fetch_forecasts())
    asyncio.run(hub.fetch_forecasts())
    assert len(calls) == 3 and hub.status["fs"]["ok"] is False  # stopped at the limit, then paused
