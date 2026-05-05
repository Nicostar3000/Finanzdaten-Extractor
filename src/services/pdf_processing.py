"""Workflows fuer PDF-Auswahl und Transaktionsextraktion.

Enthaelt die Pipeline, die von GUI, Viewer und CLI genutzt wird.
"""

from pathlib import Path
import logging

from ..core import PDFExtractor, FinancialParser, FileSelector

logger = logging.getLogger(__name__)


def collect_pdf_paths(inputs, file_selector=None):
    """Sammelt eindeutige PDF-Dateien aus Datei- und Ordnerpfaden."""
    selector = file_selector or FileSelector()
    pdf_paths = []

    for input_path in inputs or []:
        path = Path(str(input_path).strip("\"'"))
        if path.exists() and path.is_file() and path.suffix.lower() == ".pdf":
            pdf_paths.append(str(path))
        elif path.exists() and path.is_dir():
            pdf_paths.extend(selector.hole_dateien_aus_verzeichnis(str(path)))

    return list(dict.fromkeys(pdf_paths))


def extract_pdf_result(pdf_path, pdf_extractor=None, financial_parser=None, source_as_name=True):
    """Extrahiert eine einzelne PDF und liefert ein Ergebnisobjekt fuer GUI/CLI."""
    extractor = pdf_extractor or PDFExtractor()
    parser = financial_parser or FinancialParser()
    source_file = Path(pdf_path).name if source_as_name else str(pdf_path)

    try:
        text = extractor.extrahiere_text(pdf_path)
        if not text:
            return {"success": False, "file": pdf_path, "error": "No text extracted", "transactions": []}

        transactions = parser.parse_text(text)
        for transaction in transactions:
            transaction["source_file"] = source_file

        return {"success": True, "file": pdf_path, "transactions": transactions}
    except Exception as exc:
        logger.error(f"Error extracting data from {pdf_path}: {exc}")
        return {"success": False, "file": pdf_path, "error": str(exc), "transactions": []}


def extract_pdf_results(pdf_paths, source_as_name=True):
    """Extrahiert mehrere PDFs mit wiederverwendeten Parser-/Extraktor-Instanzen."""
    extractor = PDFExtractor()
    parser = FinancialParser()
    return [
        extract_pdf_result(
            pdf_path,
            pdf_extractor=extractor,
            financial_parser=parser,
            source_as_name=source_as_name,
        )
        for pdf_path in pdf_paths
    ]


def flatten_successful_transactions(results):
    """Fuehrt alle erfolgreichen Transaktionen aus Ergebnisobjekten zusammen."""
    transactions = []
    for result in results:
        if result.get("success"):
            transactions.extend(result.get("transactions", []))
    return transactions


def extract_transactions_from_pdfs(pdf_paths, source_as_name=True):
    """Komfortfunktion fuer Aufrufer, die nur die Transaktionsliste brauchen."""
    return flatten_successful_transactions(
        extract_pdf_results(pdf_paths, source_as_name=source_as_name)
    )

