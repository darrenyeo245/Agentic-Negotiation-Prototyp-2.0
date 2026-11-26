# Paktwerk

Paktwerk ist ein lokaler Forschungsprototyp für Agentic Negotiation: bilaterale B2B-Verhandlungen zwischen KI-Agenten. Einkauf und Lieferant arbeiten im selben Raum. Jede Firma beauftragt ihren eigenen, unabhängigen Claude-Agenten mit einem privaten Mandat. Die Menschen behalten dabei die Kontrolle: Sie können jederzeit selbst übernehmen, und ein Abschluss gilt erst, wenn beide Firmen ihn persönlich freigegeben haben.

## Start

Python 3.10 oder neuer und ein Zugang zur Claude API werden benötigt. Die Agenten verwenden das Paket `anthropic`. Server, SQLite und Tests kommen mit der Standardbibliothek aus. Schrift und Bild liegen im Projekt.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env && chmod 600 .env   # Schlüssel in .env eintragen
.venv/bin/python app.py
```

Die Claude-Agenten lesen `ANTHROPIC_API_KEY` direkt aus der Datei `.env` im Projektordner. Der Wert aus `.env` hat Vorrang vor einer Shell-Variablen. Fehlt die Datei oder der Eintrag, gilt `ANTHROPIC_API_KEY` aus der Umgebung. `.env` steht in `.gitignore` und wird nicht eingecheckt.

Standardmäßig verhandeln beide Agenten mit `claude-opus-5-5` und dem Denkaufwand `medium`. Mit `--model` und `--effort` lassen sich beide ändern. Ohne gültigen Schlüssel startet der Server nicht. Ist die API während einer Verhandlung nicht erreichbar, gibt der betroffene Agent die Vertretung mit einem Hinweis im Gesprächsverlauf an seine Firma zurück. Jeder neue Demoraum löst sofort einen ersten Zug des Einkaufsagenten aus und damit einen kostenpflichtigen API-Aufruf.

[Paktwerk im Browser öffnen](http://127.0.0.1:8000). Ein neuer Browser-Tab startet im Arbeitsbereich **Meine Verhandlungsräume**. **Demoraum öffnen** legt einen vorbereiteten Raum in der Rolle des Einkaufs an. Das Angebot über 290 € am zehnten Werktag gehört zum vorbereiteten Beispielverlauf. Über **Neue Verhandlung** legt Firma A einen eigenen Gegenstand, Firmen, Frist, Schrittgrenze und Käufermandat fest. Ein neu gegründeter Raum beginnt mit der Anfrage von A.

## Vorführung in zwei Tabs

Die Agenten formulieren frei. Rückfragen, Preise und die Zahl der Schritte unterscheiden sich daher von Lauf zu Lauf. Mandatsgrenzen und Freigabeablauf gelten immer.

1. Im Arbeitsbereich **Demoraum öffnen** und danach im Einkauf **Gegenfirma einladen → Gastansicht öffnen** wählen. Der zweite Tab gehört dem Lieferanten. Für eine zweite Person lässt sich derselbe Einmallink kopieren. Wer den Link einlöst, erhält die persönliche Freigabeberechtigung für B.
2. Als Lieferant selbst eine Nachricht schreiben, etwa **„Wir können einen Teil früher liefern.“** Der Einkaufsagent liest die Nachricht und antwortet, zum Beispiel mit einer Frage nach Menge, Termin und Preis.
3. **An meinen Agenten übergeben** wählen, das private Profil **Flexible Kapazität** prüfen und das Mandat erteilen. Der Lieferantenagent übernimmt mit dem bisherigen Verlauf. Zur Demonstration der Rückübernahme während der viersekündigen Vorbereitung **Selbst übernehmen** wählen und eine eigene Nachricht senden. Die vorbereitete Antwort des Agenten wird dann verworfen. Eine erneute Übergabe verwendet das gespeicherte Mandat.
4. Sobald ein Agent ein Angebot zur Freigabe empfiehlt, zeigt **Angebot prüfen** alle Konditionen, Änderungen zur Vorversion und die Bewertung der eigenen Firma. In jedem Tab die Version **persönlich freigeben**.
5. Für die Versionsprüfung zunächst nur im Einkauf freigeben. Der Lieferant kann **Selbst übernehmen → Angebot erstellen** wählen und den Gesamtpreis ändern. Beide Freigaben für die neue Version sind jetzt offen. Erst die zweite persönliche Freigabe schließt den Raum ab.

Für eine vollständig manuelle Lieferantenrolle genügt **Angebot erstellen**. Für zwei Agenten kann B sofort nach dem Beitritt übergeben. Im Profil **Knappe Kapazität** kostet die fristgerechte Lieferung mindestens 335 € und damit mehr, als der Einkauf ausgeben darf. Eine Einigung ist dann nicht möglich, und einer der Agenten beendet den Austausch mit dokumentiertem Grund.

Die Rollenberechtigung bleibt beim Neuladen im jeweiligen Tab erhalten. Für eine Vorführung auf zwei Geräten den Server mit `python3 app.py --host 0.0.0.0` im vertrauenswürdigen lokalen Netz starten und den Einkauf über die erreichbare LAN-Adresse öffnen. Der Einladungslink übernimmt diese Adresse. Der lokale Demoserver verwendet HTTP. Räume und vorbereitete Antworten liegen standardmäßig in `.paktwerk/rooms.sqlite3`. Mit `--db` und `--port` lassen sich Datenbank und Port auswählen.

## Tests und Forschungsläufe

```sh
python3 -m unittest discover -s tests -v
.venv/bin/python research.py --scenario boxes --profile flexibel --strategy direkt --repeats 5
.venv/bin/python research.py --repeats 10 --parallel 4 --out .paktwerk/serien/serie.jsonl
```

Die Tests ersetzen die Claude API durch je einen simulierten Client pro Firma und laufen ohne Netz und ohne Kosten. Die Agenten durchlaufen dabei ihren echten Code mit Prompt, Antwortschema, Mandatsprüfung und Korrekturversuchen. Die Tests prüfen unter anderem, dass kein Agent Mandat oder Notiz der Gegenseite zu sehen bekommt, dass ein Mensch eine vorbereitete Agentenantwort jederzeit verwerfen kann und dass nur beidseitig freigegebene Versionen gelten.

`research.py` lässt zwei Claude-Agenten auf dem echten Plattformablauf verhandeln, mit logischer Uhr und zwei simulierten persönlichen Freigaben. Eine Serie kombiniert zwei Szenarien, zwei Lieferantenprofile und zwei Strategien zu acht Bedingungen und wiederholt jede Bedingung so oft wie mit `--repeats` angegeben. Beide Firmen verwenden im jeweiligen Lauf dieselbe Strategie. Jeder Lauf kostet API-Guthaben, mit `claude-opus-5-5` und Denkaufwand `medium` etwa 0,07–0,14 US$ im Profil flexibel und 0,17–0,36 US$ im Profil knapp.

`--profile` und `--strategy` beschränken die Serie auf einzelne Bedingungen. `--parallel` lässt mehrere Läufe gleichzeitig verhandeln, und `--out` hängt jeden fertigen Lauf sofort als JSON-Zeile an eine Datei an. Ein ausgefallener Lauf bricht die Serie nicht ab. Jeder Lauf enthält den Gesprächsverlauf, jede Agentenentscheidung mit privater Notiz, Korrekturversuche mit Ablehnungsgrund, Tokenverbrauch, Dauer und das tatsächlich antwortende Modell. Die Ausgabe zeigt am Ende die Streuung je Bedingung und eine Kostenschätzung zum Listenpreis.

### Lieferantenprofile

Die privaten Testprofile in [templates.py](paktwerk/templates.py) legen fest, was den Lieferanten die angefragte Leistung kostet. Das Mandat des Einkaufs ist in beiden Profilen gleich.

| | Versandboxen: 40 Stück bis Tag 5, Rest bis Tag 10 | Wartung: 16 Stunden bis Tag 8 |
| --- | --- | --- |
| Einkauf: Zielpreis / harte Grenze | 305 € / 320 € | 1.700 € / 1.900 € |
| Lieferant **flexibel**: Kosten / Untergrenze / Zielpreis | 285 € / 300 € / 310 € | 1.580 € / 1.680 € / 1.750 € |
| Lieferant **knapp**: Kosten / Untergrenze / Zielpreis | 325 € / 335 € / 335 € | 1.970 € / 2.050 € / 2.050 € |

Im Profil flexibel hat der Lieferant freie Kapazität, und es gibt einen Einigungsbereich von 300–320 € bzw. 1.680–1.900 €. Im Profil knapp ist die Kapazität ausgelastet, die frühe Leistung braucht Zusatzaufwand, und die Untergrenze des Lieferanten liegt über der Grenze des Einkaufs. Eine Einigung ist dann nicht möglich. Das günstigere Paket ohne frühe Teilleistung kann der Lieferant in beiden Profilen anbieten, es erfüllt aber die Vorgaben des Einkaufs nicht. Die Forschungsauswertung kennt beide Mandate und markiert jeden Lauf als lösbar oder unlösbar.

Der Nutzen des Einkaufs entspricht den Kosten einer gleichwertigen Ersatzbeschaffung abzüglich Paketpreis. Der Nutzen des Lieferanten entspricht Erlös abzüglich eigener Paketkosten und Deckungsbeitrag der Alternative. Bei Abbruch wird die Alternative realisiert, der Mehrnutzen beträgt auf beiden Seiten null. Die Lösbarkeit ermittelt ausschließlich die Forschungsauswertung aus den Testmandaten.

## Verhandlungsmodell

- Einkauf und Lieferant werden von zwei getrennten Claude-Agenten vertreten. Jeder hat einen eigenen API-Client, einen eigenen System-Prompt mit dem Mandat seiner Firma und eine private Arbeitsnotiz zwischen den Zügen. Ein Agent erhält nie Mandat oder Notiz der Gegenseite, sondern nur den öffentlichen Verlauf mit Angebotsversionen, das öffentliche Szenario und die Restzeit. Die eigene Firma sieht die Notiz ihres Agenten unter **Mein Mandat**. Jeder Agent sendet das Mandat seiner Firma und den öffentlichen Verlauf an die Claude API.
- In jedem Zug wählt ein Agent über ein festes JSON-Schema eine von vier Aktionen: verbindliches Angebot, Nachricht, Empfehlung des gegnerischen Angebots zur persönlichen Freigabe oder begründeter Abbruch. Die Plattform prüft Angebote und Empfehlungen gegen das eigene Mandat. Einen unzulässigen Zug erhält der Agent mit Begründung zurück und kann ihn bis zu zweimal korrigieren. Danach geht die Vertretung an die Firma zurück. Den verbindlichen Angebotstext erzeugt die Plattform aus dem geprüften Paket. Die Begleitnachricht des Agenten steht getrennt darüber.
- Der Modellaufruf läuft außerhalb der Schreibtransaktion. Eine Antwort wird nur versandt, wenn sich Verlauf, Vertretung und eigenes Mandat währenddessen nicht geändert haben. Wer während der Vorbereitung selbst übernimmt, verwirft die Antwort. Lehnt das Modell eine Anfrage aus Sicherheitsgründen ab, übernimmt über den Parameter `fallbacks` serverseitig ein Ersatzmodell.
- Jede Firma kann jederzeit selbst übernehmen. Eine Übernahme verwirft eine vorbereitete, noch nicht versandte Agentenantwort, auch über einen Neustart des Servers hinweg. Bei einer erneuten Übergabe arbeitet der Agent mit dem vollständigen Verlauf weiter. Preise werden in ganzen Cent verarbeitet.
- Freitext ist unverbindlich. Die Agenten lesen Nachrichten der Gegenseite selbst und antworten darauf. Verbindlich ist nur ein vollständiges, strukturiertes Angebot, das beim Versand eine Version erhält. Für frei formulierte, komplexe Konditionen steht Menschen das Angebotsformular zur Verfügung.
- Die Freigabe bezieht sich auf eine konkrete Version. Der Server bindet jede Aktion an die berechtigte Firma. Ein Wechsel der Vertretung, die letzte Versandprüfung und das Speichern eines Ereignisses sind durch SQLite-Schreibtransaktionen serialisiert. Der Versand prüft aktive Vertretung, Vertretungswechsel, Raumrevision, Angebotsversion, Frist und eigenes Mandat. Die zweite passende Freigabe schreibt den Abschluss atomar.
- Der Dienstleistungsfall verwendet dieselben Agenten, dieselbe Versandwarteschlange und denselben Freigabeablauf. Szenarien definieren Felder, Paketregeln und Formulierungen. Private Testprofile liefern die leistbaren Pakete und wirtschaftlichen Grenzen.

Die Claude-Agenten liegen in [claude.py](paktwerk/claude.py), die Mandatsprüfung in [domain.py](paktwerk/domain.py), der transaktionale Ablauf in [store.py](paktwerk/store.py). Die [Szenarien](paktwerk/scenarios.py), [privaten Testprofile](paktwerk/templates.py) und [ausführbaren Abnahmefälle](tests/test_acceptance.py) lassen sich unabhängig davon einsehen.

<details>
<summary>Bildnachweis für das Versandboxenmotiv</summary>

Das integrierte ImageGen-Werkzeug erzeugte das [Versandboxenmotiv](web/assets/versandboxen.webp) mit diesem Prompt.

> Use case: product-mockup. Extremely wide horizontal product photograph for the header of a B2B procurement workspace. Two beautifully lit unbranded matte kraft corrugated shipping boxes, one open with crisp flaps and a second compact closed box next to it. Three-quarter view, tactile cardboard fiber and fine corrugation, restrained high-end industrial product photography. Place the entire still life on the right-hand side, with spacious empty uninterrupted dark deep forest teal background on the left half. A continuous monochromatic dark pine-green studio floor and backdrop (#123f38), subtle grounded shadows, warm directional studio light from the upper left. Frame the entire group of boxes with generous top and bottom margin to allow a wide banner crop. No text, labels, logos, people or other objects.

</details>
