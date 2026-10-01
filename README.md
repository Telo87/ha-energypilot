# EnergyPilot – Home Assistant Add-on

![Version](https://img.shields.io/badge/version-0.9.0-blue)

Welche PV-Prognose stimmt bei **deinem** Dach – und wann lohnt es sich, den Akku zu halten oder günstig aus
dem Netz zu laden? EnergyPilot sammelt stündlich die Prognosen mehrerer Wetterdienste, vergleicht sie mit
der tatsächlichen Erzeugung jeder Anlage, lernt daraus eine eigene Prognose und plant mit dynamischen
Strompreisen den günstigsten Fahrplan für den Heimspeicher. Jede Empfehlung wird festgehalten und mit den
echten Messwerten nachgerechnet.

## Funktionen

**Prognosen**
- **Mehrere PV-Anlagen** mit eigenem Messsensor, auch mit mehreren Ausrichtungen an einem Wechselrichter (z. B. Ost-West)
- **Prognosequellen:** DWD ICON-D2 und ICON-EU, ECMWF, NOAA GFS, Météo-France und weitere über Open-Meteo (kostenlos), Forecast.Solar, optional Solcast
- **Eigene, lernende PV-Prognose:** gewichtet die Quellen nach ihrer Treffsicherheit bei deinen Anlagen und lernt Verschattung und Abregelung getrennt für Sonne und Wolken; Spanne (P10–P90) und Live-Korrektur nach der Erzeugung der letzten Stunde
- **Verbrauchsprognose** für den Grundverbrauch (ohne E-Auto und Heizstab) nach Uhrzeit, Werktag/Wochenende/Feiertag, Temperatur und aktuellem Verbrauchsniveau
- **Sofortiger Rückblick:** Messwerte aus der Langzeitstatistik von Home Assistant und archivierte Modellprognosen der letzten 90 Tage – die Rangliste steht nach wenigen Minuten

**Auswertung**
- **Prognose-Check:** Genauigkeit je Quelle, für Vortag und kurzfristig, nach Wetterlage und je Anlage – plus **Entwicklung über die Zeit**: lernt die eigene Prognose dazu oder wird sie schlechter?
- **Tagesverlauf:** Erzeugung oder Grundverbrauch Stunde für Stunde, mit Rangliste der Quellen für den Tag
- **Ausrichtung prüfen:** erkennt aus den Messwerten, ob Ausrichtung und Neigung einer Anlage stimmen

**Planung**
- **Fahrplan für den Akku** so weit Strompreise bekannt sind – Eigenverbrauch, Akku halten oder aus dem Netz laden – mit Ersparnis gegenüber „ohne Eingriff“
- **„Warum dieser Plan?“:** erklärt jede Entscheidung – wann der Akku sonst leer wäre, für welche Stunden Energie aufgehoben wird und was das je kWh bringt
- **Akku-Reichweite** beim aktuellen Entladen und laut Prognose
- **Protokoll:** jede Empfehlung wird festgehalten und mit dem gesamten gemessenen Verbrauch nachgerechnet – ohne EnergyPilot, mit EnergyPilot, im Nachhinein optimal – und mit der gemessenen Stromrechnung abgeglichen

**Kosten und Tarif**
- **Strompreise:** EPEX Day-Ahead in Viertelstunden mit den Aufschlägen deines Tarifs, günstigste Zeitfenster
- **Kosten:** echte Stromkosten pro Tag und Monat (Netzbezug zum Preis der jeweiligen Viertelstunde, Grundgebühr, Einspeisevergütung), bezahlter Durchschnittspreis gegenüber dem Börsendurchschnitt, Autarkie
- **Tarifvergleich** (abschaltbar) mit einem Festpreistarif oder einer **Flat mit Freistrom-Kontingent** samt Stand des Kontingents
- **Einspeisevergütung je Anlage**, aufgeteilt nach Anlagenleistung oder gemessener Erzeugung
- **Heizstab mit eigener Überschussregelung** wird als solcher berücksichtigt

**Einrichtung und Home Assistant**
- **Einrichtung:** prüft Sensoren, Einheiten, Vorzeichen, Anlagenleistung, Tarif, Batterie und die **Energiebilanz** – mit Link zur passenden Einstellung und einer Hinweiszahl im Menü; **Diagnose-Export** für eine ausführliche Prüfung
- **Sensoren** für Automationen: Empfehlung, Netzladen/Entladesperre, Akku-Reichweite, Strompreis, PV- und Verbrauchsprognose, genaueste Quelle

## Geplant

- Steuerung: Empfehlung automatisch an den Heimspeicher übergeben (mit Sicherheitsgrenzen) – sobald das Protokoll über einige Wochen zeigt, dass Prognosen und Planung verlässlich sind
- E-Auto-Ladeplan und Heizstab in der Planung

## Installation

1. In Home Assistant: **Einstellungen › Add-ons › Add-on Store › ⋮ › Repositories**
2. `https://github.com/Telo87/ha-energypilot` hinzufügen
3. **EnergyPilot** installieren und starten, dann die Web-UI öffnen
4. Unter **Einrichtung** prüfen, was noch fehlt – die Dokumentation im Add-on erklärt alle Einstellungen

## Lizenz

[PolyForm Strict 1.0.0](LICENSE) – die Nutzung für nicht-kommerzielle Zwecke ist erlaubt (privat, Hobby,
gemeinnützige Organisationen). Weitergabe, Veränderung und darauf aufbauende Werke sind nicht erlaubt.
Versionen bis einschließlich 0.6.4 wurden unter der MIT-Lizenz veröffentlicht.
