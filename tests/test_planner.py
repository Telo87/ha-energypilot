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
