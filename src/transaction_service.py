"""Kompatibilitaetsmodul fuer die PDF-Verarbeitungs-Pipeline.

Die eigentliche Implementierung liegt in `src/services/pdf_processing.py`.
Dieses Modul bleibt als Import-Ziel bestehen, damit bestehende Imports nicht brechen.
"""

from .services.pdf_processing import (  # noqa: F401
    collect_pdf_paths,
    extract_pdf_result,
    extract_pdf_results,
    extract_transactions_from_pdfs,
    flatten_successful_transactions,
)

__all__ = [
    "collect_pdf_paths",
    "extract_pdf_result",
    "extract_pdf_results",
    "flatten_successful_transactions",
    "extract_transactions_from_pdfs",
]
