"""Solar geometry and a simple physical PV model.

Weather models deliver hourly *averages* of global (GHI) and diffuse (DHI)
irradiance on the horizontal plane. For every array we transpose them onto the
module plane (Hay-Davies), apply temperature and system losses and get the
energy of that hour. The hour is split into sub-steps so sunrise and sunset
hours are handled correctly.

Azimuths are compass degrees: 0 = north, 90 = east, 180 = south, 270 = west.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

SOLAR_CONSTANT = 1361.0  # W/m²
SUBSTEPS = 6  # per hour (10 min)
MIN_COS_ZENITH = 0.0872  # 85° – limits the beam ratio near the horizon


@dataclass(frozen=True)
class Array:
    """One PV array (one orientation)."""

    id: str
    kwp: float
    tilt: float = 30.0  # degrees from horizontal
    azimuth: float = 180.0  # compass degrees
    efficiency: float = 0.88  # inverter + cabling + soiling + mismatch
    ac_max_kw: float = 0.0  # inverter limit, 0 = none
    albedo: float = 0.2
    gamma: float = -0.0037  # power temperature coefficient per K


def sun_position(ts: float, lat: float, lon: float) -> tuple[float, float]:
    """(zenith, azimuth) in degrees for a unix timestamp (NOAA algorithm)."""
    jd = ts / 86400.0 + 2440587.5
    jc = (jd - 2451545.0) / 36525.0
    l0 = (280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360.0
    m = math.radians(357.52911 + jc * (35999.05029 - 0.0001537 * jc))
    ecc = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)
    ctr = (
        math.sin(m) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
        + math.sin(2 * m) * (0.019993 - 0.000101 * jc)
        + math.sin(3 * m) * 0.000289
    )
    omega = math.radians(125.04 - 1934.136 * jc)
    app_long = math.radians(l0 + ctr - 0.00569 - 0.00478 * math.sin(omega))
    obliq = 23 + (26 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60) / 60
    obliq = math.radians(obliq + 0.00256 * math.cos(omega))
    decl = math.asin(math.sin(obliq) * math.sin(app_long))
    y = math.tan(obliq / 2) ** 2
    l0r = math.radians(l0)
    eq_time = 4 * math.degrees(
        y * math.sin(2 * l0r)
        - 2 * ecc * math.sin(m)
        + 4 * ecc * y * math.sin(m) * math.cos(2 * l0r)
        - 0.5 * y * y * math.sin(4 * l0r)
        - 1.25 * ecc * ecc * math.sin(2 * m)
    )
    solar_minutes = ((ts % 86400) / 60.0 + eq_time + 4 * lon) % 1440
    hour_angle = math.radians(solar_minutes / 4 - 180)
    latr = math.radians(lat)
    cos_z = math.sin(latr) * math.sin(decl) + math.cos(latr) * math.cos(decl) * math.cos(hour_angle)
    cos_z = max(-1.0, min(1.0, cos_z))
    zen = math.acos(cos_z)
    sin_z = math.sin(zen)
    if sin_z < 1e-6 or abs(math.cos(latr)) < 1e-6:
        az = 180.0
    else:
        c = (math.sin(latr) * cos_z - math.sin(decl)) / (math.cos(latr) * sin_z)
        az = math.degrees(math.acos(max(-1.0, min(1.0, c))))
        az = (az + 180) % 360 if hour_angle > 0 else (540 - az) % 360
    return math.degrees(zen), az


def extraterrestrial(ts: float) -> float:
    doy = (ts / 86400.0) % 365.25
    return SOLAR_CONSTANT * (1 + 0.033 * math.cos(2 * math.pi * doy / 365.25))


def _poa(ghi: float, bh: float, dhi: float, zen: float, sun_az: float, a: Array, e0: float) -> float:
    """Plane-of-array irradiance (W/m²) for one instant, Hay-Davies model."""
    tilt = math.radians(a.tilt)
    cos_z = math.cos(math.radians(zen))
    cos_aoi = cos_z * math.cos(tilt) + math.sin(math.radians(zen)) * math.sin(tilt) * math.cos(
        math.radians(sun_az - a.azimuth)
    )
    sky = (1 + math.cos(tilt)) / 2
    ground = ghi * a.albedo * (1 - math.cos(tilt)) / 2
    if cos_z <= 0.01 or bh <= 0:
        return dhi * sky + ground
    dni = bh / max(cos_z, MIN_COS_ZENITH)
    ai = min(1.0, max(0.0, dni / e0))  # anisotropy index
    rb = max(cos_aoi, 0.0) / max(cos_z, MIN_COS_ZENITH)
    beam = dni * max(cos_aoi, 0.0)
    if cos_aoi > 0.05:  # incidence angle modifier (ASHRAE, b0 = 0.05)
        beam *= max(0.0, 1 - 0.05 * (1 / cos_aoi - 1))
    else:
        beam = 0.0
    diffuse = dhi * (ai * rb + (1 - ai) * sky)
    return beam + diffuse + ground


def _dc_to_ac(poa: float, temp: float, a: Array) -> float:
    """AC power in W for a plane-of-array irradiance."""
    if poa <= 0:
        return 0.0
    t_cell = temp + poa / 32.0  # NOCT 45 °C
    p = a.kwp * 1000 * poa / 1000 * (1 + a.gamma * (t_cell - 25)) * a.efficiency
    if a.ac_max_kw > 0:
        p = min(p, a.ac_max_kw * 1000)
    return max(0.0, p)


@lru_cache(maxsize=50000)
def sun_steps(start: int, lat: float, lon: float) -> tuple[tuple[float, float], ...]:
    """Sun positions in the middle of each sub-step of an hour."""
    step = 3600 / SUBSTEPS
    return tuple(sun_position(start + (i + 0.5) * step, lat, lon) for i in range(SUBSTEPS))


def pv_hour(start: int, ghi: float, dhi: float, temp: float, a: Array, lat: float, lon: float) -> float:
    """Energy in Wh produced by array ``a`` in the hour starting at ``start``.

    ``ghi``/``dhi`` are the hour's mean irradiance values. They are spread over
    the sub-steps in proportion to the sun's elevation.
    """
    if ghi is None or ghi <= 0:
        return 0.0
    dhi = min(ghi, max(0.0, dhi if dhi is not None else ghi))
    temp = 15.0 if temp is None else temp
    step = 3600 / SUBSTEPS
    pos = sun_steps(int(start), round(lat, 4), round(lon, 4))
    w = [max(math.cos(math.radians(z)), 0.0) for z, _ in pos]
    wsum = sum(w)
    e0 = extraterrestrial(start)
    energy = 0.0
    for (zen, az), wi in zip(pos, w, strict=True):
        if wsum > 0:
            f = wi * SUBSTEPS / wsum
            g, d = ghi * f, dhi * f
        else:  # sun below horizon all hour but light reported – diffuse only
            g, d = ghi, ghi
        energy += _dc_to_ac(_poa(g, g - d, d, zen, az, a, e0), temp, a) * step / 3600
    return energy


def clearsky_hour(start: int, a: Array, lat: float, lon: float) -> float:
    """Wh of an ideal clear hour (Haurwitz model, 15 % diffuse, 20 °C)."""
    step = 3600 / SUBSTEPS
    e0 = extraterrestrial(start)
    energy = 0.0
    for zen, az in sun_steps(int(start), round(lat, 4), round(lon, 4)):
        cz = math.cos(math.radians(zen))
        if cz <= 0.01:
            continue
        ghi = 1098 * cz * math.exp(-0.057 / cz)
        dhi = 0.15 * ghi
        energy += _dc_to_ac(_poa(ghi, ghi - dhi, dhi, zen, az, a, e0), 20.0, a) * step / 3600
    return energy
