# Changelog

## 0.11.2

- Handy-App: Die Anleitung nennt die Adresse jetzt mit der IP-Adresse von Home Assistant statt mit dem Namen – „homeassistant.local“ wird nicht auf jedem Handy und nicht über VPN gefunden

## 0.11.1

- Einstellungen: neuer Reiter **„Handy-App“** mit der Anleitung für den Direktzugriff Schritt für Schritt. Er zeigt, welche Schritte schon erledigt sind (Passwort gesetzt, Port freigegeben), und nennt die fertige Adresse zum Öffnen auf dem Handy
- Die Anleitung empfiehlt jetzt Port 8199 statt 8099 – 8099 ist auf vielen Installationen schon belegt, dann startet das Add-on nicht („port 8099 is already in use“)

## 0.11.0

- **Als App auf dem Handy:** EnergyPilot lässt sich jetzt auch direkt öffnen – ohne die Oberfläche von Home Assistant – und auf dem Handy „zum Home-Bildschirm“ hinzufügen. Es startet dann im Vollbild mit eigenem Symbol. Dafür in der Konfiguration des Add-ons ein **Passwort für den Direktzugriff** setzen und unter „Netzwerk“ einen Port freigeben; beides ist standardmäßig aus, ohne Passwort bleibt EnergyPilot nur über Home Assistant erreichbar. Anleitung unter Einstellungen › Darstellung und in der Dokumentation
- Der Direktzugriff fragt das Passwort einmal ab und merkt sich die Anmeldung auf dem Gerät; nach fünf falschen Versuchen ist die Anmeldung für einige Minuten gesperrt. Ein neues Passwort meldet alle Geräte ab

## 0.10.1

- Übersicht: „Warum?“ öffnet die Erklärung jetzt direkt auf der Übersicht, statt zur Planung zu wechseln

## 0.10.0

Neues Aussehen der Übersicht, Handy-Ansicht und mehr Bewegung:

- **Energiefluss:** Die vier Kacheln für PV, Haus, Akku und Netz sind jetzt ein Bild. Punkte laufen entlang der Linien in Richtung des Stroms – je mehr Leistung, desto schneller. EnergyPilot teilt die Live-Werte dafür auf (PV → Haus, PV → Akku, PV → Netz, Akku → Haus, Netz → Haus, Netz ↔ Akku); ein Mauszeiger auf der Linie nennt die Leistung. Der Ring um den Akku zeigt den Ladezustand und pulsiert beim Laden
- **Empfehlung jetzt:** Die Karte ist in der Farbe der Empfehlung gehalten (Eigenverbrauch grün, Akku halten gelb, Netzladen blau) und zeigt als Streifen die Empfehlungen der nächsten zwölf Stunden
- **Diagramm-Legende:** Nicht gewählte Prognosequellen stehen hinter „Quellen vergleichen“ statt in der Legende. Behoben: Der erste Klick auf eine Quelle blendete alle übrigen Quellen ein
- **Handy:** Leiste am unteren Rand mit Übersicht, Planung, Preise, Verlauf und „Mehr“; größere Tippflächen; die Ranglisten im Prognose-Check erscheinen als Karten statt als breite Tabelle
- **Animationen:** Balken wachsen beim Öffnen von unten, die Markierung „jetzt“ pulsiert, der Tooltip gleitet mit dem Mauszeiger, Ranglistenplätze verschieben sich sichtbar. Die Übersicht wird beim Aktualisieren nicht mehr neu aufgebaut, sondern nur an den geänderten Stellen angepasst – laufende Animationen bleiben erhalten. Mit „Bewegung reduzieren“ im Betriebssystem ist alles abgeschaltet

## 0.9.3

- Solcast: Eine neu eingetragene Resource-ID oder ein neuer API-Schlüssel wird jetzt sofort abgerufen – bisher konnte es bis zur nächsten Stunde dauern, wenn die ID nach dem Schlüssel eingetragen wurde. Weiterhin höchstens ein Abruf pro Dachfläche und Stunde
- Solcast: Bei zwei Anlagen verdeckte ein erfolgreicher Abruf den Fehler der anderen – der Status nennt jetzt jede Anlage, bei der der Abruf fehlschlägt
- Einrichtung: Hinweise, wenn bei Solcast nur der Schlüssel oder nur die Resource-ID eingetragen ist (dann wurde bisher stillschweigend nichts abgerufen), wenn eine Anlage keine Resource-ID hat und solange der erste Abruf aussteht
- Übersicht › Datenquellen: „learn“ heißt jetzt „Lernmodell – berechnet vor …“

## 0.9.2

- Neues Wettermodell **DMI Harmonie** (2 km, Nordwesteuropa). Es ist zusammen mit **KNMI Harmonie** (2 km) jetzt standardmäßig aktiv; bei bestehenden Installationen werden beide einmalig eingeschaltet, ihr Prognose-Archiv wird automatisch nachgeladen. Wer eines davon wieder abschaltet, behält diese Wahl
- Prognosequellen: Knopf **„Anleitung“** für Solcast – Schritt für Schritt von der kostenlosen Anmeldung bis zum API-Schlüssel, mit Links und den Werten, die für jede Anlage bei Solcast einzutragen sind (Azimut bereits in die Zählweise von Solcast umgerechnet, Ost/West-Anlagen als eine flache Fläche)

## 0.9.1

Aus der Auswertung eines Diagnose-Exports:

- Behoben (Preise): Lieferte die Ersatzquelle für einen Tag Stundenpreise, lagen sie auf den Viertelstundenpreisen desselben Tages (ein Tag mit 42 statt 24 Stunden – doppelte Balken, verzerrte Durchschnitte). Ein neuer Preis ersetzt jetzt alle Einträge, mit denen er sich überschneidet; vorhandene Überschneidungen werden beim Start bereinigt
- PV-Prognose: Die Unsicherheitsspanne war zu schmal – an echten Daten lag die Erzeugung nur in 72 % der Stunden darin statt in 80 %. Sie ist jetzt so eingestellt, dass es 80 % sind (nachgeprüft: 79 %)
- Protokoll: Viele Speicher beziehen auch bei geladenem Akku ständig etwas Strom aus dem Netz (Regelung, Eigenverbrauch). EnergyPilot misst diesen Grundbezug in dunklen Stunden mit geladenem Akku und berücksichtigt ihn in der Nachrechnung – an echten Daten liegt „ohne EnergyPilot“ damit bei −0,15 € statt −0,44 € gegenüber gemessenen −0,23 €. Die Tagesansicht nennt den Wert
- Die Leistung des Akkus wird jetzt auch als Verlauf gespeichert (rückwirkend aus der Statistik) – damit lassen sich Wirkungsgrad und tatsächliche Lade- und Entladeleistung auswerten

## 0.9.0

- Einrichtung: neuer Knopf **„Diagnose-Export“** – lädt eine ZIP-Datei mit der Datenbank (alle Prognosen, Messwerte, Preise, Protokoll), den Einstellungen ohne Solcast-Schlüssel und dem aktuellen Zustand (Plan mit Erklärung, Live-Werte, gelernte Gewichte, Status, Einrichtungsprüfung). Damit lassen sich Prognosen, Lernen, Planung und Protokoll außerhalb von Home Assistant genau nachrechnen

## 0.8.3

Durchsicht der laufenden Installation:

- Behoben (Tagesverlauf): Forecast.Solar liefert nur Stunden mit Sonne und galt deshalb als „nur 13 Stunden berechnet“ (ausgegraut, ohne Platz). Vollständig ist eine Quelle jetzt, wenn sie alle Stunden mit Erzeugung abdeckt
- Behoben (Planung): Rundungsreste der Planung erschienen als „Aus dem Netz laden“ (z. B. 0,15 kWh zu 43 ct). Unter 0,2 kWh gibt es keine Netzladung mehr, der Akku bleibt dann wie er ist
- Behoben: „Akku leer“ stimmt in Übersicht und „Warum dieser Plan?“ jetzt überein (vorher 21:49 bzw. 21:00)
- Behoben: „−0,00 €“; Diagramme mit lauter Nullwerten zeigen eine normale Achse; kleine Netzbezüge auf der Kosten-Seite mit einer Nachkommastelle („0,5 kWh“ statt „0 kWh“)

## 0.8.2

- Behoben (Forecast.Solar „Abruflimit erreicht“): Jeder Durchlauf fragte alle Anlagen und Teilflächen ab – auch die Wiederholungen alle 15 Minuten ab 13 Uhr (bis die Preise für morgen da sind), „Jetzt abrufen“, gespeicherte Einstellungen und Neustarts. Mit drei Teilflächen waren so schnell die 12 erlaubten Abrufe pro Stunde erreicht. Jetzt wird jede Anlage höchstens einmal pro Stunde abgefragt (auch über Neustarts hinweg), nach „Abruflimit“ pausiert EnergyPilot eine Stunde, und eine geänderte Ausrichtung wird sofort neu abgefragt
- Einrichtung: Ein kurzzeitig nicht abrufbarer Prognosedienst ist nur noch ein Hinweis, solange seine letzte Prognose jünger als 3 Stunden ist (sie wird weiter verwendet); erst danach eine Warnung, mit dem Zeitpunkt der letzten erfolgreichen Prognose

## 0.8.1

- Behoben (Übersicht): Die Empfehlung konnte bis zu 5 Minuten alt sein – kurz nach einer vollen Stunde sogar noch die der vorigen Stunde (z. B. „Akku halten“, obwohl für die neue Stunde „Eigenverbrauch“ geplant war). Ist der Plan älter als 1 Minute oder aus einer anderen Stunde, rechnet die Übersicht jetzt vor der Anzeige neu; zu jeder vollen Stunde wird sofort neu geplant, auch für die Sensoren in Home Assistant. Die Empfehlung zeigt ihren Stand („Stand 06:02“)
- Planung: Die Farben im Diagramm „Strompreis & Fahrplan“ passen jetzt zum Stundenplan – Eigenverbrauch grün, Akku halten orange, Aus dem Netz laden blau

## 0.8.0

- Planung: neuer Knopf **„Warum dieser Plan?“** (auch „Warum?“ in der Übersicht). Die Erklärung wird aus dem aktuellen Plan berechnet: wann der Akku ohne Eingriff leer wäre und was Netzstrom danach kostet; für jede Phase „Akku halten“ bzw. „Aus dem Netz laden“ Uhrzeit, Preis, Menge, für welche Stunden die Energie aufgehoben wird (Vergleich mit dem Akku ohne Eingriff) und der Vorteil je kWh nach Verlusten; eine Nacht mit einzelnen kurzen Entladestunden erscheint als eine Phase. Bleibt der Akku im Eigenverbrauch, steht dort der Grund. Dazu die Regeln des Planers mit den eigenen Einstellungen
- Planung, Stundenplan: Beim Überfahren von „Akku halten“ oder „Aus dem Netz laden“ erscheint die Begründung

## 0.7.3

- Menü: Bei „Einrichtung“ steht die Anzahl der Probleme (rot) bzw. – wenn es keine gibt – der Hinweise (orange). Die Prüfung läuft beim Öffnen und alle 10 Minuten, der Hinweis ist also auf jeder Seite sichtbar
- Behoben (Einrichtung): Wechselrichter, die ohne Sonne abschalten und dann „unavailable“ melden, galten als Fehler. Ist gerade zu wenig Licht auf den Modulen, ist das jetzt „in Ordnung – Wechselrichter aus“. Auch „Messwerte veraltet“ zählt nur noch fehlende Stunden mit Tageslicht
- Behoben (Einrichtung): Ein nicht verfügbarer Sensor erschien zusätzlich als „in Ordnung“ mit „aktuell unavailable W“
- Übersicht: Schlafen die Wechselrichter, zeigt „PV-Erzeugung“ 0 W und „Wechselrichter aus – keine Sonne“ statt „Sensor in den Einstellungen wählen“

## 0.7.2

- Behoben (Protokoll): Fehlten zwischendurch Empfehlungen (Neustart oder Update des Add-ons), rechnete die Nachrechnung über die Lücke hinweg mit einem erfundenen Akkustand weiter – z. B. mit einem halb leeren Akku, der in Wirklichkeit längst voll war. Jetzt beginnt jeder zusammenhängende Abschnitt mit dem gemessenen Ladezustand; die Tagesansicht nennt die Anzahl der Abschnitte. An echten Daten stimmt die Nachrechnung damit fast genau mit der Messung überein (Einspeisung 5,3 statt 0,8 kWh, gemessen 5,4 kWh)

## 0.7.1

- Übersicht, Karte Akku: Die Vorhersage ist als solche gekennzeichnet – „lädt mit 302 W · Prognose: leer morgen um 08:47“ statt „reicht bis morgen 08:47“, sonst „Prognose: reicht über … hinaus“
- Übersicht, Karte Netz: Wie beim Akku steht unter dem Wert die Richtung – „Netzbezug – Strom wird gekauft“, „Einspeisung – Überschuss geht ins Netz“ oder „ausgeglichen“

## 0.7.0

- Lizenz: ab dieser Version PolyForm Strict 1.0.0 (nicht-kommerzielle Nutzung erlaubt, keine Weitergabe oder Veränderung); bis 0.6.4 MIT
- Prognose-Check: neue Karte **„Entwicklung über die Zeit“** – Genauigkeit der eigenen Prognose Woche für Woche neben dem besten Wettermodell bzw. „Wie vor einer Woche“, mit dem Vorsprung am Anfang und zuletzt und einem Urteil („lernt dazu“, „wird schlechter“, „keine klare Veränderung“), das nur erscheint, wenn die Veränderung größer ist als die Schwankung von Woche zu Woche
- Verbrauchsprognose genauer: Werktage und Wochenenden/Feiertage statt Mo–Fr/Sa/So, und die Prognose folgt zur Hälfte dem Verbrauchsniveau der letzten drei Tage. An echten Daten (30 Tage) sank der Fehler je Stunde von 32,7 auf 31,1 %, je Tag von 18,2 auf 17,1 %. Bundesweite Feiertage (DE, AT, CH) zählen wie Sonntage
- Einrichtung: neue Prüfung der **Energiebilanz** der letzten 14 Tage (PV + Netzbezug − Einspeisung − Hausverbrauch) – erkennt Sensoren, die zu viel oder zu wenig messen oder Lücken haben
- Planung: Endet der Plan heute um 24:00, weil die Preise für morgen noch fehlen, steht dabei „Preise für morgen ab ca. 13 Uhr“

## 0.6.4

- Einstellungen › Strompreis: Der Vergleich mit einem anderen Tarif lässt sich ein- und ausschalten. Ausgeschaltet verschwinden Vergleichs-Kennzahl, Linie, Spalten und die Freistrom-Karte von der Kosten-Seite; die eingetragenen Werte bleiben gespeichert

## 0.6.3

- Einstellungen › Strompreis: Erklärung der beiden Arten, die Einspeisung aufzuteilen, mit dem Ergebnis für die eigenen Anlagen; Übersicht der Vergütung je Anlage
- Einstellungen › Strompreis: Haben alle Anlagen eine eigene Vergütung, ist die allgemeine Einspeisevergütung als „nicht verwendet“ markiert; sonst steht dabei, für welche Anlagen sie gilt

## 0.6.2

- PV-Anlagen: optional eine eigene Einspeisevergütung je Anlage. Da es nur einen Zähler für die Einspeisung gibt, wird sie aufgeteilt – nach Anlagenleistung (kWp, Standard) oder nach der gemessenen Erzeugung jeder Anlage (Einstellungen › Strompreis › „Einspeisung aufteilen“)
- Kosten und Protokoll bewerten die Einspeisung jeder Stunde mit dem passenden Satz; die Planung rechnet mit dem nach kWp gewichteten Mittel. Die Einrichtung zeigt die Vergütung je Anlage

## 0.6.1

- Kosten: Der dynamische Tarif lässt sich wahlweise mit einem Festpreistarif oder mit einer **Flat mit Freistrom** vergleichen (Einstellungen › Strompreis › „Vergleichen mit“). Für die Flat: Grundgebühr, Freistrom pro Jahr, Preis über dem Freistrom, eigene Einspeisevergütung und Beginn des Abrechnungsjahres
- Kosten: Der Freistrom wird wie bei der Abrechnung ab Beginn des Abrechnungsjahres fortlaufend verbraucht; eine neue Karte zeigt den Stand („1.366 von 2.500 kWh“) und wie lange der Rest beim Verbrauch der letzten 30 Tage reicht

## 0.6.0

- Protokoll: Die Nachrechnung nutzt jetzt den gesamten gemessenen Hausverbrauch einschließlich E-Auto, das auch aus dem Akku geladen wird. Bisher rechnete sie nur mit dem Grundverbrauch; lief z. B. der Heizstab mit PV-Überschuss, wurde dieser Strom fälschlich als Einspeisung gezählt
- Neue Einstellung beim Heizstab: „läuft nur mit PV-Überschuss“ (Standard). Ein solcher Heizstab nimmt in der Nachrechnung nur auf, was sonst eingespeist würde – er leert nie den Akku und kauft keinen Netzstrom
- Protokoll: Neu ist die gemessene Stromrechnung aus Netzbezug und Einspeisung – als Kennzahl oben, als Spalte „gemessen“ in der Tabelle und als Gegenprobe zur Nachrechnung
- Einstellungen › Sensoren: Nach dem Speichern war der Speichern-Knopf wieder aktiv, obwohl nichts mehr zu speichern war
- Protokoll, Tagesansicht: Stromrechnung für „gemessen“, „ohne EnergyPilot“, „mit EnergyPilot“ und „optimal“ aufgeteilt in Bezug (kWh, €) und Einspeisung (kWh, €); Verbrauch des Tages mit Anteil von Heizstab und E-Auto; je Stunde Gesamtverbrauch und gemessener Netzbezug bzw. Einspeisung

## 0.5.9

- Planung: Ruht der Akku, steht statt „aus PV oder Netz“ konkret da, woher der Strom gerade kommt – z. B. „PV deckt den Verbrauch – 1,20 kW Überschuss gehen ins Netz“ oder „900 W aus PV, 600 W aus dem Netz“

## 0.5.8

- Tagesverlauf und Prognose-Check: Die Umschaltung „Auswertung für“ (Anlagen / Grundverbrauch) steht als eigene, hervorgehobene Leiste über den Filtern; Tag, Zeitraum und Prognose sind beschriftet
- Planung: Die Reichweite erscheint nur noch, wenn der Akku entlädt – und wird mit seiner tatsächlichen Entladeleistung berechnet statt mit dem ganzen Hausverbrauch. Lädt der Akku, steht dort „Akku lädt“ mit Leistung und voraussichtlicher Uhrzeit für „voll“; ruht er, „Akku ruht“ bzw. „Akku voll“. Der Sensor `sensor.energypilot_akku_reichweite` ist dann „unbekannt“ und hat das neue Attribut `battery_state`

## 0.5.7

- Tagesverlauf und Prognose-Check: Die Auswahl „Alle Anlagen / einzelne Anlage / Grundverbrauch“ ist jetzt eine Reihe von Schaltflächen statt einer Aufklappliste

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
