"""Battery schedule: cheapest plan from forecasts and prices (dynamic programming).

Per hour the battery can run in one of three modes:

- ``normal``: self-consumption – PV surplus charges, deficits are covered by
  the battery (what the battery does on its own)
- ``hold``: the battery is not discharged; energy is saved for later, more
  expensive hours (PV surplus still charges it)
- ``charge``: the battery is charged from the grid (plus PV surplus)

The state is the stored energy in steps of ``STEP_KWH``. For each hour and
state the cheapest way to the end of the horizon is computed backwards; energy
left at the end is valued at a conservative price so the plan does not simply
empty the battery before the horizon ends.
"""

from __future__ import annotations

from dataclasses import dataclass, field

STEP_KWH = 0.1
MIN_GRID_CHARGE = 0.2  # kWh – smaller grid charges are not worth switching the battery
MIN_SAVINGS = 1.0  # ct over the whole horizon – below that the battery just runs on its own
MODES = ("normal", "hold", "charge")


@dataclass
class Battery:
    capacity_kwh: float = 11.0
    min_soc: float = 10.0  # %
    max_soc_grid: float = 100.0  # % – grid charging stops here
    max_charge_kw: float = 3.3
    max_discharge_kw: float = 3.3
    efficiency: float = 0.92  # round trip
    grid_charge: bool = True

    @property
    def eta(self) -> float:
        return self.efficiency ** 0.5  # per direction


@dataclass
class Hour:
    start: int
    pv_kwh: float
    load_kwh: float
    price: float  # ct/kWh (buy)
    fraction: float = 1.0  # share of the hour still ahead (first hour)


@dataclass
class Step:
    start: int
    mode: str
    soc_start: float  # kWh
    soc_end: float
    grid_import: float  # kWh
    grid_export: float
    cost: float  # ct
    grid: float = 0.0  # kWh charged from the grid into the battery


@dataclass
class Plan:
    steps: list[Step] = field(default_factory=list)
    cost: float = 0.0  # ct, optimized
    cost_baseline: float = 0.0  # ct, battery on its own (normal all the time)
    end_value: float = 0.0  # ct per kWh left in the battery at the end

    @property
    def savings(self) -> float:
        return self.cost_baseline - self.cost


def _flows(mode: str, soc: float, target: float | None, h: Hour, b: Battery, feed_in: float, lo: float, hi: float):
    """Energy flows of one hour: (soc_end, import, export, cost, grid charge). ``target`` for grid charging."""
    pv, load, frac = h.pv_kwh, h.load_kwh, h.fraction
    eta = b.eta
    max_c = b.max_charge_kw * frac
    max_d = b.max_discharge_kw * frac
    net = pv - load
    charge_in = 0.0  # energy into the battery (before losses)
    discharge_out = 0.0  # energy delivered by the battery
    if net > 0:  # surplus charges the battery in every mode
        charge_in = min(net, max_c, max(0.0, (hi - soc) / eta))
    elif mode == "normal":
        discharge_out = min(-net, max_d, max(0.0, (soc - lo) * eta))
    grid_charge = 0.0
    if mode == "charge" and target is not None:
        room = min(max_c - charge_in, max(0.0, (target - soc) / eta - charge_in))
        grid_charge = max(0.0, room)
    soc_end = soc + (charge_in + grid_charge) * eta - discharge_out / eta
    balance = load + charge_in + grid_charge - pv - discharge_out
    imp = max(0.0, balance)
    exp = max(0.0, -balance)
    return soc_end, imp, exp, imp * h.price - exp * feed_in, grid_charge


def end_price(hours: list[Hour], b: Battery) -> float:
    """Value (ct/kWh) of energy left in the battery at the end: what it saves later,
    conservatively the lower-middle price of the period."""
    prices = sorted(h.price for h in hours)
    return max(0.0, prices[len(prices) // 3]) * b.eta if prices else 0.0


def simulate(
    hours: list[Hour], soc_kwh: float, b: Battery, feed_in: float,
    modes: list[str] | None = None, targets: list[float | None] | None = None, end_value: float | None = None,
) -> Plan:
    """Run given modes (default: normal) over the hours – e.g. yesterday's recommendations on real data."""
    lo = b.capacity_kwh * b.min_soc / 100
    hi = b.capacity_kwh
    ev = end_price(hours, b) if end_value is None else end_value
    plan = Plan(end_value=ev)
    soc = max(0.0, min(hi, soc_kwh))
    for i, h in enumerate(hours):
        mode = modes[i] if modes else "normal"
        target = targets[i] if targets and mode == "charge" else None
        if mode == "charge" and target is None:
            target = b.capacity_kwh * b.max_soc_grid / 100
        soc_end, imp, exp, cost, g = _flows(mode, soc, target, h, b, feed_in, lo, hi)
        plan.steps.append(Step(h.start, mode, soc, soc_end, imp, exp, cost, g))
        plan.cost += cost
        soc = soc_end
    plan.cost -= max(0.0, soc - lo) * ev
    return plan


def optimize(hours: list[Hour], soc_kwh: float, b: Battery, feed_in: float) -> Plan:
    if not hours:
        return Plan()
    lo = b.capacity_kwh * b.min_soc / 100
    hi = b.capacity_kwh
    grid_hi = b.capacity_kwh * b.max_soc_grid / 100
    n = round(hi / STEP_KWH) + 1
    idx = lambda kwh: max(0, min(n - 1, round(kwh / STEP_KWH)))
    soc_kwh = max(0.0, min(hi, soc_kwh))
    end_value = end_price(hours, b)
    T = len(hours)
    INF = float("inf")
    # value[t][i]: minimal cost from hour t with stored energy i*STEP to the end
    value = [[INF] * n for _ in range(T + 1)]
    choice: list[list[tuple[str, int] | None]] = [[None] * n for _ in range(T)]
    for i in range(n):
        value[T][i] = -max(0.0, i * STEP_KWH - lo) * end_value
    for t in range(T - 1, -1, -1):
        h = hours[t]
        for i in range(n):
            soc = i * STEP_KWH
            best, best_c = INF, None
            options: list[tuple[str, float | None]] = [("normal", None), ("hold", None)]
            if b.grid_charge and soc < grid_hi - 1e-9:
                reach = min(grid_hi, soc + b.max_charge_kw * h.fraction * b.eta)
                k = idx(soc) + 1
                while k * STEP_KWH <= reach + 1e-9:
                    options.append(("charge", k * STEP_KWH))
                    k += 1
            for mode, target in options:
                soc_end, _imp, _exp, cost, g = _flows(mode, soc, target, h, b, feed_in, lo, hi)
                if mode == "charge" and g < MIN_GRID_CHARGE:
                    continue  # rounding artefact, not a real grid charge
                j = idx(soc_end)
                total = cost + value[t + 1][j]
                if total < best - 1e-9:
                    best, best_c = total, (mode, j if target is None else idx(target))
            value[t][i] = best
            choice[t][i] = best_c
    # forward pass with exact energies (the grid only picks decisions)
    plan = Plan(end_value=end_value)
    soc = soc_kwh
    for t, h in enumerate(hours):
        mode, j = choice[t][idx(soc)]
        target = j * STEP_KWH if mode == "charge" else None
        soc_end, imp, exp, cost, grid = _flows(mode, soc, target, h, b, feed_in, lo, hi)
        if mode == "charge" and grid < MIN_GRID_CHARGE / 2:
            mode = "hold"
        if mode == "hold" and (h.pv_kwh >= h.load_kwh or soc <= lo + STEP_KWH):
            mode = "normal"  # nothing to hold back (surplus hour or battery already empty)
        plan.steps.append(Step(h.start, mode, soc, soc_end, imp, exp, cost, grid if mode == "charge" else 0.0))
        plan.cost += cost
        soc = soc_end
    baseline = Plan(end_value=end_value)
    soc = soc_kwh
    for h in hours:
        soc_end, imp, exp, cost, _g = _flows("normal", soc, None, h, b, feed_in, lo, hi)
        baseline.steps.append(Step(h.start, "normal", soc, soc_end, imp, exp, cost))
        baseline.cost += cost
        soc = soc_end
    # compare fairly: both including the value of what is left in the battery
    plan.cost -= max(0.0, plan.steps[-1].soc_end - lo) * end_value
    baseline.cost -= max(0.0, soc - lo) * end_value
    plan.cost_baseline = baseline.cost_baseline = baseline.cost
    # switching the battery around is only worth it if it saves something
    # (this also absorbs rounding effects of the energy steps)
    if plan.cost > baseline.cost - MIN_SAVINGS:
        return baseline
    return plan
