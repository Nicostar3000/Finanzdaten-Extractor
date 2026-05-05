# PDF Finanzdaten Extraktor

Ein Python-Tool zum Auslesen, Prüfen, Visualisieren und Exportieren von Finanztransaktionen aus Broker-PDFs. Das Projekt bietet eine einfache GUI für die manuelle Arbeit, eine Diagramm-Ansicht für Portfolio-Auswertungen und eine CLI für wiederholbare Exporte.

## Funktionen

- PDF-Textextraktion mit `pypdf`
- Regelbasierte Erkennung von Broker, Depot, Datum, Positionen, Kursen, Stückzahlen, Beträgen und Gebühren
- Unterstützung für einzelne PDF-Dateien und komplette Ordner
- GUI zum Sammeln und Exportieren ausgewählter PDFs
- Diagramm-Viewer mit Tabellen, Validierung, Brokerfilter und interaktivem Kreisdiagramm
- CSV-Export im Semikolon-Format für Excel
- Automatische Dateinamen-Kollisionserkennung: `datei.csv`, `datei (1).csv`, `datei (2).csv`
- CLI mit eindeutigen Standardnamen wie `Portfolio-CSV-20260504-171530.csv`

## Installation

Voraussetzung ist Python 3.10 oder neuer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Alternativ kann unter Windows auch der Python-Launcher verwendet werden:

PowerShell
py -m pip install -r requirements.txt
Verwendung
GUI starten
Ohne Parameter startet die Anwendung im GUI-Modus:

PowerShell
py main.py
In der GUI können PDF-Dateien oder Ordner ausgewählt werden. Anschließend stehen zwei Wege offen:

Als CSV speichern: exportiert die markierten PDFs direkt
Daten anzeigen & visualisieren: öffnet den Viewer mit Tabellen, Diagrammen und CSV-Export
CLI verwenden
Die Kommandozeile läuft ausschließlich über main.py.

PowerShell
py main.py --input PDFs
py main.py --input PDFs --output output\portfolio.csv
py main.py --input PDFs --chart
py main.py --input PDFs\beleg.pdf output\weitere_pdfs
Parameter:

Parameter	Beschreibung
--input	Eine oder mehrere PDF-Dateien oder Ordner.
--output	Optionaler CSV-Zielpfad oder Zielordner. Setzt --input voraus.
--chart	Öffnet nach der Verarbeitung die Diagramm-Ansicht. Setzt --input voraus.
Wenn --input gesetzt ist und --output fehlt, wird automatisch im aktuellen Ordner eine CSV-Datei mit eindeutigem Zeitstempel erstellt.

Projektstruktur
Text
.
├── main.py                 # Einziger direkter Programmeinstieg
├── requirements.txt        # Python-Abhängigkeiten
├── src/
│   ├── cli.py              # CLI-Ablauf und Konsolenausgabe
│   ├── csv_export.py       # Gemeinsame CSV-Exportlogik
│   ├── gui.py              # PDF-Auswahl-GUI
│   ├── gui_viewer.py       # Tabellen, Diagramme und Viewer-Export
│   ├── utils.py            # Gemeinsame Hilfsfunktionen
│   └── core/
│       ├── file_selector.py
│       ├── financial_parser.py
│       └── pdf_extractor.py
Architektur
main.py entscheidet, ob die GUI oder die CLI gestartet wird. Alle anderen Module sind bewusst nicht direkt ausführbar und stellen nur wiederverwendbare Klassen oder Funktionen bereit.

Der fachliche Ablauf ist:

FileSelector sammelt PDF-Dateien aus Dateien oder Ordnern.
PDFExtractor liest den Text mit pypdf.
FinancialParser erkennt Transaktionen und Metadaten.
csv_export.write_transactions_csv schreibt die Daten in ein einheitliches CSV-Format.
DataViewerApp visualisiert und filtert die Daten bei Bedarf.
CSV-Export
Der Export verwendet ein Semikolon als Trennzeichen und bereinigt Zeilenumbrüche sowie Semikolons innerhalb von Textfeldern. Dadurch bleibt die Datei in Excel stabil lesbar.

Wenn eine Datei bereits existiert, überschreibt das Programm sie nicht. Stattdessen wird automatisch ein freier Name erzeugt:

Text
portfolio.csv
portfolio (1).csv
portfolio (2).csv
Entwicklung
Syntaxprüfung:

PowerShell
py -m py_compile main.py src\cli.py src\csv_export.py src\gui.py src\gui_viewer.py src\utils.py src\core\file_selector.py src\core\financial_parser.py src\core\pdf_extractor.py
CLI-Test mit Beispielordner:

PowerShell
py main.py --input PDFs --output output\test-export.csv

Hinweise
Das Projekt ist auf Broker-PDFs mit textbasierter PDF-Struktur ausgelegt.
Eingescannte PDFs ohne eingebetteten Text benötigen OCR und werden aktuell nicht unterstützt.
Der Parser ist regelbasiert. Neue Broker-Layouts können durch zusätzliche Muster in src/core/financial_parser.py ergänzt werden.
