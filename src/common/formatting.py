"""
Hilfsmodul für gemeinsame Funktionen.

Dieses Modul enthält Hilfsfunktionen, die von verschiedenen Teilen der Anwendung verwendet werden.
"""

import re
from typing import Any, Dict, Iterable, List, Optional

LEGAL_ENTITY_TOKENS = {
    "inc", "incorporated", "corp", "corporation", "company", "co",
    "ltd", "limited", "plc", "ag", "gmbh", "holding", "holdings",
    "group", "sa", "se", "nv", "spa", "srl", "llc"
}

GENERIC_TRAILING_TOKENS = {
    "com", "the", "class", "ordinary", "shares", "share", "stock"
}


def clean_csv(text: Optional[str]) -> str:
    """
    Bereinigt Text für CSV-Export.

    Entfernt Zeilenumbrüche, ersetzt Semikolons durch Kommas und entfernt überflüssige Leerzeichen.

    Args:
        text: Der zu bereinigende Text.

    Returns:
        Der bereinigte Text oder "Nil" wenn leer.
    """
    if text is None:
        return "Nil"
    text_str = str(text)
    if not text_str.strip() or text_str.strip() == "None":
        return "Nil"
    return re.sub(r"\s+", " ", text_str).replace(";", ",").strip()


def natural_sort_key(value: Any) -> List[Any]:
    """Sortierschluessel fuer gemischte Text-/Zahlenwerte wie Datei 2, Datei 10."""
    text = str(value)
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def format_quantity(quantity: Optional[float]) -> str:
    """Formatiert Stueckzahlen im deutschen Zahlenformat."""
    if quantity is None:
        return ""
    if float(quantity).is_integer():
        return str(int(quantity))
    return f"{quantity}".replace(".", ",")


def _extract_ticker_hint(text: str) -> Optional[str]:
    matches = re.findall(r"\(([A-Z0-9.\-]{1,10})\)", text)
    for candidate in matches:
        if re.fullmatch(r"[A-Z0-9.\-]{1,10}", candidate):
            return candidate
    return None


def _tokenize_position_name(text: str) -> List[str]:
    lowered = re.sub(r"\([^)]*\)", " ", text.lower())
    lowered = lowered.replace("&", " and ")
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return [token for token in lowered.split() if token]


def _core_position_tokens(text: str) -> List[str]:
    tokens = _tokenize_position_name(text)
    trimmed = [token for token in tokens if token not in LEGAL_ENTITY_TOKENS]

    while trimmed and trimmed[-1] in GENERIC_TRAILING_TOKENS:
        trimmed.pop()

    return trimmed or tokens


def _positions_can_be_merged(name_a: str, name_b: str) -> bool:
    cleaned_a = clean_csv(name_a)
    cleaned_b = clean_csv(name_b)

    if cleaned_a == "Nil" or cleaned_b == "Nil":
        return False

    if cleaned_a.casefold() == cleaned_b.casefold():
        return True

    ticker_a = _extract_ticker_hint(cleaned_a)
    ticker_b = _extract_ticker_hint(cleaned_b)
    if ticker_a and ticker_b and ticker_a == ticker_b:
        return True

    tokens_a = _core_position_tokens(cleaned_a)
    tokens_b = _core_position_tokens(cleaned_b)
    if not tokens_a or not tokens_b:
        return False

    if tokens_a == tokens_b:
        return True

    short_tokens, long_tokens = (
        (tokens_a, tokens_b) if len(tokens_a) <= len(tokens_b) else (tokens_b, tokens_a)
    )

    if len(short_tokens) >= 2 and long_tokens[: len(short_tokens)] == short_tokens:
        return True

    if len(short_tokens) == 1 and long_tokens[0] == short_tokens[0]:
        extras = long_tokens[1:]
        if extras and all(
            token in GENERIC_TRAILING_TOKENS or token in LEGAL_ENTITY_TOKENS for token in extras
        ):
            return True

    return False


def choose_canonical_position_name(position_names: Iterable[Optional[str]]) -> Dict[str, str]:
    """
    Build a mapping from observed position names to a shared display name when
    they likely refer to the same company.
    """
    groups: List[List[str]] = []
    cleaned_names: List[str] = []

    for raw_name in position_names:
        cleaned_name = clean_csv(raw_name)
        if cleaned_name == "Nil":
            continue
        if cleaned_name not in cleaned_names:
            cleaned_names.append(cleaned_name)

    for cleaned_name in cleaned_names:
        matching_group = None
        for group in groups:
            if any(_positions_can_be_merged(cleaned_name, existing_name) for existing_name in group):
                matching_group = group
                break

        if matching_group is None:
            groups.append([cleaned_name])
        else:
            matching_group.append(cleaned_name)

    alias_map: Dict[str, str] = {}
    for group in groups:
        canonical_name = max(
            group,
            key=lambda name: (
                _extract_ticker_hint(name) is not None,
                len(_core_position_tokens(name)),
                len(name),
            ),
        )
        for name in group:
            alias_map[name] = canonical_name

    return alias_map


def format_currency(amount: Optional[float]) -> str:
    """
    Formatiert einen Betrag als Währung im deutschen Format.

    Args:
        amount: Der zu formatierende Betrag.

    Returns:
        Der formatierte Betrag als String mit €-Symbol.
    """
    if amount is None or amount == 0.0:
        return ""
    us_format = f"{amount:,.2f}"
    ger_format = us_format.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{ger_format} €"

