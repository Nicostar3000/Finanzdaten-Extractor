"""App-Modul fuer die PDF-Auswahl-GUI.

Aktuell ist dies ein Wrapper um die bestehende Implementierung in `src/gui.py`,
damit die Ordnerstruktur konsistent ist, ohne Verhalten zu aendern.
"""

from ..gui import DateiAuswahlApp, extract_financial_data, get_pdf_paths  # noqa: F401

__all__ = ["DateiAuswahlApp", "get_pdf_paths", "extract_financial_data"]

