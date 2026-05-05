import argparse
import sys
from pathlib import Path


# main.py ist bewusst der einzige direkte Einstiegspunkt der Anwendung.
# Alle anderen Module liefern nur wiederverwendbare Klassen und Funktionen.
src_dir = Path(__file__).parent / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir))


def parse_args():
    """Definiert die oeffentliche Kommandozeilenoberflaeche des Programms."""
    parser = argparse.ArgumentParser(description="PDF Finanzdaten Extraktor")
    parser.add_argument(
        "--input",
        nargs="+",
        help="Eine oder mehrere PDF-Dateien oder Ordner mit PDF-Dateien",
    )
    parser.add_argument("--output", help="CSV-Ausgabedatei oder Ausgabeordner")
    parser.add_argument(
        "--chart",
        action="store_true",
        help="Oeffnet nach der Verarbeitung die Diagramm-Ansicht",
    )
    args = parser.parse_args()

    # Export und Chart brauchen konkrete Eingabedaten. Ohne Parameter startet
    # main() stattdessen die GUI und laesst die Auswahl interaktiv treffen.
    if (args.output or args.chart) and not args.input:
        parser.error("--output und --chart setzen --input voraus")

    return args


def open_gui():
    """Startet die einfache PDF-Auswahl-GUI."""
    from src.apps.pdf_selector import DateiAuswahlApp
    import tkinter as tk

    root = tk.Tk()
    DateiAuswahlApp(root)
    root.mainloop()


def main():
    """Waehlt zwischen GUI-Modus und CLI-Verarbeitung."""
    args = parse_args()
    if not any([args.input, args.output, args.chart]):
        open_gui()
        return

    from src.apps.cli_app import CLIApp

    cli = CLIApp()
    sys.exit(cli.ausfuehren(args))


if __name__ == "__main__":
    main()
