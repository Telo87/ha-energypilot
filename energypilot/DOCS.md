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

## Eigene Prognose „EnergyPilot (lernend)“

EnergyPilot baut aus allen Quellen eine eigene Prognose je Anlage:

1. **Gewichtung:** Jede Quelle zählt umso mehr, je kleiner ihr Fehler bei dieser Anlage in den letzten
   30 Tagen war – getrennt nach erwarteter Wetterlage.
2. **Korrektur je Uhrzeit, getrennt für Sonne und Wolken:** Schatten von Bäumen oder Nachbarhäusern
   wirkt nur bei direkter Sonne; systematische Fehler der Wettermodelle zeigen sich auch bei Bewölkung.
3. **Spanne (P10–P90):** aus der Verteilung der bisherigen Fehler in derselben Wetterlage – in 8 von 10
   Stunden liegt die Erzeugung innerhalb des grauen Bandes.

Gelernt wird **jede Stunde neu** und rückwirkend Tag für Tag nur aus den Tagen davor. Im Prognose-Check
tritt sie daher fair gegen die Wetterdienste an.

### Live-Korrektur

Die gemessene PV-Leistung der letzten Stunde wird mit der Prognose verglichen. Die Abweichung korrigiert
die laufende Stunde (40 %), die nächste (20 %) und die übernächste (10 %). Stärkere Gewichte reagieren an
echten Daten zu sehr auf einzelne Wolken und machen die Prognose schlechter. Im Prognose-Check erscheint
sie unter „Kurzfristig“ als „EnergyPilot (live korrigiert)“; der Planer rechnet damit.

### Ausrichtung prüfen

Unter Einstellungen › PV-Anlagen berechnet „Ausrichtung prüfen“ aus den klaren Stunden (Sonnenhöhe über
20°), welche Ausrichtung und Neigung am besten zur gemessenen Tageskurve passen – verglichen wird nur die
Form, nicht die Höhe. Eine falsch eingetragene Ausrichtung macht alle Wetterdienst-Prognosen ungenauer;
der Vorschlag lässt sich mit einem Klick übernehmen.

## Verbrauchsprognose

Aus Hausverbrauch minus E-Auto minus Heizstab (Einstellungen › Sensoren) ergibt sich der
**Grundverbrauch**. Er wird nach Uhrzeit und Wochentag (Mo–Fr, Sa, So) gelernt, jüngere Wochen zählen
mehr; hängt der Verbrauch erkennbar von der Außentemperatur ab, wird das berücksichtigt. E-Auto und
Heizstab sind steuerbar und werden später gezielt eingeplant. Vergleichsmaßstab im Prognose-Check
(Auswahl „Grundverbrauch“) ist „Wie vor einer Woche“.

## Planung

Die Seite **Planung** rechnet alle 5 Minuten den günstigsten Fahrplan für den Heimspeicher bis zum Ende
der bekannten Strompreise (die Preise für morgen erscheinen gegen 13 Uhr). Für jede Stunde gibt es drei
Möglichkeiten:

| Modus | Bedeutung |
|---|---|
| Eigenverbrauch | Der Akku arbeitet wie gewohnt: PV-Überschuss laden, Verbrauch decken |
| Akku halten | Der Akku wird nicht entladen – die Energie wird für spätere, teurere Stunden aufgespart |
| Aus dem Netz laden | Günstiger Netzstrom wird eingespeichert, weil er später teureren Netzstrom ersetzt |

Grundlage sind die genaueste PV-Prognose, die Verbrauchsprognose (ohne E-Auto und Heizstab), der
aktuelle Ladezustand, die Akku-Daten (Einstellungen › Batterie) und die Strompreise. Energie, die am
Ende noch im Akku ist, wird mit einem vorsichtigen Preis bewertet, damit der Plan den Akku nicht
künstlich leerfährt. Umgeschaltet wird nur, wenn es über den ganzen Zeitraum mindestens 1 ct spart.

Mit dem **Sicherheitsabschlag** (Einstellungen › Batterie) rechnet der Planer bei unsicherer
PV-Prognose mit weniger Sonne („Vorsichtig“ = untere Grenze der Spanne). So bleibt der Akku eher für den
Abend gefüllt, wenn der Tag trüber wird als erwartet.

Die **Reichweite** zeigt, wie lange der Akku beim aktuellen Hausverbrauch bis zur Reserve reicht, und
wann er laut Prognose (mit PV-Erzeugung) leer bzw. wieder voll ist.

EnergyPilot **steuert noch nichts**. Die Empfehlung steht als Sensoren für eigene Automationen bereit:

| Entität | Inhalt |
|---|---|
| `sensor.energypilot_empfehlung` | Eigenverbrauch / Akku halten / Aus dem Netz laden; Attribute `reason`, `plan` |
| `binary_sensor.energypilot_netzladen` | an, wenn jetzt aus dem Netz geladen werden soll |
| `binary_sensor.energypilot_entladesperre` | an, wenn der Akku jetzt nicht entladen werden soll |
| `sensor.energypilot_akku_reichweite` | Stunden beim aktuellen Verbrauch; Attribute `empty_at`, `full_at` |

## Protokoll

Jede Stunde hält EnergyPilot fest, was es zu Beginn der Stunde empfohlen hat – mit Preis, PV- und
Verbrauchsprognose sowie geplantem und gemessenem Ladezustand. Sobald die Messwerte der Stunde da sind,
rechnet es für jeden Tag drei Stromrechnungen aus den **echten** Werten:

| Rechnung | Bedeutung |
|---|---|
| ohne Plan | Akku im Eigenverbrauch – so, wie er tatsächlich lief |
| mit Plan | die Empfehlungen, die aus den Prognosen entstanden, wären befolgt worden |
| optimal | im Nachhinein bestmöglicher Fahrplan mit perfektem Wissen |

„Mit Plan gespart“ kann auch negativ sein, wenn Prognosen danebenlagen. Liegt der Wert über einige Tage
nahe an „optimal“ (Anteil „davon erreicht“ hoch), sind Prognosen und Planung verlässlich genug, um
EnergyPilot die Steuerung zu überlassen. Grundlage ist der Grundverbrauch; E-Auto und Heizstab sind nicht
enthalten.

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

Einfacher geht es mit **„Aufschlag aus einem Preis berechnen“**: einen oder mehrere Gesamtpreise aus der
App des Anbieters (z. B. sonnen-App, viertelstündlicher Preis) mit Tag und Uhrzeit eintragen. EnergyPilot
rechnet `Preis ÷ (1 + MwSt) − Börsenpreis` für jede Viertelstunde aus und übernimmt den Mittelwert.

## Sensoren in Home Assistant

Mit der Option *Sensoren in Home Assistant anlegen* stellt EnergyPilot bereit:

| Entität | Inhalt |
|---|---|
| `sensor.energypilot_strompreis` | aktueller Endpreis in ct/kWh; Attribut `prices` mit den nächsten 36 Stunden |
| `sensor.energypilot_pv_prognose_heute` | PV-Prognose heute in kWh von der genauesten Quelle; Attribut `hourly` |
| `sensor.energypilot_pv_prognose_morgen` | dasselbe für morgen |
| `sensor.energypilot_verbrauch_prognose_heute` / `_morgen` | Grundverbrauch (ohne E-Auto und Heizstab) in kWh; Attribut `hourly` |
| `sensor.energypilot_beste_prognosequelle` | Name der genauesten Quelle (letzte 30 Tage, Vortag) |

## Entwicklung

Lokal ohne Home Assistant, mit synthetischen Daten:

```bash
cd energypilot/rootfs/opt
ENERGYPILOT_DEMO=1 ENERGYPILOT_ALLOW_ALL=1 ENERGYPILOT_DATA=../../../data/demo python -m energypilot
```

Lokal gegen ein echtes Home Assistant (nur lesend – schreibt keine Sensoren, eigene Daten in
`data/dev`): `.env.example` nach `.env` kopieren, Adresse und ein langlebiges Zugriffstoken eintragen
(Profil › Sicherheit), dann `python dev.py` starten und http://localhost:8099 öffnen. `.env` ist von Git
ausgeschlossen.
