# Paktwerk

Paktwerk ist ein lokaler Forschungsprototyp für bilaterale B2B-Verhandlungen. Einkauf und Lieferant arbeiten im selben Raum. Jede Firma kann selbst verhandeln, ihren eigenen Agenten beauftragen und einen simulierten Abschluss persönlich freigeben. Die Agenten verhandeln über die Claude API. Jede Firma hat ihren eigenen, unabhängigen Agenten mit eigenem Mandat.

## Start

Python 3.10 oder neuer und ein Zugang zur Claude API werden benötigt. Die Claude-Agenten verwenden das Paket `anthropic`. Server, SQLite, Tests und die regelbasierten Agenten kommen mit der Standardbibliothek aus. Schrift und Bild liegen im Projekt.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env && chmod 600 .env   # Schlüssel in .env eintragen
.venv/bin/python app.py
```

`app.py` und `research.py --agents claude` lesen `ANTHROPIC_API_KEY` aus der Datei `.env` im Projektordner. Eine in der Shell gesetzte Umgebungsvariable hat Vorrang. `.env` steht in `.gitignore` und wird nicht eingecheckt.

Standardmäßig verhandeln beide Agenten mit `claude-opus-5-5` und dem Denkaufwand `medium`. Mit `--model` und `--effort` lassen sich beide ändern. `--agents regeln` startet die deterministischen, regelbasierten Agenten ohne API-Zugang. Fehlt der Zugang oder ist die API nicht erreichbar, gibt der betroffene Agent die Vertretung mit einem Hinweis im Gesprächsverlauf an seine Firma zurück. Jeder neue Demoraum löst sofort einen ersten Zug des Einkaufsagenten aus und damit einen kostenpflichtigen API-Aufruf.

[Demo im Browser öffnen](http://127.0.0.1:8000). Ein neuer Browser-Tab ohne Raumzugang erhält einen eigenen Demoraum in der Rolle des Einkaufs. Das Angebot über 290 € am zehnten Werktag gehört zum vorbereiteten Beispielverlauf. Über **Neue Verhandlung** legt Firma A einen eigenen Gegenstand, Firmen, Frist, Schrittgrenze und Käufermandat fest. Ein neu gegründeter Raum beginnt mit der Anfrage von A.

## Vorführung in zwei Tabs

Die folgenden Schritte beschreiben den Referenzverlauf der regelbasierten Agenten (`--agents regeln`). Claude-Agenten formulieren frei. Rückfragen, Preise und die Zahl der Schritte können deshalb abweichen. Die Mandatsgrenzen und der Freigabeablauf gelten unverändert.

1. Im Einkauf **Gegenfirma einladen → Gastansicht öffnen** wählen. Der zweite Tab gehört dem Lieferanten. Für eine zweite Person lässt sich derselbe Einmallink kopieren. Wer den Link einlöst, erhält die persönliche Freigabeberechtigung für B.
2. Als Lieferant **„Wir können einen Teil früher liefern“** schreiben. Der Käuferagent fragt nach Teilmenge, Liefertermin und Gesamtpreis. Auf **„Wir bestätigen 40 Stück binnen fünf Werktagen.“** folgt nur noch die Preisfrage.
3. **An meinen Agenten übergeben** wählen, das private Profil **Flexible Kapazität** prüfen und das Mandat erteilen. Der Verkäuferagent ergänzt den offenen Preis. Zur Demonstration der Rückübernahme während der viersekündigen Vorbereitung **Selbst übernehmen** wählen und eine eigene Nachricht senden. Eine erneute Übergabe verwendet das gespeicherte Mandat.
4. **Angebot prüfen** zeigt alle Konditionen, Änderungen zur Vorversion und die Bewertung der eigenen Firma. Im Referenzfall sind es 100 Boxen für **310 € einschließlich Lieferung**, davon 40 bis zum fünften und alle bis zum zehnten Werktag. In jedem Tab **V2 persönlich freigeben** wählen.
5. Für die Versionsprüfung zunächst nur im Einkauf freigeben. Der Lieferant kann **Selbst übernehmen → Angebot erstellen** wählen und den Gesamtpreis auf 315 € ändern. Beide Freigaben für V3 sind jetzt offen. Erst die zweite persönliche Freigabe schließt den Raum ab.

Für eine vollständig manuelle Lieferantenrolle genügt **Angebot erstellen**. Für zwei Agenten kann B sofort nach dem Beitritt übergeben. Im Profil **Knappe Kapazität** kostet die fristgerechte Lieferung mindestens 335 €. Der Käuferagent beendet den Austausch mit dokumentiertem Grund.

Die Rollenberechtigung bleibt beim Neuladen im jeweiligen Tab erhalten. Für eine Vorführung auf zwei Geräten den Server mit `python3 app.py --host 0.0.0.0` im vertrauenswürdigen lokalen Netz starten und den Einkauf über die erreichbare LAN-Adresse öffnen. Der Einladungslink übernimmt diese Adresse. Der lokale Demoserver verwendet HTTP. Räume und vorbereitete Antworten liegen standardmäßig in `.paktwerk/rooms.sqlite3`. Mit `--db` und `--port` lassen sich Datenbank und Port auswählen.

## Tests und Forschungsläufe

```sh
python3 -m unittest discover -s tests -v
python3 research.py
python3 research.py --scenario service --repeats 3 --json > /tmp/paktwerk-wartung.json
.venv/bin/python research.py --agents claude --json > /tmp/paktwerk-claude.json
```

Die Tests ersetzen die Claude API durch je einen simulierten Client pro Firma und laufen ohne Netz. Sie prüfen unter anderem, dass kein Agent Mandat oder Notiz der Gegenseite zu sehen bekommt. `research.py` verwendet standardmäßig die regelbasierten Agenten. Mit `--agents claude` verhandeln in jedem Lauf zwei Claude-Agenten. Diese Läufe sind nicht deterministisch und kosten API-Guthaben. Die Referenzwerte unten gelten für die regelbasierten Agenten.

Das **Forschungslabor** im Browser führt denselben Vergleich mit den regelbasierten Agenten aus und exportiert JSON. Jeder Lauf hat eine eigene In-Memory-Datenbank, dieselbe logische Startzeit und zwei simulierte menschliche Freigabeaktionen. Beide Firmen verwenden im jeweiligen Lauf die gewählte Strategie. Wiederholungen derselben Bedingung sind deterministisch.

| Szenario und Profil | Direktes Paket | Schrittweise Konzession |
| --- | --- | --- |
| Versandboxen, flexibel | 310 € nach 4 Schritten | 320 € nach 6 Schritten |
| Versandboxen, knapp | Abbruch nach 3 Schritten | Abbruch nach 7 Schritten |
| Wartung, flexibel | 16 Stunden binnen 8 Werktagen für 1.750 € | Gleicher Umfang und Termin für 1.850 € |
| Wartung, knapp | Abbruch | Abbruch |

Der Referenzvergleich umfasst acht Läufe. Alle vier lösbaren Bedingungen enden mit einer Einigung, alle vier knappen Bedingungen mit einem Abbruch. Die Protokolle enthalten Szenario- und Strategieversion, Mandatsrevision und Fingerabdruck der Testeingaben, Schritte, Angebote, Abschluss, Abbruchgrund und Nutzen je Firma. Die Auswertung zählt beim Versand blockierte Aktionen und prüft versandte Agentenangebote sowie Empfehlungen nochmals gegen das jeweilige Mandat.

Der Nutzen des Einkaufs entspricht den Kosten einer gleichwertigen Ersatzbeschaffung abzüglich Paketpreis. Der Nutzen des Lieferanten entspricht Erlös abzüglich eigener Paketkosten und Deckungsbeitrag der Alternative. Bei Abbruch wird die Alternative realisiert, der Mehrnutzen beträgt auf beiden Seiten null. Die Lösbarkeit ermittelt ausschließlich die Forschungsauswertung aus den Testmandaten.

## Verhandlungsmodell

- Einkauf und Lieferant werden von zwei getrennten Claude-Agenten vertreten. Jeder hat einen eigenen API-Client, einen eigenen System-Prompt mit dem Mandat seiner Firma und eine private Arbeitsnotiz zwischen den Zügen. Ein Agent erhält nie Mandat oder Notiz der Gegenseite, sondern nur den öffentlichen Verlauf mit Angebotsversionen, das öffentliche Szenario und die Restzeit. Die eigene Firma sieht die Notiz ihres Agenten unter **Mein Mandat**. Jeder Agent sendet das Mandat seiner Firma und den öffentlichen Verlauf an die Claude API.
- In jedem Zug wählt ein Agent über ein festes JSON-Schema eine von vier Aktionen: verbindliches Angebot, Nachricht, Empfehlung des gegnerischen Angebots zur persönlichen Freigabe oder begründeter Abbruch. Die Plattform prüft Angebote und Empfehlungen gegen das eigene Mandat. Einen unzulässigen Zug erhält der Agent mit Begründung zurück und kann ihn bis zu zweimal korrigieren. Danach geht die Vertretung an die Firma zurück. Den verbindlichen Angebotstext erzeugt die Plattform aus dem geprüften Paket. Die Begleitnachricht des Agenten steht getrennt darüber.
- Der Modellaufruf läuft außerhalb der Schreibtransaktion. Eine Antwort wird nur versandt, wenn sich Verlauf, Vertretung und eigenes Mandat währenddessen nicht geändert haben. Wer während der Vorbereitung selbst übernimmt, verwirft die Antwort. Lehnt das Modell eine Anfrage aus Sicherheitsgründen ab, übernimmt über den Parameter `fallbacks` serverseitig ein Ersatzmodell.
- Mit `--agents regeln` verhandeln stattdessen die deterministischen, regelbasierten Agenten. Preise werden in ganzen Cent verarbeitet.
- Freitext bleibt im Gespräch erhalten. Eindeutige Angaben wie „Wir können 40 Stück früher liefern“, „Die Teillieferung erfolgt binnen fünf Werktagen“ oder „Der Gesamtpreis beträgt 310 €“ können offene Punkte klären. Unbestimmte Angaben führen zu Rückfragen. Ein vollständiges Angebot erhält erst beim strukturierten Versand eine Version. Für frei formulierte, komplexe Konditionen steht das Angebotsformular zur Verfügung.
- Die Freigabe bezieht sich auf eine konkrete Version. Der Server bindet jede Aktion an die berechtigte Firma. Ein Wechsel der Vertretung, die letzte Versandprüfung und das Speichern eines Ereignisses sind durch SQLite-Schreibtransaktionen serialisiert. Der Versand prüft aktive Vertretung, Vertretungswechsel, Raumrevision, Angebotsversion, Frist und eigenes Mandat. Die zweite passende Freigabe schreibt den Abschluss atomar.
- Der Dienstleistungsfall verwendet dieselben Agenten, dieselbe Versandwarteschlange und denselben Freigabeablauf. Szenarien definieren Felder, Paketregeln, Freitextmuster und Formulierungen. Private Testprofile liefern die leistbaren Pakete und wirtschaftlichen Grenzen.

Die Claude-Agenten liegen in [claude.py](paktwerk/claude.py), die regelbasierte Agentenlogik und die Mandatsprüfung in [domain.py](paktwerk/domain.py), der transaktionale Ablauf in [store.py](paktwerk/store.py). Die [Szenarien](paktwerk/scenarios.py), [privaten Testprofile](paktwerk/templates.py) und [ausführbaren Abnahmefälle](tests/test_acceptance.py) lassen sich unabhängig davon einsehen.

<details>
<summary>Bildnachweis für das Versandboxenmotiv</summary>

Das integrierte ImageGen-Werkzeug erzeugte das [Versandboxenmotiv](web/assets/versandboxen.webp) mit diesem Prompt.

> Use case: product-mockup. Extremely wide horizontal product photograph for the header of a B2B procurement workspace. Two beautifully lit unbranded matte kraft corrugated shipping boxes, one open with crisp flaps and a second compact closed box next to it. Three-quarter view, tactile cardboard fiber and fine corrugation, restrained high-end industrial product photography. Place the entire still life on the right-hand side, with spacious empty uninterrupted dark deep forest teal background on the left half. A continuous monochromatic dark pine-green studio floor and backdrop (#123f38), subtle grounded shadows, warm directional studio light from the upper left. Frame the entire group of boxes with generous top and bottom margin to allow a wide banner crop. No text, labels, logos, people or other objects.

</details>
