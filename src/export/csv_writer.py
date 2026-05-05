"""
Gemeinsame CSV-Exportlogik fuer CLI und GUI.
"""

from datetime import datetime
from pathlib import Path

from ..analysis.portfolio import is_fee_transaction, is_purchase_transaction
from ..common.formatting import clean_csv, choose_canonical_position_name


def get_unique_file_path(file_path):
    """Haengt bei vorhandenen Dateien automatisch (1), (2), ... an."""
    candidate = Path(file_path)
    counter = 1

    while candidate.exists():
        candidate = candidate.with_name(f"{candidate.stem} ({counter}){candidate.suffix}")
        counter += 1

    return candidate


def get_default_csv_path(base_dir=None):
    """Erzeugt einen eindeutigen Standardnamen im Format Portfolio-CSV-Zeitstring.csv."""
    target_dir = Path(base_dir) if base_dir else Path.cwd()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return get_unique_file_path(target_dir / f"Portfolio-CSV-{timestamp}.csv")


def resolve_csv_path(output_path=None):
    """Loest Datei- oder Ordnerangaben zu einem freien CSV-Dateipfad auf."""
    if not output_path:
        return get_default_csv_path()

    path = Path(output_path)
    if path.exists() and path.is_dir():
        return get_default_csv_path(path)

    if not path.suffix:
        path = path.with_suffix(".csv")

    return get_unique_file_path(path)


def write_transactions_csv(transactions, output_path):
    """Schreibt Transaktionen in das einheitliche Semikolon-CSV-Format."""
    output_file = resolve_csv_path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    positions_aliase = choose_canonical_position_name(
        transaction.get("position") for transaction in transactions
    )

    headers = [
        "Firmenname",
        "Firmenanschrift",
        "Telefonnummer",
        "Fax",
        "E-Mail-Adresse",
        "Internetseite",
        "Kundenname",
        "Kundenanschrift",
        "Depotnummer",
        "Kaufbeleg-Datum",
        "Transaktionsdatum",
        "Uhrzeit",
        "Handelsplatz",
        "Position (Wertpapier)",
        "Anzahl",
        "Kurs",
        "Endbetrag",
        "Fremdkostenzuschlag",
        "Verrechnungskonto",
        "Valuta-Datum",
        "Gesamtsumme (Soll)",
        "Zusatzinformationen / Fehler",
        "Quelldatei",
    ]

    with open(output_file, "w", encoding="utf-8") as file:
        file.write(";".join(headers) + "\n")

        for transaction in transactions:
            raw_position = clean_csv(transaction.get("position"))
            position = positions_aliase.get(raw_position, raw_position)
            amount = _format_csv_number(transaction.get("amount"))
            target_sum_value = transaction.get("target_sum")
            warning = _build_warning(transaction, target_sum_value)
            is_purchase = is_purchase_transaction(transaction)
            is_fee = is_fee_transaction(transaction)

            row = [
                clean_csv(transaction.get("broker")),
                clean_csv(transaction.get("company_address")),
                clean_csv(transaction.get("company_phone")),
                clean_csv(transaction.get("company_fax")),
                clean_csv(transaction.get("company_email")),
                clean_csv(transaction.get("company_website")),
                clean_csv(transaction.get("customer_name")),
                clean_csv(transaction.get("customer_address")),
                clean_csv(transaction.get("depot")),
                clean_csv(transaction.get("date")),
                clean_csv(transaction.get("date")),
                clean_csv(transaction.get("uhrzeit")),
                clean_csv(transaction.get("handelsplatz")),
                position,
                _format_csv_number(transaction.get("anzahl")),
                _format_csv_number(transaction.get("kurs")),
                amount if is_purchase else "Nil",
                amount if is_fee else "Nil",
                clean_csv(transaction.get("verrechnungskonto")),
                clean_csv(transaction.get("valuta_datum")),
                _format_csv_number(target_sum_value),
                warning,
                clean_csv(Path(transaction.get("source_file", "")).name),
            ]

            file.write(";".join(row) + "\n")

    return output_file


def _format_csv_number(value):
    if value is None:
        return "Nil"
    return str(value).replace(".", ",")


def _build_warning(transaction, target_sum_value):
    if target_sum_value is None or not is_purchase_transaction(transaction):
        return "Nil"

    difference = abs((transaction.get("amount") or 0) - target_sum_value)
    if difference >= 0.02:
        return "ABWEICHUNG: Berechneter Wert weicht von PDF ab!"

    return "Nil"

