# EnergyPilot – Dokumentation

EnergyPilot sammelt PV-Prognosen mehrerer Wetterdienste, vergleicht sie mit der tatsächlichen
Erzeugung deiner Anlagen und zeigt dynamische Strompreise. Diese Version (0.1) ist die
**Datengrundlage**. Die eigene, lernende Prognose und die Steuerung von Batterie, E-Auto und
Heizstab bauen darauf auf.

## Erste Schritte

1. Add-on starten und **Web-UI öffnen**.
2. Unter **Einstellungen › PV-Anlagen** für jeden Messsensor, meist einen Wechselrichter, eine Anlage anlegen:
   - **Messsensor:** Sensor des Wechselrichters, z. B. die AC-Leistung (W) oder der Energiezähler (kWh) des Fronius.
   - **Teilflächen:** eine Zeile pro Ausrichtung mit Leistung (kWp), Neigung (0° = flach, 90° = senkrecht) und Ausrichtung (Ost, Süd, West … oder genau in Grad, 90° = Ost, 180° = Süd, 270° = West).
3. Unter **Strompreis** die festen Preisbestandteile deines Tarifs eintragen (siehe unten).
4. Optional unter **Sensoren & Standort** Hausverbrauch, Netzleistung und Batterie auswählen.

Nach dem Speichern lädt EnergyPilot im Hintergrund:

- die **Messwerte der letzten 90 Tage** aus der Langzeitstatistik von Home Assistant,
- das **Prognose-Archiv** der Wettermodelle für denselben Zeitraum.

Der **Prognose-Check** zeigt damit schon nach wenigen Minuten, welche Quelle bei dir am
genauesten ist. Er muss nicht erst wochenlang Daten sammeln.

## Messsensor

Der Sensor braucht eine **Langzeitstatistik**, also ein Attribut `state_class`. Die
Wechselrichter-Integrationen (Fronius, SMA, …) setzen das automatisch. Im Auswahlfeld sind Sensoren
ohne Statistik markiert. Unterstützt werden:

- Leistung in W oder kW (EnergyPilot nutzt den Stundenmittelwert),
- Energie in Wh oder kWh (Zählerstand, EnergyPilot nutzt die Änderung pro Stunde).

### Ost-West-Anlagen und mehrere Ausrichtungen an einem Wechselrichter

Zeigt ein String nach Osten und einer nach Westen, der Wechselrichter meldet aber nur einen
Gesamtwert, legst du **eine** Anlage mit diesem Sensor an und trägst **zwei Teilflächen** ein
(Ost und West, jeweils mit ihrer kWp-Leistung). EnergyPilot rechnet jede Teilfläche einzeln und
vergleicht die Summe mit dem Sensor. Die Wechselrichter-Grenze (Erweitert) gilt dabei für die Summe.

Liefert der Wechselrichter die Strings einzeln (z. B. Spannung und Strom je MPPT-Eingang), kannst du
in Home Assistant je String einen Leistungssensor anlegen und daraus zwei getrennte Anlagen machen.
Dann zeigt der Prognose-Check sogar, welches Modell Osten und Westen jeweils besser trifft.

## Prognosequellen

| Quelle | Kosten | Zeitraum | Archiv |
|---|---|---|---|
| Open-Meteo: DWD ICON-D2, ICON-EU, ECMWF, GFS, Météo-France, KNMI, UK Met Office, „Auto“ | kostenlos | bis 3 Tage | ja |
| Forecast.Solar | kostenlos (12 Abrufe/Stunde, ein Abruf je Teilfläche) | heute + morgen | nein |
| Solcast (Hobby-Zugang) | kostenlos mit Anmeldung (10 Abrufe/Tag) | 3 Tage | nein |

Bei den Open-Meteo-Modellen berechnet EnergyPilot die PV-Leistung selbst. Die Global- und
Diffusstrahlung wird auf die Modulebene umgerechnet (Hay-Davies-Modell, Sonnenstand in
10-Minuten-Schritten), danach werden Temperaturverluste und der Systemwirkungsgrad abgezogen. Wenn du
die Teilflächen einer Anlage änderst, berechnet EnergyPilot alle gespeicherten Prognosen
sofort neu.

### Prognose-Horizonte

Jede Prognose wird für jede Stunde in zwei Varianten gespeichert:

- **Vortag:** die letzte Prognose, die vor Mitternacht vorlag. Auf ihr beruht die Planung für den nächsten Tag, z. B. ob die Batterie nachts günstig aus dem Netz geladen wird.
- **Kurzfristig:** die letzte Prognose, bevor die Stunde begann.

## Prognose-Check

| Kennzahl | Bedeutung |
|---|---|
| Genauigkeit | 100 % minus mittlerer Stundenfehler relativ zur Erzeugung |
| Tagesabweichung Ø | mittlerer Fehler beim Tagesertrag relativ zum Tagesertrag |
| Summe | systematische Abweichung: + = Prognose zu hoch, − = zu niedrig |
| Größter Tagesfehler | der schlechteste Tag im Zeitraum |

**Nach Wetterlage** teilt die Tage anhand der gemessenen Erzeugung im Verhältnis zu einem
wolkenlosen Tag ein: sonnig ≥ 60 %, wechselhaft 30–60 %, trüb < 30 %. So sieht man, welches Modell
bei welchem Wetter am besten liegt.

Mit **Nur gemeinsame Stunden** werden alle Quellen auf denselben Stunden verglichen. Das ist fair,
wenn Quellen unterschiedlich lange Daten haben, z. B. Forecast.Solar ohne Archiv.

## Strompreis

Dynamische Tarife wie **sonnen EnergyDynamic** geben den Börsenpreis (EPEX Day-Ahead, seit Oktober
2025 in Viertelstunden) weiter. EnergyPilot lädt ihn von Energy-Charts (Fraunhofer ISE) mit
aWATTar als Ersatzquelle und rechnet den Endpreis so:

```
Endpreis = (Börsenpreis + Aufschlag netto) × (1 + MwSt)
```

Der Aufschlag netto ist die Summe aus Netzentgelt, Umlagen, Stromsteuer und dem Aufschlag des
Anbieters, jeweils in ct/kWh ohne Mehrwertsteuer. Die Werte stehen im Vertrag bzw. auf der Rechnung.

## Sensoren in Home Assistant

Mit der Option *Sensoren in Home Assistant anlegen* stellt EnergyPilot bereit:

| Entität | Inhalt |
|---|---|
| `sensor.energypilot_strompreis` | aktueller Endpreis in ct/kWh; Attribut `prices` mit den nächsten 36 Stunden |
| `sensor.energypilot_pv_prognose_heute` | PV-Prognose heute in kWh von der genauesten Quelle; Attribut `hourly` |
| `sensor.energypilot_pv_prognose_morgen` | dasselbe für morgen |
| `sensor.energypilot_beste_prognosequelle` | Name der genauesten Quelle (letzte 30 Tage, Vortag) |

## Entwicklung

Lokal ohne Home Assistant, mit synthetischen Daten:

```bash
cd energypilot/rootfs/opt
ENERGYPILOT_DEMO=1 ENERGYPILOT_ALLOW_ALL=1 ENERGYPILOT_DATA=../../../data/demo python -m energypilot
```

Gegen ein echtes Home Assistant zusätzlich `ENERGYPILOT_HA_URL=http://homeassistant.local:8123`
und `ENERGYPILOT_HA_TOKEN=<langlebiges Zugriffstoken>` setzen und `ENERGYPILOT_DEMO` weglassen.
