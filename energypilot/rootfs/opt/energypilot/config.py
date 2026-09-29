"""Add-on options (Supervisor) and settings changed in the web UI."""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from .solar import Array, Plane

_LOGGER = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("ENERGYPILOT_DATA", "/data"))
OPTIONS_FILE = DATA_DIR / "options.json"
SETTINGS_FILE = DATA_DIR / "settings.json"

# Open-Meteo weather models that are compared by default (all free, no key).
OPEN_METEO_MODELS = {
    "best_match": "Open-Meteo Auto",
    "icon_d2": "DWD ICON-D2",
    "icon_eu": "DWD ICON-EU",
    "ecmwf_ifs025": "ECMWF IFS",
    "gfs_seamless": "NOAA GFS",
    "meteofrance_seamless": "Météo-France",
    "knmi_seamless": "KNMI Harmonie",
    "ukmo_seamless": "UK Met Office",
}
DEFAULT_MODELS = ["best_match", "icon_d2", "icon_eu", "ecmwf_ifs025", "gfs_seamless", "meteofrance_seamless"]


@dataclass
class Options:
    publish_sensors: bool = True
    log_level: str = "info"
    port: int = int(os.environ.get("ENERGYPILOT_PORT", "8099"))
    # Only the Supervisor ingress proxy may talk to us. ENERGYPILOT_ALLOW_ALL=1 for development.
    allow_all: bool = os.environ.get("ENERGYPILOT_ALLOW_ALL") == "1"
    demo: bool = os.environ.get("ENERGYPILOT_DEMO") == "1"


def load_options() -> Options:
    opts = Options()
    try:
        raw = json.loads(OPTIONS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return opts
    except (OSError, ValueError) as err:
        _LOGGER.warning("Could not read %s: %s", OPTIONS_FILE, err)
        return opts
    for key in ("publish_sensors", "log_level"):
        if raw.get(key) is not None:
            setattr(opts, key, raw[key])
    return opts


DEFAULT_SETTINGS: dict = {
    # null = take latitude/longitude from Home Assistant
    "location": {"latitude": None, "longitude": None},
    "arrays": [],
    "sources": {
        "open_meteo": True,
        "models": list(DEFAULT_MODELS),
        "forecast_solar": True,
        "solcast_key": "",
        "solcast_hours": [6, 10, 13, 16],  # local hours; hobbyist accounts have 10 calls/day
    },
    "tariff": {
        "bidding_zone": "DE-LU",
        "markup_ct": 0.0,  # net surcharge on top of the spot price (grid fees, levies, provider)
        "vat": 19.0,
        "feed_in_ct": 0.0,
    },
    # ev / heater: measured separately and subtracted from the house consumption
    "sensors": {"house": "", "grid": "", "battery_soc": "", "battery_power": "", "ev": "", "heater": ""},
    "backfill_days": 90,
    # home battery for the planner (sonnenBatterie etc.)
    "battery": {
        "capacity_kwh": 11.0,
        "min_soc": 10.0,  # % reserve the battery does not go below
        "max_soc_grid": 100.0,  # % – grid charging stops here
        "max_charge_kw": 3.3,
        "max_discharge_kw": 3.3,
        "efficiency": 0.92,  # round trip
        "grid_charge": True,
    },
}
BATTERY_LIMITS = (
    ("capacity_kwh", 0.5, 200), ("min_soc", 0, 90), ("max_soc_grid", 10, 100),
    ("max_charge_kw", 0.1, 50), ("max_discharge_kw", 0.1, 50), ("efficiency", 0.5, 1.0),
)

_ARRAY_DEFAULTS = {
    "name": "",
    # orientations measured by the sensor, e.g. east + west string: [{kwp, tilt, azimuth}]
    "planes": [],
    "kwp": 0.0,  # sum of all planes (derived)
    "efficiency": 0.88,
    "ac_max_kw": 0.0,
    "sensor": "",  # power (W/kW) or energy (Wh/kWh) sensor of this array's inverter
    "solcast_id": "",
}


def _num(value, default: float, lo: float | None = None, hi: float | None = None) -> float:
    try:
        v = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def _entity(value) -> str:
    v = str(value or "").strip()
    return v if re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", v) else ""


MAX_PLANES = 6


def clean_plane(data: dict) -> dict:
    return {
        "kwp": _num(data.get("kwp"), 0.0, 0, 1000),
        "tilt": _num(data.get("tilt"), 30.0, 0, 90),
        "azimuth": _num(data.get("azimuth"), 180.0) % 360,
    }


def clean_array(data: dict, existing: dict | None = None) -> dict:
    arr = dict(existing or _ARRAY_DEFAULTS)
    arr.setdefault("id", uuid.uuid4().hex[:8])
    if "name" in data:
        arr["name"] = str(data["name"] or "").strip()[:40]
    planes = data.get("planes")
    if planes is None and "kwp" in data:  # single orientation (settings of version 0.1.0)
        planes = [{k: data.get(k) for k in ("kwp", "tilt", "azimuth")}]
    if isinstance(planes, list):
        arr["planes"] = [p for p in (clean_plane(p) for p in planes[:MAX_PLANES] if isinstance(p, dict)) if p["kwp"] > 0]
    arr["planes"] = list(arr.get("planes") or [])
    arr["kwp"] = round(sum(p["kwp"] for p in arr["planes"]), 3)
    for legacy in ("tilt", "azimuth"):
        arr.pop(legacy, None)
    if "efficiency" in data:
        arr["efficiency"] = _num(data["efficiency"], arr["efficiency"], 0.5, 1.0)
    if "ac_max_kw" in data:
        arr["ac_max_kw"] = _num(data["ac_max_kw"], arr["ac_max_kw"], 0, 1000)
    if "sensor" in data:
        arr["sensor"] = _entity(data["sensor"])
    if "solcast_id" in data:
        arr["solcast_id"] = re.sub(r"[^a-z0-9-]", "", str(data["solcast_id"] or "").lower())[:40]
    if not arr["name"]:
        arr["name"] = f"PV {arr['id'][:4]}"
    return arr


def to_array(cfg: dict) -> Array:
    return Array(
        id=cfg["id"],
        planes=tuple(Plane(p["kwp"], p["tilt"], p["azimuth"]) for p in cfg["planes"]),
        efficiency=cfg["efficiency"],
        ac_max_kw=cfg["ac_max_kw"],
    )


class Settings:
    """JSON settings in /data, edited in the web UI."""

    def __init__(self, path: Path = SETTINGS_FILE) -> None:
        self._path = path
        self._lock = threading.Lock()
        self.data = copy.deepcopy(DEFAULT_SETTINGS)
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as err:
            _LOGGER.warning("Could not read %s: %s", self._path, err)
            return
        self._merge(raw)

    def _merge(self, raw: dict) -> None:
        for key, default in DEFAULT_SETTINGS.items():
            if key not in raw:
                continue
            if isinstance(default, dict):
                self.data[key].update({k: v for k, v in raw[key].items() if k in default})
            elif key == "arrays":
                self.data["arrays"] = [clean_array(a, {**_ARRAY_DEFAULTS, "id": a.get("id") or uuid.uuid4().hex[:8]}) for a in raw["arrays"]]
            else:
                self.data[key] = raw[key]

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(self._path)

    def snapshot(self) -> dict:
        with self._lock:
            return copy.deepcopy(self.data)

    def public(self) -> dict:
        """Settings for the browser: the Solcast key is never sent back."""
        data = self.snapshot()
        data["sources"]["has_solcast_key"] = bool(data["sources"].pop("solcast_key"))
        return data

    @property
    def arrays(self) -> list[dict]:
        with self._lock:
            return copy.deepcopy(self.data["arrays"])

    def upsert_array(self, data: dict) -> dict:
        with self._lock:
            arrays = self.data["arrays"]
            existing = next((a for a in arrays if a["id"] == data.get("id")), None)
            arr = clean_array(data, existing)
            if existing is None:
                arrays.append(arr)
            else:
                arrays[arrays.index(existing)] = arr
            self._save()
            return dict(arr)

    def delete_array(self, array_id: str) -> bool:
        with self._lock:
            before = len(self.data["arrays"])
            self.data["arrays"] = [a for a in self.data["arrays"] if a["id"] != array_id]
            if len(self.data["arrays"]) == before:
                return False
            self._save()
            return True

    def update(self, values: dict) -> dict:
        """Update the dict sections (location, sources, tariff, sensors)."""
        with self._lock:
            loc = values.get("location")
            if isinstance(loc, dict):
                for key, lo, hi in (("latitude", -90, 90), ("longitude", -180, 180)):
                    if key in loc:
                        v = loc[key]
                        self.data["location"][key] = None if v in (None, "") else _num(v, 0, lo, hi)
            src = values.get("sources")
            if isinstance(src, dict):
                s = self.data["sources"]
                for key in ("open_meteo", "forecast_solar"):
                    if key in src:
                        s[key] = bool(src[key])
                if "models" in src:
                    s["models"] = [m for m in OPEN_METEO_MODELS if m in (src["models"] or [])]
                if src.get("solcast_key") is not None and src["solcast_key"] != "":
                    s["solcast_key"] = str(src["solcast_key"]).strip()
                if src.get("solcast_clear"):
                    s["solcast_key"] = ""
                if "solcast_hours" in src:
                    hours = sorted({int(_num(h, 0, 0, 23)) for h in (src["solcast_hours"] or [])})
                    s["solcast_hours"] = hours[:10]
            tariff = values.get("tariff")
            if isinstance(tariff, dict):
                t = self.data["tariff"]
                if "bidding_zone" in tariff:
                    zone = str(tariff["bidding_zone"] or "").strip().upper()
                    t["bidding_zone"] = zone if re.fullmatch(r"[A-Z0-9-]{2,10}", zone) else "DE-LU"
                for key, hi in (("markup_ct", 200), ("vat", 50), ("feed_in_ct", 100)):
                    if key in tariff:
                        t[key] = _num(tariff[key], t[key], 0, hi)
            sensors = values.get("sensors")
            if isinstance(sensors, dict):
                for key in DEFAULT_SETTINGS["sensors"]:
                    if key in sensors:
                        self.data["sensors"][key] = _entity(sensors[key])
            bat = values.get("battery")
            if isinstance(bat, dict):
                b = self.data["battery"]
                for key, lo, hi in BATTERY_LIMITS:
                    if key in bat:
                        b[key] = _num(bat[key], b[key], lo, hi)
                if "grid_charge" in bat:
                    b["grid_charge"] = bool(bat["grid_charge"])
            if "backfill_days" in values:
                self.data["backfill_days"] = int(_num(values["backfill_days"], 90, 0, 730))
            self._save()
            return copy.deepcopy(self.data)
