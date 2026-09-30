"""Check an array's orientation against its measurements.

In clear hours the shape of the daily curve mostly depends on where the
modules point: an array facing south-west delivers less in the morning and
more in the afternoon than the same array facing south. For candidate
orientations (rotation and tilt changed together for all planes, so an
east-west roof stays east-west) the production is recalculated from the
weather data and compared with the measurement. A common scale factor is
fitted for every candidate, so wrong kWp or losses do not decide the result -
only the shape of the curve does. Low sun (elevation < 20°) is left out,
because morning and evening shade would otherwise pull the orientation.
"""

from __future__ import annotations

import math
from dataclasses import replace

from .solar import Array, Plane, pv_hour, sun_steps

ROTATIONS = range(-45, 50, 5)  # degrees, applied to all planes
TILT_OFFSETS = range(-20, 25, 5)
MIN_ELEVATION = 20.0
MIN_CLEARNESS = 0.7
MIN_HOURS = 20
MIN_IMPROVEMENT = 5.0  # % – below that the current orientation is kept


def _clear_ghi(start: int, lat: float, lon: float) -> tuple[float, float]:
    """Mean clear-sky GHI (Haurwitz) and mean sun elevation of an hour."""
    ghi = el = 0.0
    steps = sun_steps(int(start), round(lat, 4), round(lon, 4))
    for zen, _az in steps:
        cz = math.cos(math.radians(zen))
        if cz > 0.01:
            ghi += 1098 * cz * math.exp(-0.057 / cz)
        el += 90 - zen
    return ghi / len(steps), el / len(steps)


def _candidate(a: Array, rot: float, dtilt: float) -> Array:
    planes = tuple(Plane(p.kwp, min(90.0, max(0.0, p.tilt + dtilt)), (p.azimuth + rot) % 360) for p in a.planes)
    return replace(a, planes=planes)


def _error(hours: list[tuple[int, float, float, float, float]], a: Array, lat: float, lon: float) -> tuple[float, float]:
    """Relative RMSE after the best common scale factor, and that factor."""
    pred = [pv_hour(t, ghi, dhi, temp, a, lat, lon) for t, ghi, dhi, temp, _act in hours]
    act = [h[4] for h in hours]
    den = sum(p * p for p in pred)
    if den <= 0:
        return float("inf"), 1.0
    scale = sum(p * m for p, m in zip(pred, act, strict=True)) / den
    mse = sum((m - scale * p) ** 2 for p, m in zip(pred, act, strict=True)) / len(act)
    return math.sqrt(mse) / (sum(act) / len(act)), scale


def fit(a: Array, weather: list[tuple[int, float, float, float]], actual: dict[int, float], lat: float, lon: float) -> dict:
    """``weather``: (hour start, GHI, DHI, temperature); ``actual``: hour start -> Wh."""
    hours = []
    for t, ghi, dhi, temp in weather:
        act = actual.get(t)
        if act is None or act <= 0 or ghi is None or ghi < 50:
            continue
        clear, el = _clear_ghi(t, lat, lon)
        if el < MIN_ELEVATION or clear <= 0 or ghi / clear < MIN_CLEARNESS:
            continue
        hours.append((t, ghi, dhi, temp, act))
    out: dict = {"hours": len(hours), "days": len({t // 86400 for t, *_ in hours})}
    if len(hours) < MIN_HOURS:
        out["ok"] = False
        out["reason"] = f"Zu wenige klare Stunden ({len(hours)} von mindestens {MIN_HOURS}) – nach ein paar sonnigen Tagen erneut prüfen."
        return out
    cur_err, cur_scale = _error(hours, a, lat, lon)
    best = (cur_err, 0, 0, cur_scale)
    for rot in ROTATIONS:
        for dt in TILT_OFFSETS:
            if rot == 0 and dt == 0:
                continue
            err, scale = _error(hours, _candidate(a, rot, dt), lat, lon)
            if err < best[0]:
                best = (err, rot, dt, scale)
    err, rot, dt, scale = best
    improvement = (cur_err - err) / cur_err * 100 if cur_err > 0 else 0.0
    cand = _candidate(a, rot, dt)
    out.update(
        ok=True,
        current_error=round(cur_err * 100, 1),
        best_error=round(err * 100, 1),
        improvement=round(improvement, 1),
        rotation=rot,
        tilt_offset=dt,
        suggest=bool(improvement >= MIN_IMPROVEMENT and (rot or dt)),
        planes=[{"kwp": p.kwp, "tilt": p.tilt, "azimuth": p.azimuth} for p in cand.planes],
        current_planes=[{"kwp": p.kwp, "tilt": p.tilt, "azimuth": p.azimuth} for p in a.planes],
        scale=round(scale, 3),
        current_scale=round(cur_scale, 3),
    )
    return out
