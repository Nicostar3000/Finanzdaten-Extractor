"""
Gemeinsame Auswertungslogik fuer Portfolio-Tabellen und Diagramme.
"""

from datetime import datetime
from pathlib import Path

from .utils import choose_canonical_position_name, clean_csv


def get_broker_filtered_transactions(transactions, selected_broker):
    """Filtert Transaktionen nur nach Broker."""
    if not selected_broker or selected_broker == "Alle Broker":
        return list(transactions)

    if isinstance(selected_broker, (set, list, tuple)):
        selected = set(selected_broker)
        if not selected:
            return []
        return [
            transaction for transaction in transactions
            if transaction.get('broker', 'Unbekannt') in selected
        ]

    return [
        transaction for transaction in transactions
        if transaction.get('broker', 'Unbekannt') == selected_broker
    ]


def filter_transactions(
    transactions,
    selected_broker=None,
    selected_position=None,
    bucket_positions=None,
    selected_positions=None,
    selected_depots=None,
    date_start=None,
    date_end=None,
    amount_min=None,
    amount_max=None,
    quantity_min=None,
    quantity_max=None,
    top_x=None,
):
    """Kombiniert alle aktiven Filter fuer Tabellen, Diagramme und Export."""
    broker_transactions = get_broker_filtered_transactions(transactions, selected_broker)
    filtered = []
    for transaction in broker_transactions:
        if selected_depots is not None and transaction.get('depot', 'Nil') not in selected_depots:
            continue

        date_obj = _parse_german_date(transaction.get('date', 'Nil'))
        if date_start is not None and (date_obj is None or date_obj < date_start):
            continue
        if date_end is not None and (date_obj is None or date_obj > date_end):
            continue

        filtered.append(transaction)

    aliases = choose_canonical_position_name(
        transaction.get('position') for transaction in filtered
    )

    allowed_positions = None
    if selected_position:
        allowed_positions = {selected_position}
    elif bucket_positions:
        allowed_positions = set(bucket_positions)
    elif selected_positions is not None:
        allowed_positions = set(selected_positions)

    aggregate_filters_active = any(
        value is not None for value in [amount_min, amount_max, quantity_min, quantity_max, top_x]
    )
    if aggregate_filters_active:
        position_data = {}
        for transaction in filtered:
            if not is_purchase_transaction(transaction):
                continue
            position = _canonical_position(transaction, aliases)
            entry = position_data.setdefault(position, {'amount': 0.0, 'anzahl': 0.0})
            entry['amount'] += transaction.get('amount') or 0.0
            entry['anzahl'] += transaction.get('anzahl') or 0.0

        aggregate_positions = set()
        for position, data in position_data.items():
            if amount_min is not None and data['amount'] < amount_min:
                continue
            if amount_max is not None and data['amount'] > amount_max:
                continue
            if quantity_min is not None and data['anzahl'] < quantity_min:
                continue
            if quantity_max is not None and data['anzahl'] > quantity_max:
                continue
            aggregate_positions.add(position)

        if top_x is not None:
            top_positions = [
                position for position, _data in sorted(
                    position_data.items(),
                    key=lambda item: item[1]['amount'],
                    reverse=True,
                )[:top_x]
            ]
            aggregate_positions = aggregate_positions.intersection(top_positions) if aggregate_positions else set(top_positions)

        allowed_positions = aggregate_positions if allowed_positions is None else allowed_positions.intersection(aggregate_positions)

    if allowed_positions is None:
        return filtered

    return [
        transaction for transaction in filtered
        if _canonical_position(transaction, aliases) in allowed_positions
    ]


def summarize_transactions(transactions):
    """Berechnet die Kopfkennzahlen fuer die Zusammenfassung."""
    total = len(transactions)
    purchases = sum(t.get('amount', 0) or 0 for t in transactions if is_purchase_transaction(t))
    fees = sum(t.get('amount', 0) or 0 for t in transactions if is_fee_transaction(t))
    return {
        'total': total,
        'purchases': purchases,
        'fees': fees,
        'net': purchases - fees,
    }


def group_transactions_by_file(transactions):
    """Zaehlt Transaktionen und Summen je Quelldatei."""
    file_data = {}
    for transaction in transactions:
        source = transaction.get('source_file', 'Unbekannt')
        entry = file_data.setdefault(source, {'count': 0, 'amount': 0})
        entry['count'] += 1
        entry['amount'] += transaction.get('amount') or 0
    return file_data


def combine_positions(transactions):
    """Verdichtet Transaktionen zu Positionssummen fuer die Tabelle."""
    aliases = choose_canonical_position_name(
        transaction.get('position') for transaction in transactions
    )
    combined_data = {}
    for transaction in transactions:
        position = _canonical_position(transaction, aliases)
        amount = transaction.get('amount') or 0
        quantity = transaction.get('anzahl') or 0
        entry = combined_data.setdefault(position, {'amount': 0, 'anzahl': 0})
        entry['amount'] += amount
        entry['anzahl'] += quantity
    return combined_data


def calculate_file_validation_sums(transactions):
    """Berechnet Ist-/Sollwerte je Quelldatei fuer die Validierungstabelle."""
    file_sums = {}
    for transaction in transactions:
        source = transaction.get('source_file', 'Unbekannt')
        entry = file_sums.setdefault(source, {'ist': 0.0, 'soll': transaction.get('target_sum')})
        entry['ist'] += transaction.get('amount') or 0.0
    return file_sums


def build_position_chart_data(transactions):
    """Verdichtet Kauf-/Gutschrifttransaktionen zu Positionssummen fuer das Kreisdiagramm."""
    aliases = choose_canonical_position_name(
        transaction.get('position') for transaction in transactions
    )
    position_data = {}

    for transaction in transactions:
        if not is_purchase_transaction(transaction):
            continue

        position = _canonical_position(transaction, aliases)
        if position == "Nil":
            continue

        entry = position_data.setdefault(position, {
            'amount': 0.0,
            'anzahl': 0.0,
            'kurs_gewicht': 0.0,
            'kurs_basis': 0.0,
            'kurs_fallback': None,
        })

        amount = float(transaction.get('amount') or 0.0)
        quantity = float(transaction.get('anzahl') or 0.0)
        kurs = transaction.get('kurs')

        entry['amount'] += amount
        entry['anzahl'] += quantity

        if kurs is not None:
            entry['kurs_fallback'] = kurs
            if quantity > 0:
                entry['kurs_gewicht'] += float(kurs) * quantity
                entry['kurs_basis'] += quantity

    return dict(
        sorted(
            position_data.items(),
            key=lambda item: item[1]['amount'],
            reverse=True,
        )
    )


def build_pie_bucket_data(position_data, segment_size=10):
    """Fasst sortierte Positionen in Rangbereiche zusammen.

    segment_size 0: eine Kuchenscheibe pro Position (keine Prozent-Buckets).
    segment_size > 0: Gruppierung entsprechend der gewaehlten Segmentgroesse.
    """
    positions = list(position_data.items())
    if not positions:
        return []

    if int(segment_size or 0) == 0:
        buckets = []
        for bucket_index, (position, entry) in enumerate(positions):
            buckets.append({
                'index': bucket_index,
                'label': position,
                'amount': entry['amount'],
                'positions': [position],
                'count': 1,
            })
        return buckets

    segment_size = max(1, int(segment_size or 10))
    segment_count = max(1, (100 + segment_size - 1) // segment_size)
    bucket_size = max(1, (len(positions) + segment_count - 1) // segment_count)
    buckets = []
    for bucket_index, start in enumerate(range(0, len(positions), bucket_size)):
        chunk = positions[start:start + bucket_size]
        range_start = bucket_index * segment_size
        range_end = min(range_start + segment_size, 100)
        label = f"Top {segment_size}%" if bucket_index == 0 else f"{range_start}-{range_end}%"

        buckets.append({
            'index': bucket_index,
            'label': label,
            'amount': sum(entry['amount'] for _, entry in chunk),
            'positions': [position for position, _ in chunk],
            'count': len(chunk),
        })

    return buckets


def get_bucket_positions(bucket_data, bucket_index):
    """Liefert Positionsnamen eines Pie-Bereichs."""
    for bucket in bucket_data:
        if bucket['index'] == bucket_index:
            return bucket['positions']
    return []


def build_line_chart_data(transactions):
    """Aggregiert Portfolio-Werte je Broker und Datum fuer den Zeitverlauf."""
    broker_data, all_dates = {}, []
    for transaction in transactions:
        if not is_purchase_transaction(transaction):
            continue
        date_obj = _parse_german_date(transaction.get('date', 'Nil'))
        if date_obj is None:
            continue

        broker_name = transaction.get('broker', 'Unbekannt')
        broker_data.setdefault(broker_name, {})
        broker_data[broker_name][date_obj] = broker_data[broker_name].get(date_obj, 0) + (transaction.get('amount') or 0)
        all_dates.append(date_obj)

    return broker_data, all_dates


def build_broker_info_data(transactions):
    """Verdichtet Transaktionen zu Brokerkennzahlen fuer die Informationsansicht."""
    broker_data = {}
    aliases = choose_canonical_position_name(
        transaction.get('position') for transaction in transactions
    )

    for transaction in transactions:
        broker_name = transaction.get('broker', 'Unbekannt')
        entry = broker_data.setdefault(broker_name, {
            'broker': broker_name,
            'transactions': 0,
            'positions': set(),
            'depots': set(),
            'company_address': '',
            'company_phone': '',
            'company_fax': '',
            'company_email': '',
            'company_website': '',
            'purchases': 0.0,
            'fees': 0.0,
            'net': 0.0,
        })

        amount = transaction.get('amount') or 0.0
        entry['transactions'] += 1

        depot = clean_csv(transaction.get('depot', ''))
        if depot and depot != 'Nil':
            entry['depots'].add(depot)

        for target_key, source_key in [
            ('company_address', 'company_address'),
            ('company_phone', 'company_phone'),
            ('company_fax', 'company_fax'),
            ('company_email', 'company_email'),
            ('company_website', 'company_website'),
        ]:
            value = clean_csv(transaction.get(source_key, ''))
            if value and value != 'Nil' and not entry[target_key]:
                entry[target_key] = value

        if is_purchase_transaction(transaction):
            entry['purchases'] += amount
            position = _canonical_position(transaction, aliases)
            if position and position != 'Nil':
                entry['positions'].add(position)
        elif is_fee_transaction(transaction):
            entry['fees'] += amount

        entry['net'] = entry['purchases'] - entry['fees']

    total_purchases = sum(entry['purchases'] for entry in broker_data.values()) or 0.0
    summaries = []
    for entry in broker_data.values():
        purchase_share = (entry['purchases'] / total_purchases * 100) if total_purchases else 0.0
        summaries.append({
            **entry,
            'position_count': len(entry['positions']),
            'depot_count': len(entry['depots']),
            'purchase_share': purchase_share,
        })

    return sorted(summaries, key=lambda item: item['purchases'], reverse=True)


def build_extracted_data(pdf_paths, results):
    """Erzeugt das gemeinsame Ergebnisobjekt fuer Viewer und Auswahl-GUI."""
    return {
        'files': list(pdf_paths),
        'results': list(results),
    }


def attach_source_file(transactions, source_file):
    """Traegt eine Quelldatei in Transaktionen ein."""
    source_name = Path(source_file).name
    for transaction in transactions:
        transaction['source_file'] = source_name
    return transactions


def is_purchase_transaction(transaction):
    """Erkennt Wertpapierkaeufe ueber die fachlichen Zahlenfelder."""
    return transaction.get('anzahl') is not None and transaction.get('kurs') is not None


def is_fee_transaction(transaction):
    """Erkennt Gebuehren ueber fachliche Merkmale der Transaktion."""
    if is_purchase_transaction(transaction):
        return False

    position = str(transaction.get('position', '')).lower()
    fee_keywords = ('fremdkostenzuschlag', 'provision', 'spesen', 'kosten', 'makler', 'gebuehr', 'gebühr')
    return any(keyword in position for keyword in fee_keywords)


def _canonical_position(transaction, aliases):
    raw_position = clean_csv(transaction.get('position', 'Unbekannt'))
    return aliases.get(raw_position, raw_position)


def _parse_german_date(date_text):
    try:
        return datetime.strptime(date_text, '%d.%m.%Y') if date_text != "Nil" else None
    except ValueError:
        return None
