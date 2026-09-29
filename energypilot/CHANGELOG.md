# Changelog

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
