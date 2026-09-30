# Changelog

## 0.3.4

- Übersicht neu geordnet: oben die Karte **„Jetzt“** mit Empfehlung, Begründung und „Strom kaufen: ja/nein“ sowie den Energieflüssen (PV, Haus, Akku, Netz); darunter Strompreis, PV heute und Grundverbrauch
- Diagramm-Legenden zeigen nur die eingeblendeten Linien, weitere Quellen hinter „+N weitere“
- Besser lesbar: Hilfstexte mit höherem Kontrast (WCAG AA), größere Bedienflächen auf Touch-Geräten
- Planung: Kachel „Akku leer (Prognose)“ statt der mehrdeutigen Angabe „reicht“
- Entwicklung: `dev.py` startet EnergyPilot lokal gegen ein echtes Home Assistant – nur lesend, schreibt keine Sensoren

## 0.3.3

- Neu: **Protokoll** – jede Stunde wird die Empfehlung festgehalten (Modus, Preis, PV- und Verbrauchsprognose, geplanter Ladezustand, gemessener Ladezustand). Sobald die Messwerte da sind, rechnet EnergyPilot für jeden Tag drei Stromrechnungen aus den echten Werten: **ohne Plan** (Akku im Eigenverbrauch), **mit Plan** (Empfehlungen befolgt) und **optimal** (im Nachhinein bestmöglich)
- Übersicht mit Ersparnis, möglicher Ersparnis und erreichtem Anteil; Tagestabelle mit Prognose gegen Messwert; Stundendetails per Klick
- Grundlage, um zu entscheiden, ab wann EnergyPilot den Akku selbst steuern darf
- Gestrichelte Linien in Diagrammen werden jetzt korrekt gestrichelt dargestellt

## 0.3.2

- Neu: **Richtung umkehren** für Hausverbrauch, Netzleistung und Batterie-Leistung (Einstellungen › Sensoren) – z. B. für die sonnenBatterie, die Entladen positiv meldet. Darunter steht sofort, wie EnergyPilot den aktuellen Wert versteht („Batterie entlädt mit 737 W“)
- Unter jedem gewählten Sensor wird der **aktuelle Zustand** angezeigt
- Behoben: Batterie wurde als „lädt“ angezeigt, obwohl sie entlädt (fehlende Vorzeichen-Einstellung)

## 0.3.1

- Neu: **Kontrolle** unter Einstellungen › Sensoren – Durchschnitt pro Tag der letzten 7 Tage für Hausverbrauch, E-Auto, Heizstab und den daraus berechneten Grundverbrauch, mit Hinweis auf Lücken; zum Prüfen, ob die Sensoren richtig gewählt sind
- Behoben: Der gespeicherte Grundverbrauch wird bei jedem Lernen komplett neu berechnet – Werte aus der Zeit, bevor E-Auto und Heizstab eingetragen waren, bleiben nicht mehr stehen (betraf Anzeige und Prognose-Check)
- Sensoren, die den Verbrauch mit negativem Vorzeichen melden, werden erkannt und umgedreht

## 0.3.0

- Neu: **Planung** – günstigster Fahrplan für den Heimspeicher bis zum Ende der bekannten Strompreise (meist morgen 24 Uhr). Pro Stunde: Eigenverbrauch, Akku halten (Energie für teure Stunden aufsparen) oder aus dem Netz laden. Grundlage: genaueste PV-Prognose, Verbrauchsprognose, aktueller Ladezustand und Strompreise; Energie, die am Ende im Akku bleibt, wird mit einem vorsichtigen Preis bewertet
- **Empfehlung jetzt** mit Begründung („Strom kaufen: ja/nein“) und Ersparnis gegenüber dem Akku ohne Planung; Umschalten nur, wenn es mindestens 1 ct bringt
- **Akku-Reichweite:** wie lange der Akku beim aktuellen Verbrauch reicht und wann er laut Prognose leer bzw. wieder voll ist – auf der Planungsseite und in der Übersicht
- **Verbrauchsprognose sichtbar:** als Linie im Diagramm der Übersicht und auf der Planungsseite
- Neuer Einstellungsreiter **Batterie**: Kapazität, Reserve, Lade-/Entladeleistung, Wirkungsgrad, Netzladen bis, Netzladen erlauben
- Neue Sensoren: `sensor.energypilot_empfehlung`, `binary_sensor.energypilot_netzladen`, `binary_sensor.energypilot_entladesperre`, `sensor.energypilot_akku_reichweite`
- Noch keine Steuerung – die Empfehlung kann über die Sensoren in eigenen Automationen genutzt werden

## 0.2.1

- Sensorauswahl mit **Suche**: Name oder Entitäts-ID eintippen (mehrere Wörter möglich), mit Pfeiltasten und Enter auswählen oder die Liste aufklappen; zeigt aktuellen Wert und Einheit und markiert Sensoren ohne Langzeitstatistik. Eine Entität, die nicht in der Liste steht, kann direkt als ID eingetragen werden
- Neues Icon und Logo für den Add-on-Store

## 0.2.0

- Neu: **Eigene, lernende PV-Prognose „EnergyPilot“** – gewichtet jede Quelle je Anlage und erwarteter Wetterlage nach ihrer bisherigen Treffsicherheit und korrigiert je Uhrzeit (Verschattung, Abregelung, Verschmutzung). Wird stündlich neu gelernt, rückwirkend Tag für Tag nur aus den Vortagen – so ist der Vergleich im Prognose-Check ehrlich
- Neu: **Verbrauchsprognose** für den Grundverbrauch (Hausverbrauch ohne E-Auto und Heizstab) nach Uhrzeit, Wochentag und Temperatur; Vergleichsmaßstab „wie vor einer Woche“
- Neu: Sensoren für **E-Auto/Wallbox** und **Heizstab** (Einstellungen › Sensoren)
- Prognose-Check und Tagesverlauf: Auswahl „Grundverbrauch“; Karte „So rechnet die eigene Prognose“ mit Gewichtung der Quellen und Korrektur nach Uhrzeit
- Die genaueste Quelle (auch für die Sensoren) wird automatisch gewählt – das ist die eigene Prognose, sobald sie besser ist als alle Wetterdienste
- Neue Sensoren: `sensor.energypilot_verbrauch_prognose_heute` / `_morgen`

## 0.1.1

- Neu: **Teilflächen** – eine Anlage kann mehrere Ausrichtungen haben, z. B. Ost und West an einem Wechselrichter mit nur einem Gesamtwert. Jede Teilfläche wird einzeln berechnet (Wettermodelle und Forecast.Solar), verglichen wird die Summe mit dem Sensor
- Wechselrichter-Grenze gilt für die Summe aller Teilflächen
- Ausrichtung per Himmelsrichtung wählbar oder genau in Grad; „Teilfläche hinzufügen“ schlägt die Gegenrichtung vor
- Bestehende Anlagen werden automatisch übernommen

## 0.1.0

- Erste Version: **Datengrundlage für die Energieoptimierung**
- PV-Anlagen mit Leistung, Neigung, Ausrichtung und Messsensor (eine Anlage pro Ausrichtung)
- Stündliche PV-Prognosen von 6 Open-Meteo-Wettermodellen (DWD ICON-D2/ICON-EU, ECMWF, GFS, Météo-France, Auto; optional KNMI und UK Met Office), Forecast.Solar und optional Solcast
- Eigenes PV-Modell: Transposition auf die Modulebene (Hay-Davies), Temperatur- und Systemverluste, Wechselrichter-Grenze
- Rückblick: Messwerte aus der Langzeitstatistik von Home Assistant und archivierte Modellprognosen der letzten 90 Tage werden automatisch nachgeladen
- **Prognose-Check:** Rangliste der Quellen (Genauigkeit, Tagesabweichung, systematischer Fehler), getrennt nach Vortags- und Kurzfrist-Prognose, nach Wetterlage (sonnig/wechselhaft/trüb) und je Anlage
- **Tagesverlauf:** Stundenwerte von Messung und allen Prognosen, Tagessummen
- **Strompreise:** EPEX Day-Ahead (15 Minuten) mit eigenen Aufschlägen und MwSt, günstigste Zeitfenster
- **Übersicht:** Live-Werte (PV, Haus, Netz, Batterie), Preis, Prognose heute und morgen, Status der Datenquellen
- Sensoren in Home Assistant: Strompreis, PV-Prognose heute/morgen, genaueste Prognosequelle
