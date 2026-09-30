# Changelog

## 0.5.6

- Behoben: Die Live-Korrektur der PV-Prognose wurde auch auf die Verbrauchsprognose kopiert (beide tragen intern dasselbe Kürzel) und erschien deshalb beim Grundverbrauch in Tagesverlauf und Prognose-Check. Der Plan war nicht betroffen. Die falschen Werte werden beim Update gelöscht
- Tagesverlauf: Die Tagessumme heißt je nach Auswahl „Tagessumme Erzeugung“ oder „Tagessumme Verbrauch“

## 0.5.5

Durchsicht des ganzen Add-ons auf Fehler:

- Behoben (Tagesverlauf): Die Tagessumme verglich die Prognose für den ganzen Tag mit den bisher gemessenen Stunden – daraus wurden Abweichungen von mehreren tausend Prozent. Jetzt zählen für die Abweichung nur die schon gemessenen Stunden; kleine Mengen am Morgen werden in kWh statt in Prozent angegeben
- Tagesverlauf: Die Tagessumme ist als Rangliste gekennzeichnet (Platz 1 = kleinste Abweichung); die live korrigierte Prognose, die nur für die jeweils nächsten Stunden berechnet wird, ist als „nur N Stunden berechnet“ markiert
- Behoben (Tagesverlauf): Nachtstunden ohne Wert des Wechselrichters zählen als 0 – vergangene Tage galten sonst als unvollständig gemessen
- Behoben (Live-Korrektur): Sie wurde an der eigenen Prognose gemessen, aber auf die Quelle angewendet, mit der der Plan rechnet. Beides ist jetzt dieselbe Quelle
- Behoben (Live-Korrektur, Einrichtung): Ist als Messsensor ein Energiezähler (kWh) gewählt, wurde sein Zählerstand als Leistung gelesen. Live-Korrektur, Anzeige „PV-Erzeugung“ und die Prüfung des Batterie-Vorzeichens nutzen jetzt nur Leistungssensoren
- Behoben (Kosten): Der Durchschnitt aller Viertelstunden enthielt schon bekannte, aber noch nicht vergangene Preise (Rest des Tages, morgen)
- Behoben (Kosten): Ein Hausverbrauch-Sensor mit negativem Vorzeichen wird wie beim Grundverbrauch automatisch umgedreht – die Autarkie fehlte sonst
- Behoben (Datenquellen): Schlug Forecast.Solar für eine Anlage fehl und klappte für die nächste, wurde der Fehler nicht angezeigt
- Genauigkeit: Übersicht und Prognose-Check zeigen jetzt, wonach sortiert wird (Fehler je Stunde) und daneben den Fehler je Tag; „Summe“ heißt jetzt „Tendenz“
- Übersicht: „Akku reicht über … hinaus“ nennt das tatsächliche Ende des Planungszeitraums

## 0.5.4

- Menü neu gegliedert: „Heute“ (Übersicht, Planung, Strompreise), „Auswertung“ (Tagesverlauf, Prognose-Check, Protokoll, Kosten) und „Verwaltung“

## 0.5.3

- Einstellungen → Sensoren & Standort neu aufgebaut: Gruppen für Haus, Stromnetz, Batterie und große Verbraucher, je mit Status („eingerichtet“, „fehlt“, „optional“)
- Kürzere Hinweise direkt neben jedem Sensor; getrennter Netzbezug/Einspeisung als aufklappbare Option
- Standort eingeklappt – nur nötig, wenn er vom Home-Assistant-Standort abweicht
- Speicherleiste bleibt sichtbar und zeigt ungespeicherte Änderungen an

## 0.5.2

- Behoben (Protokoll): Nachtstunden wurden nicht ausgewertet, weil Wechselrichter nachts abschalten und ihr Sensor dann keinen Wert liefert – bei Sonne unter dem Horizont zählt die Erzeugung jetzt als 0
- Behoben (Protokoll): Die angezeigten Stromkosten enthielten eine Gutschrift für die Energie, die am Ende noch im Akku steckt – dadurch z. B. −0,74 € für eine einzige Stunde. Angezeigt wird jetzt die reine Stromrechnung; die Gutschrift wirkt nur noch beim Vergleich (gespart / möglich)
- Protokoll: Prognose und Messung von PV und Verbrauch werden über dieselben Stunden verglichen

## 0.5.1

- Neu: **Einrichtung** (unter Verwaltung) – prüft, ob alle Einstellungen vorhanden, erreichbar und plausibel sind: Verbindung und Standort; PV-Anlagen (Sensor vorhanden, Einheit, Langzeitstatistik, aktuelle Werte, gemessene Höchstleistung passend zur kWp-Angabe); Sensoren inklusive **Vorzeichen-Prüfung** (bei großem PV-Überschuss muss eingespeist bzw. der Akku geladen werden) und Lücken bei E-Auto/Heizstab; Strompreis (Preise vorhanden, Aufschlag, MwSt, Einspeisevergütung plausibel); Batterie (Kapazität, Leistungen, Reserve, Wirkungsgrad); Prognosequellen, eigene Prognose, Verbrauchsprognose und Plan
- Jeder Punkt mit „Beheben“-Link zur passenden Einstellung; Anzahl der Probleme im Menü und als Hinweis auf der Übersicht
- Protokoll und Planung: „mit/ohne Plan“ heißt jetzt „mit/ohne EnergyPilot“

## 0.5.0

- Neu: **Kosten** – Stromkosten pro Tag und Monat aus dem gemessenen Netzbezug und dem Preis der jeweiligen Stunde, plus anteilige Grundgebühr, abzüglich Einspeisevergütung; rückwirkend für den ganzen Rückblick-Zeitraum
- **Ø bezahlter Preis** gegenüber dem Durchschnitt aller Viertelstunden – zeigt, ob Strom eher in günstigen oder teuren Stunden gekauft wird
- **Vergleich mit einem Festpreistarif** (Arbeitspreis und Grundpreis einstellbar) und Monatsübersicht der letzten 12 Monate
- **Autarkie** und **Eigenverbrauchsquote**
- Neu in den Einstellungen: Grundgebühr, Vergleichstarif; optionale Sensoren **Netzbezug** und **Einspeisung** (genauer als die Netzleistung mit Vorzeichen)
- Börsenpreise werden für den Rückblick-Zeitraum rückwirkend geladen
- Texte in Oberfläche und Dokumentation neutral formuliert (keine Anbieter- oder Produktnamen als Beispiele)

## 0.4.1

- Neu: **Aufschlag aus einem Preis berechnen** (Einstellungen › Strompreis) – Gesamtpreise aus der App des Anbieters mit Tag und Uhrzeit eintragen, EnergyPilot rechnet den Aufschlag netto aus dem Börsenpreis der jeweiligen Viertelstunde zurück, bildet bei mehreren Preisen den Mittelwert und zeigt, ob sie zusammenpassen; mit einem Klick übernehmen
- Das Rechenbeispiel in den Strompreis-Einstellungen nutzt den aktuellen Börsenpreis

## 0.4.0

- Neu: **Live-Korrektur** – die gemessene PV-Leistung der letzten Stunde wird mit der Prognose verglichen und korrigiert die laufende und die nächsten zwei Stunden (Gewichte 0,4 / 0,2 / 0,1, an echten Daten abgestimmt: rund 10 % genauer für die nächste Stunde). Eigene Quelle „EnergyPilot (live korrigiert)“ im Prognose-Check (kurzfristig); der Planer rechnet damit
- **Korrektur je Uhrzeit getrennt für Sonne und Wolken**: Schatten wirkt nur bei direkter Sonne, systematische Fehler der Wettermodelle auch bei Bewölkung. (Eine Schattenkarte nach Sonnenstand wurde ebenfalls gebaut und an echten Daten getestet – sie war nicht genauer und wurde wieder entfernt.)
- Neu: **Ausrichtung prüfen** (Einstellungen › PV-Anlagen) – aus klaren Stunden wird berechnet, welche Ausrichtung und Neigung am besten zu den Messwerten passen; Vorschlag mit einem Klick übernehmen
- Neu: **Unsicherheit** – Spanne (P10–P90) der eigenen Prognose als Band in den Diagrammen und als „von–bis“ bei PV heute; im Planer ein einstellbarer **Sicherheitsabschlag** (Einstellungen › Batterie: Aus / Mittel / Vorsichtig)
- Behoben: Die „genaueste Quelle“ wurde nach dem Tagesfehler gewählt, die Rangliste nach dem Stundenfehler – jetzt überall der Stundenfehler (der Planer konnte eine andere Quelle verwenden als angezeigt)

## 0.3.5

- Behoben: Die „genaueste Quelle“ (für Planung, Übersicht und die PV-Sensoren) wurde nach dem Tagesfehler gewählt, die Rangliste im Prognose-Check nach dem Stundenfehler – dadurch konnte der Planer eine andere Quelle verwenden als die, die als genaueste angezeigt wird. Jetzt zählt überall der Stundenfehler, denn der Planer rechnet Stunde für Stunde

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

- Neu: **Richtung umkehren** für Hausverbrauch, Netzleistung und Batterie-Leistung (Einstellungen › Sensoren) – z. B. für Speicher, die Entladen positiv melden. Darunter steht sofort, wie EnergyPilot den aktuellen Wert versteht („Batterie entlädt mit 737 W“)
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
