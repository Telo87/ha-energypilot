"""Diagnostic export: everything needed to recompute forecasts, learning, plans and the journal offline.

A ZIP with
- ``energypilot.db``: a consistent copy of the database (forecasts of every source and horizon,
  measurements, prices, plan log, meta)
- ``settings.json``: the settings without secrets (the Solcast key is removed)
- ``state.json``: what only lives in memory (plan with explanation, live values, live correction,
  learned weights and factors, source status, setup check)
- ``README.txt``: version, time and the extent of the data
"""

from __future__ import annotations

import io
import json
import sqlite3
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from . import __version__

if TYPE_CHECKING:
    from .hub import Hub


def _db_copy(hub: Hub) -> bytes:
    """Online backup of the SQLite database (consistent even while the add-on writes)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "energypilot.db"
        dest = sqlite3.connect(str(path))
        try:
            with hub.db._lock:
                hub.db._conn.backup(dest)
        finally:
            dest.close()
        return path.read_bytes()


def _extent(hub: Hub) -> dict:
    def q(sql: str) -> list:
        return hub.db._read(sql)

    def ts(v):
        return datetime.fromtimestamp(v, hub.tz).isoformat() if v else None

    out = {}
    for table, col in (("forecast", "target"), ("actual", "target"), ("price", "ts"), ("plan_log", "ts"), ("weather", "target")):
        n, lo, hi = q(f"SELECT COUNT(*), MIN({col}), MAX({col}) FROM {table}")[0]
        out[table] = {"rows": n, "from": ts(lo), "to": ts(hi)}
    out["sources"] = {s: {"rows": n, "first": ts(first), "last_issued": ts(last)} for s, n, first, last in hub.db.forecast_sources()}
    out["series"] = {s: {"rows": n, "from": ts(lo), "to": ts(hi)}
                     for s, n, lo, hi in q("SELECT series, COUNT(*), MIN(target), MAX(target) FROM actual GROUP BY series")}
    return out


def build(hub: Hub, check: dict | None) -> tuple[str, bytes]:
    """(file name, ZIP bytes)"""
    now = time.time()
    settings = hub.settings.snapshot()
    settings["sources"]["has_solcast_key"] = bool(settings["sources"].pop("solcast_key", ""))
    state = {
        "version": __version__,
        "exported_at": datetime.fromtimestamp(now, hub.tz).isoformat(),
        "timezone": str(hub.tz),
        "location": hub.location,
        "ha_location": hub.ha_location,
        "country": hub.country,
        "status": hub.status,
        "live": hub.live,
        "nowcast": hub.nowcast,
        "pv_samples_last_hour": [(round(t), round(w)) for t, w in hub._pv_samples if t >= now - 3600],
        "plan": hub.plan,
        "plan_age_s": round(now - hub._plan_at),
        "model_info": hub.model_info,
        "backfill": hub.backfill,
        "forecast_solar": {"last": {k: round(v) for k, v in hub._fs_last.items()}, "pause_until": round(hub._fs_pause_until)},
        "setup_check": check,
    }
    extent = _extent(hub)
    readme = "\n".join([
        f"EnergyPilot {__version__} – Diagnose-Export vom {state['exported_at']}",
        "",
        "energypilot.db  Datenbank: Prognosen aller Quellen (d0 = kurzfristig, d1 = Vortag), Messwerte, Preise, Protokoll",
        "settings.json   Einstellungen (ohne Solcast-Schlüssel)",
        "state.json      Zustand im Speicher: Plan mit Erklärung, Live-Werte, gelernte Gewichte, Status, Einrichtung",
        "",
        "Umfang:",
        json.dumps(extent, indent=2, ensure_ascii=False),
        "",
        "Enthält den Standort und stündliche Verbrauchs- und Erzeugungswerte – nur an Personen weitergeben, denen du das anvertraust.",
    ])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("energypilot.db", _db_copy(hub))
        z.writestr("settings.json", json.dumps(settings, indent=2, ensure_ascii=False))
        z.writestr("state.json", json.dumps(state, indent=2, ensure_ascii=False, default=str))
        z.writestr("README.txt", readme)
    name = f"energypilot-diagnose-{datetime.fromtimestamp(now, hub.tz):%Y%m%d-%H%M}.zip"
    return name, buf.getvalue()
