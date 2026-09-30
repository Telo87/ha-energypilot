# EnergyPilot – Home Assistant Add-on

![Version](https://img.shields.io/badge/version-0.5.9-blue)

Welche PV-Prognose stimmt bei **deinem** Dach? EnergyPilot sammelt stündlich die Prognosen mehrerer
Wetterdienste, vergleicht sie mit der tatsächlichen Erzeugung jeder Anlage und zeigt dynamische
Strompreise. Auf dieser Grundlage folgen eine eigene, lernende Prognose und die Steuerung von
Batterie, E-Auto und Heizstab.

## Funktionen

- **Mehrere PV-Anlagen** mit eigenem Messsensor, auch mit mehreren Ausrichtungen an einem Wechselrichter (z. B. Ost-West)
- **Prognosequellen:** DWD ICON-D2 und ICON-EU, ECMWF, NOAA GFS, Météo-France und weitere über Open-Meteo (kostenlos), Forecast.Solar, optional Solcast
- **Sofortiger Rückblick:** Messwerte aus der Langzeitstatistik von Home Assistant und archivierte Modellprognosen der letzten 90 Tage, die Rangliste steht nach wenigen Minuten
- **Prognose-Check:** Genauigkeit je Quelle, für Vortag und kurzfristig, nach Wetterlage und je Anlage
- **Strompreise:** EPEX Day-Ahead in Viertelstunden mit den Aufschlägen deines Tarifs, günstigste Zeitfenster
- **Eigene, lernende PV-Prognose:** gewichtet die Quellen nach ihrer Treffsicherheit bei deinen Anlagen und lernt Verschattung und Abregelung – und muss sich im Prognose-Check gegen die Wetterdienste behaupten
- **Verbrauchsprognose** für den Grundverbrauch (ohne E-Auto und Heizstab) nach Uhrzeit, Wochentag und Temperatur
- **Planung:** günstigster Fahrplan für den Akku bis morgen Abend – Eigenverbrauch, Akku halten oder aus dem Netz laden – mit Begründung und Ersparnis; Akku-Reichweite beim aktuellen Verbrauch und laut Prognose
- **Kosten:** echte Stromkosten pro Tag und Monat (Netzbezug zum Preis der jeweiligen Viertelstunde, Grundgebühr, Einspeisevergütung), bezahlter Durchschnittspreis gegenüber dem Börsendurchschnitt, Vergleich mit einem Festpreistarif, Autarkie
- **Protokoll:** jede Empfehlung wird festgehalten und nachgerechnet – was hätte das Befolgen mit den echten Messwerten gespart, was wäre im Nachhinein möglich gewesen
- **Einrichtung:** prüft, ob alle Einstellungen vorhanden und plausibel sind – Sensoren, Einheiten, Vorzeichen, Anlagenleistung, Tarif, Batterie – mit Link zur passenden Einstellung
- **Sensoren** für Automationen: Empfehlung, Netzladen/Entladesperre, Akku-Reichweite, Strompreis, PV- und Verbrauchsprognose, genaueste Quelle

## Geplant

- Steuerung: Empfehlung automatisch an den Heimspeicher übergeben (mit Sicherheitsgrenzen)
- E-Auto-Ladeplan, Heizstab bei PV-Überschuss

## Installation

1. In Home Assistant: **Einstellungen › Add-ons › Add-on Store › ⋮ › Repositories**
2. `https://github.com/Telo87/ha-energypilot` hinzufügen
3. **EnergyPilot** installieren und starten, dann die Web-UI öffnen

## Lizenz

MIT
