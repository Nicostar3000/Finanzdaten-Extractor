"""
CLI-Modul fuer den PDF-Finanzdaten-Extraktor.

Dieses Modul enthaelt nur die wiederverwendbare CLI-Anwendungslogik. Der
ausfuehrbare Einstiegspunkt liegt ausschliesslich in main.py.
"""

import logging

from ..export.csv_writer import resolve_csv_path, write_transactions_csv
from ..services.pdf_processing import collect_pdf_paths, extract_transactions_from_pdfs
from ..common.formatting import format_currency, format_quantity
from ..gui_viewer import load_and_view

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CLIApp:
    """
    Hauptklasse fuer die Kommandozeilen-Anwendung.

    Diese Klasse verwaltet die Verarbeitung von PDF-Dateien ueber die CLI.
    """

    def __init__(self):
        pass

    def ausfuehren(self, args):
        """
        Fuehrt die Hauptlogik der CLI-Anwendung aus.

        Args:
            args: Die geparsten Kommandozeilen-Argumente aus main.py.

        Returns:
            Exit-Code (0 fuer Erfolg, 1 fuer Fehler).
        """
        pdf_dateien = self._sammle_pdf_dateien(args)
        if not pdf_dateien:
            print("Fehler: Keine PDF-Dateien gefunden.")
            return 1

        alle_transaktionen = self._extrahiere_transaktionen(pdf_dateien)
        if not alle_transaktionen:
            print("Fehler: Es konnten keine Transaktionen extrahiert werden.")
            return 1

        self._drucke_transaktionen(alle_transaktionen)
        ausgabe_pfad = resolve_csv_path(args.output)
        self._speichere_in_csv(alle_transaktionen, ausgabe_pfad)

        if args.chart:
            print(f"\nOeffne Diagramm-Ansicht mit {len(pdf_dateien)} geladenen Datei(en)...")
            load_and_view(pdf_dateien)

        return 0

    def _sammle_pdf_dateien(self, args):
        """Sammelt PDF-Dateien aus --input. Eingaben duerfen Dateien oder Ordner sein."""
        return collect_pdf_paths(args.input)

    def _extrahiere_transaktionen(self, pdf_dateien):
        """Extrahiert Text aus allen PDFs und parst daraus Transaktionsobjekte."""
        print(f"\nVerarbeite {len(pdf_dateien)} PDF-Datei(en)...\n")
        return extract_transactions_from_pdfs(pdf_dateien)

    def _drucke_transaktionen(self, transaktionen):
        """Gibt eine kompakte Vorschau der gefundenen Transaktionen aus."""
        print(f"{'Broker':<15} | {'Position':<25} | {'Kurs':<8} | {'Anz.':<6} | {'Betrag':<10}")
        print("-" * 80)

        for transaktion in transaktionen:
            broker_str = str(transaktion.get("broker", ""))[:14]
            position = str(transaktion.get("position", ""))[:24]
            kurs = format_currency(transaktion.get("kurs")).replace(" EUR", "").replace(" €", "")
            anzahl_wert = transaktion.get("anzahl")
            anzahl = format_quantity(anzahl_wert) if anzahl_wert else ""
            betrag = format_currency(transaktion.get("amount", 0))
            print(f"{broker_str:<15} | {position:<25} | {kurs:<8} | {anzahl:<6} | {betrag:<10}")

    def _speichere_in_csv(self, transaktionen, ausgabe_pfad):
        """Speichert die Transaktionen in einer CSV-Datei."""
        try:
            ausgabe_datei = write_transactions_csv(transaktionen, ausgabe_pfad)
            print(f"\nDaten erfolgreich gespeichert unter: {ausgabe_datei}")
        except Exception as exc:
            print(f"\nFehler beim Speichern der CSV-Datei: {exc}")

