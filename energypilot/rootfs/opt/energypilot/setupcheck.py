"""Setup check: is everything EnergyPilot needs configured, available and plausible?

Every check yields a level (ok / info / warn / err), a short title, an
explanation and optionally a link to the setting that fixes it.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from datetime import datetime
from typing import TYPE_CHECKING

from . import learn
from .ha import HAError
from .hub import POWER_UNITS, source_label

if TYPE_CHECKING:
    from .hub import Hub

ENERGY_UNITS = ("Wh", "kWh", "MWh")
LINK = {
    "arrays": "#/settings?tab=arrays",
    "sources": "#/settings?tab=sources",
    "tariff": "#/settings?tab=tariff",
    "battery": "#/settings?tab=battery",
    "sensors": "#/settings?tab=sensors",
}


class Report:
    def __init__(self) -> None:
        self.groups: list[dict] = []

    def group(self, key: str, title: str) -> list[dict]:
        checks: list[dict] = []
        self.groups.append({"key": key, "title": title, "checks": checks})
        return checks

    def result(self) -> dict:
        count = defaultdict(int)
        for g in self.groups:
            for c in g["checks"]:
                count[c["level"]] += 1
        return {"groups": self.groups, "summary": dict(count), "at": int(time.time())}


_DECIMAL = re.compile(r"(?<=\d)\.(?=\d)")


def _c(level: str, title: str, text: str = "", link: str | None = None) -> dict:
    # German decimal comma for all numbers in the texts (entity IDs contain no digit.digit)
    return {"level": level, "title": _DECIMAL.sub(",", title), "text": _DECIMAL.sub(",", text), "link": link}


async def run(hub: Hub) -> dict:
    rep = Report()
    s = hub.settings.data
    sensors, inv, tariff, bat = s["sensors"], s["invert"], s["tariff"], s["battery"]
    now = int(time.time())

    # ------------------------------------------------------------ connection
    conn = rep.group("connection", "Verbindung & Standort")
    states: dict[str, dict] = {}
    meta: dict[str, dict] = {}
    if hub.options.demo:
        conn.append(_c("info", "Demo-Modus", "Es werden synthetische Daten verwendet – die Prüfung der Sensoren ist eingeschränkt."))
        from .demo import demo_entities

        states = {e["entity_id"]: {"state": e["state"], "attributes": {"unit_of_measurement": e["unit"], "state_class": "measurement"}} for e in demo_entities(hub)}
        meta = {e: {"unit_class": "power"} for e in states}
    elif not hub.ha.available:
        conn.append(_c("err", "Keine Verbindung zu Home Assistant", "Das Add-on braucht Zugriff auf die Home-Assistant-API (homeassistant_api)."))
    else:
        try:
            states = {st["entity_id"]: st for st in await hub.ha.states()}
            conn.append(_c("ok", "Home Assistant erreichbar", f"{len(states)} Entitäten"))
        except HAError as err:
            conn.append(_c("err", "Home Assistant nicht erreichbar", str(err)))
        wanted = [e for e in [*(a.get("sensor") for a in s["arrays"]), *sensors.values()] if e]
        if wanted and states:
            try:
                meta = await hub.ha.statistics_metadata(sorted(set(wanted)))
            except HAError as err:
                conn.append(_c("warn", "Statistik-Informationen nicht abrufbar", str(err)))
    if hub.location:
        lat, lon = hub.location
        src = "eigene Angabe" if s["location"].get("latitude") is not None else "aus Home Assistant"
        conn.append(_c("ok", "Standort bekannt", f"{lat:.3f}, {lon:.3f} ({src})"))
    else:
        conn.append(_c("err", "Standort unbekannt", "Ohne Standort gibt es keine Wetterprognosen – in Home Assistant setzen oder hier eintragen.", LINK["sensors"]))

    def sensor_state(entity: str, kinds: tuple[str, ...], label: str, link: str, required: bool) -> tuple[list[dict], dict | None]:
        """existence, availability, unit and statistics of a chosen sensor"""
        out = []
        if not entity:
            if required:
                out.append(_c("err", f"{label}: kein Sensor gewählt", "", link))
            return out, None
        st = states.get(entity)
        if states and st is None:
            out.append(_c("err", f"{label}: Entität nicht gefunden", f"{entity} gibt es in Home Assistant nicht (mehr).", link))
            return out, None
        if st is None:
            return out, None
        attrs = st.get("attributes") or {}
        unit = attrs.get("unit_of_measurement")
        if st.get("state") in ("unavailable", "unknown", None):
            out.append(_c("warn", f"{label}: gerade nicht verfügbar", f"{entity} meldet „{st.get('state')}“.", link))
        kind = "power" if unit in POWER_UNITS else "energy" if unit in ENERGY_UNITS else "percent" if unit == "%" else None
        if kind not in kinds:
            need = " oder ".join({"power": "Leistung (W/kW)", "energy": "Energie (Wh/kWh)", "percent": "Prozent"}[k] for k in kinds)
            out.append(_c("err", f"{label}: falsche Einheit", f"{entity} hat die Einheit „{unit or 'keine'}“, erwartet wird {need}.", link))
        elif kind in ("power", "energy") and meta is not None and states and entity not in meta and not hub.options.demo:
            out.append(_c("warn", f"{label}: keine Langzeitstatistik", f"{entity} hat keine state_class – ohne Statistik kann EnergyPilot keine Verläufe auswerten.", link))
        else:
            out.append(_c("ok", f"{label}", f"{entity} · aktuell {st.get('state')} {unit or ''}".strip()))
        return out, st

    # ------------------------------------------------------------ PV arrays
    pv = rep.group("arrays", "PV-Anlagen")
    arrays = [a for a in s["arrays"]]
    if not arrays:
        pv.append(_c("err", "Keine PV-Anlage angelegt", "Ohne Anlage gibt es keine PV-Prognose.", LINK["arrays"]))
    start30 = hub.midnight(now) - 30 * 86400
    acts: dict[str, dict[int, float]] = defaultdict(dict)
    for series, t, wh in hub.db.actuals(start30, now):
        acts[series][t] = wh
    for a in arrays:
        name = a["name"]
        if a["kwp"] <= 0 or not a["planes"]:
            pv.append(_c("err", f"{name}: keine Leistung eingetragen", "Mindestens eine Teilfläche mit kWp angeben.", LINK["arrays"]))
            continue
        checks, _st = sensor_state(a.get("sensor", ""), ("power", "energy"), f"{name}: Messsensor", LINK["arrays"], False)
        if not a.get("sensor"):
            pv.append(_c("warn", f"{name}: kein Messsensor", "Ohne Messwerte kann die Prognose weder geprüft noch dazulernen.", LINK["arrays"]))
            continue
        pv.extend(checks)
        series = acts.get(a["id"], {})
        if not series:
            pv.append(_c("warn", f"{name}: noch keine Messwerte", "In den letzten 30 Tagen sind keine Stundenwerte angekommen – Sensor und Statistik prüfen.", LINK["arrays"]))
            continue
        last = max(series)
        if now - last > 6 * 3600:
            pv.append(_c("warn", f"{name}: Messwerte veraltet", f"Letzter Stundenwert von {datetime.fromtimestamp(last, hub.tz):%d.%m. %H:%M}.", LINK["arrays"]))
        peak = max(series.values())
        limit = min(a["kwp"], a["ac_max_kw"]) if a.get("ac_max_kw") else a["kwp"]
        ratio = peak / (limit * 1000) if limit else 0
        if ratio > 1.15:
            pv.append(_c("err", f"{name}: Messung über der Anlagenleistung",
                         f"Höchster Stundenwert {peak / 1000:.1f} kWh bei {limit:.2f} kWp – kWp zu klein eingetragen oder der Sensor misst mehr als diese Anlage.", LINK["arrays"]))
        elif ratio < 0.35:
            pv.append(_c("warn", f"{name}: Messung weit unter der Anlagenleistung",
                         f"Höchster Stundenwert der letzten 30 Tage {peak / 1000:.1f} kWh bei {limit:.2f} kWp – kWp zu groß, Sensor misst nur einen Teil, oder starke Verschattung.", LINK["arrays"]))
        else:
            pv.append(_c("ok", f"{name}: Leistung plausibel", f"Höchster Stundenwert {peak / 1000:.1f} kWh bei {limit:.2f} kWp ({ratio * 100:.0f} %)."))

    # ------------------------------------------------------------ sensors
    sen = rep.group("sensors", "Sensoren")
    for key, kinds, label, required in (
        ("house", ("power", "energy"), "Hausverbrauch", True),
        ("grid", ("power",), "Netzleistung", False),
        ("grid_import", ("power", "energy"), "Netzbezug", False),
        ("grid_export", ("power", "energy"), "Einspeisung", False),
        ("battery_soc", ("percent",), "Batterie Ladezustand", True),
        ("battery_power", ("power",), "Batterie Leistung", False),
        ("ev", ("power", "energy"), "E-Auto / Wallbox", False),
        ("heater", ("power", "energy"), "Heizstab", False),
    ):
        checks, _st = sensor_state(sensors.get(key, ""), kinds, label, LINK["sensors"], required)
        sen.extend(checks)
    if not sensors.get("grid") and not sensors.get("grid_import"):
        sen.append(_c("warn", "Kein Netz-Sensor", "Für die Kostenübersicht und die Vorzeichen-Prüfung wird die Netzleistung oder Netzbezug/Einspeisung gebraucht.", LINK["sensors"]))
    if sensors.get("battery_soc"):
        v = (hub.live.get("values", {}).get("battery_soc") or {}).get("value")
        if v is not None and not 0 <= v <= 100:
            sen.append(_c("err", "Batterie Ladezustand unplausibel", f"Aktuell {v} % – erwartet 0–100 %.", LINK["sensors"]))
    # house sign
    house = acts.get("house", {})
    if house and sum(house.values()) < 0 and not inv.get("house"):
        sen.append(_c("warn", "Hausverbrauch negativ", "Der Sensor meldet den Verbrauch mit negativem Vorzeichen – „Richtung umkehren“ anhaken.", LINK["sensors"]))
    # grid sign: in hours with a big PV surplus the grid must show export
    ids = [a["id"] for a in arrays if a.get("sensor") and a["kwp"] > 0]
    surplus_hours = []
    for t, h in house.items():
        if ids and all(t in acts.get(i, {}) for i in ids):
            surplus = sum(max(0.0, acts[i][t]) for i in ids) - abs(h)
            if surplus > bat["max_charge_kw"] * 1000 + 1000:
                surplus_hours.append(t)
    grid = acts.get("grid", {})
    if sensors.get("grid") and grid:
        sign = -1 if inv.get("grid") else 1
        hrs = [t for t in surplus_hours if t in grid]
        if len(hrs) >= 5:
            wrong = sum(1 for t in hrs if grid[t] * sign > 0) / len(hrs)
            if wrong >= 0.7:
                sen.append(_c("err", "Vorzeichen der Netzleistung vermutlich falsch",
                              f"In {len(hrs)} Stunden mit großem PV-Überschuss zeigt die Netzleistung {wrong * 100:.0f} % der Zeit Bezug statt Einspeisung – „Richtung umkehren“ ändern.", LINK["sensors"]))
            elif wrong <= 0.3:
                sen.append(_c("ok", "Vorzeichen der Netzleistung plausibel", f"Bei PV-Überschuss zeigt sie Einspeisung ({len(hrs)} Stunden geprüft)."))
    if sensors.get("grid_export"):
        exp = acts.get("grid_out", {})
        hrs = [t for t in surplus_hours if t in exp]
        if len(hrs) >= 5 and sum(1 for t in hrs if abs(exp[t]) < 100) / len(hrs) >= 0.7:
            sen.append(_c("warn", "Einspeisung bei PV-Überschuss fast null",
                          "In Stunden mit großem Überschuss meldet der Einspeise-Sensor kaum etwas – sind Bezug und Einspeisung vertauscht?", LINK["sensors"]))
    # battery sign (live): with a clear surplus and a battery that is not full it must charge
    live = hub.live.get("values", {})
    bp = (live.get("battery_power") or {}).get("value")
    soc = (live.get("battery_soc") or {}).get("value")
    pv_now = [(live.get(f"pv:{i}") or {}).get("value") for i in ids]
    house_now = (live.get("house") or {}).get("value")
    if bp is not None and soc is not None and ids and all(v is not None for v in pv_now) and house_now is not None:
        surplus_now = sum(pv_now) - abs(house_now)
        if surplus_now > 800 and soc < 90:
            if bp < -200:
                sen.append(_c("err", "Vorzeichen der Batterie-Leistung vermutlich falsch",
                              f"Gerade {surplus_now:.0f} W PV-Überschuss bei {soc:.0f} % Ladezustand, die Batterie zeigt aber Entladen ({bp:.0f} W) – „Richtung umkehren“ ändern.", LINK["sensors"]))
            elif bp > 200:
                sen.append(_c("ok", "Vorzeichen der Batterie-Leistung plausibel", "Bei PV-Überschuss zeigt sie Laden."))
    # EV / heater gaps
    for key, series, label in (("ev", "ev", "E-Auto"), ("heater", "heater", "Heizstab")):
        if sensors.get(key) and house:
            have = acts.get(series, {})
            missing = sum(1 for t in house if t not in have)
            if missing > len(house) * 0.1:
                sen.append(_c("warn", f"{label}: Lücken in den Messwerten",
                              f"In {missing} von {len(house)} Stunden fehlt ein Wert – diese Stunden fehlen im Grundverbrauch.", LINK["sensors"]))

    # ------------------------------------------------------------ prices
    pr = rep.group("tariff", "Strompreis")
    st = hub.status.get("price")
    today_slots = hub.price_slots(hub.midnight(now), hub.midnight(now) + 86400)
    if today_slots:
        pr.append(_c("ok", "Börsenpreise für heute vorhanden", f"{len(today_slots)} Preise, Zone {tariff['bidding_zone']}"))
    else:
        pr.append(_c("err", "Keine Börsenpreise für heute", (st or {}).get("text") or "Gebotszone prüfen.", LINK["tariff"]))
    if datetime.now(hub.tz).hour >= 14:
        tomorrow = hub.midnight(hub.midnight(now) + 90000)
        if not hub.price_slots(tomorrow, tomorrow + 86400):
            pr.append(_c("warn", "Preise für morgen fehlen", "Sie erscheinen normalerweise gegen 13 Uhr – EnergyPilot versucht es alle 15 Minuten erneut."))
    mk = float(tariff["markup_ct"])
    if mk <= 0:
        pr.append(_c("warn", "Kein Aufschlag eingetragen", "Ohne Netzentgelt, Steuern und Umlagen sind alle Preise zu niedrig – mit „Aufschlag aus einem Preis berechnen“ ermitteln.", LINK["tariff"]))
    elif not 5 <= mk <= 30:
        pr.append(_c("warn", "Aufschlag ungewöhnlich", f"{mk:.2f} ct/kWh netto – üblich sind etwa 10–25 ct. Stimmt die Angabe (netto, ohne Börsenpreis)?", LINK["tariff"]))
    else:
        pr.append(_c("ok", "Aufschlag plausibel", f"{mk:.2f} ct/kWh netto"))
    vat = float(tariff["vat"])
    pr.append(_c("ok" if vat in (0, 7, 19, 20, 21, 8.1, 9, 10) else "warn", f"Mehrwertsteuer {vat:g} %", "" if vat else "0 % – nur richtig, wenn der Tarif ohne MwSt abgerechnet wird.", LINK["tariff"]))
    feed = float(tariff["feed_in_ct"])
    if feed <= 0:
        pr.append(_c("info", "Keine Einspeisevergütung eingetragen", "Planung und Kostenübersicht rechnen eingespeisten Strom dann mit 0 ct.", LINK["tariff"]))
    elif feed > 30:
        pr.append(_c("warn", "Einspeisevergütung ungewöhnlich hoch", f"{feed:.2f} ct/kWh – bitte prüfen.", LINK["tariff"]))
    else:
        pr.append(_c("ok", "Einspeisevergütung", f"{feed:.2f} ct/kWh"))
    if not float(tariff.get("base_fee_eur", 0)):
        pr.append(_c("info", "Keine Grundgebühr eingetragen", "Nur für die Kostenübersicht relevant.", LINK["tariff"]))

    # ------------------------------------------------------------ battery
    ba = rep.group("battery", "Batterie")
    cap = float(bat["capacity_kwh"])
    if not sensors.get("battery_soc"):
        ba.append(_c("info", "Keine Batterie eingerichtet", "Ohne Ladezustand gibt es keinen Akku-Fahrplan – nur nötig, wenn ein Speicher vorhanden ist.", LINK["sensors"]))
    else:
        ba.append(_c("ok" if 1 <= cap <= 100 else "warn", f"Kapazität {cap:g} kWh", "" if 1 <= cap <= 100 else "Ungewöhnlicher Wert – nutzbare Kapazität in kWh angeben.", LINK["battery"]))
        for key, label in (("max_charge_kw", "Ladeleistung"), ("max_discharge_kw", "Entladeleistung")):
            v = float(bat[key])
            c_rate = v / cap if cap else 0
            if not 0.1 <= c_rate <= 2:
                ba.append(_c("warn", f"{label} {v:g} kW unplausibel", f"Das entspricht {c_rate:.1f}C – Heimspeicher liegen meist bei 0,3–1C.", LINK["battery"]))
            else:
                ba.append(_c("ok", f"{label} {v:g} kW", ""))
        if float(bat["min_soc"]) >= float(bat["max_soc_grid"]):
            ba.append(_c("err", "Reserve über der Netzlade-Grenze", "Die Reserve muss kleiner sein als „Netzladen bis“.", LINK["battery"]))
        eff = float(bat["efficiency"])
        if not 0.8 <= eff <= 0.98:
            ba.append(_c("warn", f"Wirkungsgrad {eff * 100:.0f} % ungewöhnlich", "Laden und Entladen zusammen liegen meist bei 85–95 %.", LINK["battery"]))

    # ------------------------------------------------------------ forecast & plan
    fc = rep.group("forecast", "Prognose & Planung")
    enabled = s["sources"]["open_meteo"] and s["sources"]["models"] or s["sources"]["forecast_solar"] or s["sources"].get("solcast_key")
    if not enabled:
        fc.append(_c("err", "Keine Prognosequelle aktiv", "", LINK["sources"]))
    for key, stt in sorted(hub.status.items()):
        if key.startswith(("om:", "fs", "sc")):
            if stt["ok"]:
                continue
            fc.append(_c("warn", f"{source_label(key)}: Abruf fehlgeschlagen", stt.get("text", ""), LINK["sources"]))
    if hub.backfill.get("running"):
        fc.append(_c("info", "Archiv wird geladen", hub.backfill.get("text", "")))
    if hub.model_info:
        fc.append(_c("ok", "Eigene PV-Prognose aktiv", f"gelernt für {len(hub.model_info)} Anlage(n)"))
    elif ids:
        fc.append(_c("info", "Eigene PV-Prognose lernt noch", "Sie braucht Messwerte und Prognosen von mindestens 5 Tagen."))
    load_rows = [1 for src, arr, _t, _wh in hub.db.forecasts(now, now + 86400, "d0") if src == learn.LOAD_SOURCE and arr == learn.BASE_SERIES]
    if sensors.get("house"):
        fc.append(_c("ok", "Verbrauchsprognose aktiv", "") if load_rows else _c("info", "Verbrauchsprognose lernt noch", "Sie braucht Messwerte des Hausverbrauchs von mindestens 5 Tagen."))
    plan = hub.plan
    if sensors.get("battery_soc"):
        fc.append(_c("ok", "Akku-Plan wird berechnet", plan.get("label", "")) if plan.get("ok") else _c("warn", "Kein Akku-Plan", plan.get("reason", "")))
    return rep.result()
