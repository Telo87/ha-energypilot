# Changelog

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
