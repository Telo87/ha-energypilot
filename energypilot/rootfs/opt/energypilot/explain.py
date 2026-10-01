"""Why the plan looks the way it does - derived from the plan itself, for the "Warum?" dialog.

For every stretch of "hold" or "charge" hours it traces where that energy goes:
the following hours in which the battery discharges, until the next such
stretch. Their price against the price now is the reason for the decision.
Without any such stretch it explains why self-consumption is the best choice,
using the plan without any intervention (battery on its own) for comparison.
"""

from __future__ import annotations

from . import planner


def _avg(pairs: list[tuple[float, float]]) -> float | None:
    """Weighted mean of (value, weight)."""
    w = sum(x for _v, x in pairs)
    return sum(v * x for v, x in pairs) / w if w > 0 else None


def explain(hours: list[planner.Hour], plan: planner.Plan, base: planner.Plan, b: planner.Battery) -> dict:
    lo = b.capacity_kwh * b.min_soc / 100
    steps = plan.steps
    n = len(steps)
    blocks: list[list] = []  # [mode, first, last, gap hours]
    i = 0
    while i < n:
        mode = steps[i].mode
        if mode == "normal":
            i += 1
            continue
        j = i
        while j + 1 < n and steps[j + 1].mode == mode:
            j += 1
        prev = blocks[-1] if blocks else None
        # one strategy, e.g. a night: holding with a few short normal hours in between
        if prev and prev[0] == mode and i - prev[2] <= 3 and all(
                steps[k].mode == "normal" and hours[k].pv_kwh < hours[k].load_kwh for k in range(prev[2] + 1, i)):
            prev[3] += list(range(prev[2] + 1, i))
            prev[2] = j
        else:
            blocks.append([mode, i, j, []])
        i = j + 1

    # where the plan uses the battery more than the battery on its own would: that is where
    # held or bought energy ends up (usually hours in which it would already be empty)
    def out(st):
        return max(0.0, st.soc_start - st.soc_end) * b.eta

    extra = [[k, out(steps[k]) - out(base.steps[k])] for k in range(n)]
    extra = [e for e in extra if e[1] > 0.02 and hours[e[0]].load_kwh > hours[e[0]].pv_kwh]

    items = []
    for mode, i, j, gaps in blocks:
        span = [k for k in range(i, j + 1) if k not in gaps]
        if mode == "charge":
            energy = sum(steps[k].grid for k in span)  # bought for the battery
            target = energy * b.efficiency  # what comes out of it later
        else:  # hold: what the battery would have delivered in these hours
            energy = sum(min(max(0.0, hours[k].load_kwh - hours[k].pv_kwh), b.max_discharge_kw * hours[k].fraction)
                         for k in span)
            target = energy
        use: list[tuple[int, float]] = []
        need = target
        for e in extra:  # first come, first served - later blocks get what is left
            if need <= 0.02:
                break
            if e[0] <= j or e[1] <= 0.02:
                continue
            take = min(e[1], need)
            use.append((e[0], take))
            e[1] -= take
            need -= take
        p_now = _avg([(hours[k].price, hours[k].fraction) for k in span])
        p_use = _avg([(hours[k].price, x) for k, x in use])
        per_kwh = None
        if p_use is not None and p_now is not None:
            per_kwh = p_use * b.efficiency - p_now if mode == "charge" else p_use - p_now
        items.append({
            "mode": mode,
            "start": steps[i].start,
            "end": steps[j].start + 3600,
            "hours": len(span),
            "gaps": [steps[k].start for k in gaps],  # normal hours inside the stretch
            "price_now": round(p_now, 1) if p_now is not None else None,
            "energy_kwh": round(energy, 2),
            "soc_end": round(steps[j].soc_end / b.capacity_kwh * 100),
            "use_start": steps[min(k for k, _x in use)].start if use else None,
            "use_end": steps[max(k for k, _x in use)].start + 3600 if use else None,
            "price_use": round(p_use, 1) if p_use is not None else None,
            "price_use_max": round(max(hours[k].price for k, _x in use), 1) if use else None,
            "gain_ct_per_kwh": round(per_kwh, 1) if per_kwh is not None else None,
        })

    # the battery on its own: when would it be empty, what does grid power cost afterwards?
    empty_i = next((k for k, st in enumerate(base.steps)
                    if st.soc_end <= lo + 0.05 and hours[k].load_kwh > hours[k].pv_kwh), None)
    after = [(hours[k].price, base.steps[k].grid_import) for k in range(empty_i, n)] if empty_i is not None else []
    after = [(p, e) for p, e in after if e > 0.02]
    before = [(hours[k].price, max(0.0, st.soc_start - st.soc_end)) for k, st in enumerate(base.steps[:empty_i or n])]
    before = [(p, e) for p, e in before if e > 0.02]
    cheapest = min(range(n), key=lambda k: hours[k].price) if n else None
    empty_at = None
    if empty_i is not None:
        st, h = base.steps[empty_i], hours[empty_i]
        drop = st.soc_start - st.soc_end
        share = min(1.0, max(0.0, (st.soc_start - lo) / drop)) if drop > 0 else 0.0
        t0 = st.start + (1 - h.fraction) * 3600  # the first hour starts now
        empty_at = int(t0 + share * h.fraction * 3600)
    base_summary = {
        "empty_at": empty_at,
        "price_after": round(_avg(after), 1) if after else None,
        "price_after_max": round(max(p for p, _e in after), 1) if after else None,
        "price_before": round(_avg(before), 1) if before else None,
        "price_before_min": round(min(p for p, _e in before), 1) if before else None,
        "cheapest_at": steps[cheapest].start if cheapest is not None else None,
        "cheapest_price": round(hours[cheapest].price, 1) if cheapest is not None else None,
        # a kWh bought for the battery costs more once the losses are paid for
        "charge_cost": round(hours[cheapest].price / b.efficiency, 1) if cheapest is not None else None,
    }
    if items:
        reason = "plan"
    elif empty_i is None:
        reason = "enough"  # the battery lasts through the whole period
    elif not after or (before and max(p for p, _e in after) <= min(p for p, _e in before) + 0.5):
        reason = "expensive_first"  # the battery is used in the dearer hours anyway
    else:
        reason = "too_small"  # holding / charging would save less than the minimum
    return {"items": items, "baseline": base_summary, "reason": reason, "min_savings_ct": planner.MIN_SAVINGS}
