# PDF Finanzdaten Extraktor

Ein Python-Tool zum Auslesen, Prüfen, Visualisieren und Exportieren von Finanztransaktionen aus Broker-PDFs. Das Projekt bietet eine einfache GUI für die manuelle Arbeit, eine Diagramm-Ansicht für Datenvisualisierung und eine CLI für automatisierte Batch-Verarbeitung.

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
```

Alternativ kann unter Windows auch der Python-Launcher verwendet werden:

```powershell
py -m pip install -r requirements.txt
```

## Verwendung

### GUI starten

Ohne Parameter startet die Anwendung im GUI-Modus:

```powershell
py main.py
```

In der GUI können PDF-Dateien oder Ordner ausgewählt werden. Anschließend stehen zwei Wege offen:

- `Als CSV speichern`: exportiert die markierten PDFs direkt
- `Daten anzeigen & visualisieren`: öffnet den Viewer mit Tabellen, Diagrammen und CSV-Export

### CLI verwenden

Die Kommandozeile läuft ausschließlich über `main.py`.

```powershell
py main.py --input PDFs
py main.py --input PDFs --output output\portfolio.csv
py main.py --input PDFs --chart
py main.py --input PDFs\beleg.pdf output\weitere_pdfs
```

Parameter:

| Parameter | Beschreibung |
| --- | --- |
| `--input` | Eine oder mehrere PDF-Dateien oder Ordner. |
| `--output` | Optionaler CSV-Zielpfad oder Zielordner. Setzt `--input` voraus. |
| `--chart` | Öffnet nach der Verarbeitung die Diagramm-Ansicht. Setzt `--input` voraus. |

Wenn `--input` gesetzt ist und `--output` fehlt, wird automatisch im aktuellen Ordner eine CSV-Datei mit eindeutigem Zeitstempel erstellt.

## Projektstruktur

```text
.
├── requirements.txt                # Python-Abhängigkeiten
├── testPDF/                        # Test-PDFs (Beispiele je Broker)
└── src/
    ├── __init__.py                 # Src-Package-Init
    │
    ├── apps/                       # App-Schicht (GUI/CLI/Viewer-Wrapper)
    │   ├── __init__.py
    │   ├── cli_app.py              # CLI-Implementierung
    │   ├── pdf_selector.py         # Wrapper -> gui.py (PDF-Auswahl)
    │   ├── viewer.py               # Wrapper -> gui_viewer.py (Viewer)
    │   └── viewer/                 # Viewer-Unterpaket (aufgeteilt)
    │       ├── __init__.py
    │       ├── charts/
    │       │   └── chart_mixin.py  # Pie-/Line-Chart-Logik (Mixin)
    │       └── filters/
    │           └── filter_mixin.py # Filterpanel + Filterlogik (Mixin)
    │
    ├── gui.py                      # PDF-Auswahl-GUI (Tkinter)
    ├── gui_viewer.py               # Viewer-GUI (Tkinter; nutzt Mixins)
    │
    ├── core/                       # Core: PDF/Text/Parsing
    │   ├── __init__.py
    │   ├── file_selector.py        # Dateisystem-Traversal, PDF-Erkennung
    │   ├── pdf_extractor.py        # PDF-Text-Extraktion (pypdf-Wrapper)
    │   └── financial_parser.py     # Regelbasierter Parser (inkl. Buchungswerte)
    │
    ├── services/                   # Service: Workflows/Pipelines
    │   ├── __init__.py
    │   └── pdf_processing.py       # Pipeline: collect_pdf_paths, extract_* etc.
    │
    ├── export/                     # Export-Implementierung
    │   ├── __init__.py
    │   └── csv_writer.py           # CSV-Schreiber
    │
    ├── analysis/                   # Analyse-/Aggregationslogik
    │   ├── __init__.py
    │   └── portfolio.py
    │
    ├── common/                     # Gemeinsame Hilfsfunktionen
    │   ├── __init__.py
    │   └── formatting.py
    │
    ├── ui/                         # Wiederverwendbare UI-Bausteine
    │   ├── __init__.py
    │   └── widgets.py              # Tooltip/Dropdown/Mousewheel
    │
    ├── cli.py                      # Kompatibilitäts-Wrapper -> apps/cli_app.py
    ├── csv_export.py               # Kompatibilitäts-Wrapper -> export/csv_writer.py
    ├── portfolio_analysis.py       # Kompatibilitäts-Wrapper -> analysis/portfolio.py
    ├── utils.py                    # Kompatibilitäts-Wrapper -> common/formatting.py
    └── transaction_service.py      # Kompatibilitäts-Wrapper -> services/pdf_processing.py
```

## Architektur

Das Projekt folgt einer **Schichtenarchitektur mit klarer Verantwortungsteilung**:

### Schichten-Übersicht

```
┌─────────────────────────────────────────────┐
│     GUI / CLI / Externe Aufrufer            │
│   (main.py, gui.py, cli.py)                 │
├─────────────────────────────────────────────┤
│         Services (Workflows)                │
│     (src/services/pdf_processing.py)        │
│                                             │
│  - collect_pdf_paths()                      │
│  - extract_transactions_from_pdfs()         │
│  - extract_pdf_results()                    │
├─────────────────────────────────────────────┤
│     Core (Datenverarbeitung)                │
│                                             │
│  - FileSelector (Datei-Sammlung)            │
│  - PDFExtractor (Text-Extraktion)           │
│  - FinancialParser (Regex-Parsing)          │
├─────────────────────────────────────────────┤
│     Utilities & Libraries                   │
│   (pypdf, tkinter, csv, pathlib, etc.)      │
└─────────────────────────────────────────────┘
```

### Verarbeitungspipeline

`main.py` entscheidet, ob die GUI oder die CLI gestartet wird. Alle anderen Module sind bewusst nicht direkt ausführbar und stellen nur wiederverwendbare Klassen oder Funktionen bereit.

Der fachliche Ablauf ist:

1. **FileSelector** (`core/file_selector.py`) → Dateisystem-Traversal, PDF-Sammlung
2. **PDFExtractor** (`core/pdf_extractor.py`) → Text-Extraktion mit `pypdf`
3. **FinancialParser** (`core/financial_parser.py`) → Regex-Mustererkennung für Transaktionen
4. **csv_export** (`csv_export.py`) → Normalisierung und CSV-Schreiber
5. **DataViewerApp** (`gui_viewer.py`) → Visualisierung und Filterung
6. **Services** (`services/pdf_processing.py`) → Komfortable High-Level-API

### Modulbeschreibungen

#### Core-Module

| Modul | Klasse | Verantwortung |
| --- | --- | --- |
| `file_selector.py` | `FileSelector` | Dateisystem-Navigation, PDF-Sammlung aus Dateien/Ordnern |
| `pdf_extractor.py` | `PDFExtractor` | Text-Extraktion aus PDFs mit Fehlerbehandlung |
| `financial_parser.py` | `FinancialParser` | Regex-Parsing für Broker, Datum, Transaktionen, Gebühren |

#### Services-Module

| Modul | Funktion | Verantwortung |
| --- | --- | --- |
| `pdf_processing.py` | `collect_pdf_paths()` | Sammelt eindeutige PDF-Pfade aus Eingaben |
| | `extract_pdf_result()` | Extrahiert eine PDF mit Fehlerbehandlung |
| | `extract_pdf_results()` | Batch-Extraktion mehrerer PDFs |
| | `flatten_successful_transactions()` | Flatten erfolgreicher Transaktionen |
| | `extract_transactions_from_pdfs()` | High-Level-API für Transaktions-Extraktion |

#### UI/Export-Module

| Modul | Klasse | Verantwortung |
| --- | --- | --- |
| `cli.py` | `CLIApp` | Kommandozeilen-Interface mit Ausgabe-Formatierung |
| `gui.py` | `DateiAuswahlApp` | GUI-Fenster für PDF-Auswahl (Tkinter) |
| `gui_viewer.py` | `DataViewerApp` | Datenviewer mit Tabellen, Diagrammen, Filterung |
| `csv_export.py` | `write_transactions_csv()` | CSV-Export, Normalisierung, Kollisionserkennung |
| `utils.py` | Hilfsfunktionen | Pfad-Handling, String-Bereinigung |

## CSV-Export

Der Export verwendet ein Semikolon als Trennzeichen und bereinigt Zeilenumbrüche sowie Semikolons innerhalb von Textfeldern. Dadurch bleibt die Datei in Excel stabil lesbar.

Wenn eine Datei bereits existiert, überschreibt das Programm sie nicht. Stattdessen wird automatisch ein freier Name erzeugt:

```text
portfolio.csv
portfolio (1).csv
portfolio (2).csv
```

Bei CLI-Verarbeitung wird ein eindeutiger Zeitstempel verwendet:

```text
Portfolio-CSV-20260505-143022.csv
```

## Projektdokumentation

Eine detaillierte Projektdokumentation (2 Seiten, PDF-Format) kann mit folgendem Befehl generiert werden:

```powershell
pip install reportlab
py generate_documentation.py
```

Die Dokumentation enthält:
- Problemstellung und Zielsetzung (SMART-Methode)
- Ist-Analyse und Architektur-Übersicht
- Verarbeitungspipeline und Modulbeschreibungen
- Kritische Bewertung und Ausblick

Die PDF-Datei wird unter `docs/2026-05-05_Dokumentation_SniftedIncluded.pdf` erstellt.

## Entwicklung

### Syntaxprüfung

```powershell
py -m py_compile main.py `
  src\cli.py `
  src\csv_export.py `
  src\gui.py `
  src\gui_viewer.py `
  src\utils.py `
  src\core\__init__.py `
  src\core\file_selector.py `
  src\core\financial_parser.py `
  src\core\pdf_extractor.py `
  src\services\__init__.py `
  src\services\pdf_processing.py
```

### CLI-Test mit Beispielordner

```powershell
py main.py --input PDFs --output output\test-export.csv
```

### GUI-Test

```powershell
py main.py
```

### Mit Chart-Viewer

```powershell
py main.py --input PDFs --chart
```

### Service-API direkt verwenden

```python
from src.services.pdf_processing import extract_transactions_from_pdfs

# Einfacher API-Aufruf für Transaktions-Extraktion
transactions = extract_transactions_from_pdfs(['path/to/pdf1.pdf', 'path/to/folder'])

for transaction in transactions:
    print(f"Broker: {transaction['broker']}, Betrag: {transaction['betrag']}")
```

## Sprachzusammensetzung

- **Python**: 98,1 % (Kern-Implementierung)
- **Batch**: 1,9 % (Windows-Automation, optional)

## Hinweise

- Das Projekt ist auf Broker-PDFs mit textbasierter PDF-Struktur ausgelegt.
- Eingescannte PDFs ohne eingebetteten Text benötigen OCR und werden aktuell nicht unterstützt.
- Der Parser ist regelbasiert. Neue Broker-Layouts können durch zusätzliche Muster in `src/core/financial_parser.py` ergänzt werden.
- Die Anwendung ist plattformübergreifend kompatibel (Python 3.10+), nutzt aber Windows-Batch-Skripte für optionale Automation.

## Lizenz

Derzeit ohne Lizenz. Zukünftige Versionen werden eine Lizenz definieren.

## Kontakt

Erstellt von [Nico](https://github.com/Nicostar3000), [Tommy](https://github.com/kacklinux), [Mats](https://github.com/Snifted)
