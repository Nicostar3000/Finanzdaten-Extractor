"""
Finanz-Parser-Modul

Stellt Funktionen zur Verarbeitung von Finanztransaktionsdaten aus extrahiertem PDF-Text bereit.
"""

import re
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FinanzParser:
    """
    Regelbasierter Parser fuer Broker-PDF-Texte.

    Der Parser arbeitet ohne feste PDF-Koordinaten. Stattdessen liest er den von
    pypdf extrahierten Text zeilenweise und erkennt bekannte Muster fuer Broker,
    Datum, Depot, Positionen, Kurse, Mengen, Gebuehren und Zielsumme.
    """

    def __init__(self):
        self.transactions = []
        self.transaktionen = []  # Alias für Rückwärtskompatibilität
        self._lines = []
        self._kompiliere_muster()
    
    def _kompiliere_muster(self):
        """Bereitet Datumsregeln vor, damit sie beim Parsen schnell verfuegbar sind."""
        self.date_patterns = [
            re.compile(r'\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b'),
            re.compile(r'\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b'),
            re.compile(r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b'),
        ]
    
    def _bereinige_adress_teil(self, text: str) -> str:
        """Putzdienst: Entfernt Kopfzeilen-Müll (Seite, Datum), der in die Adresse gerutscht ist."""
        # Löscht "Seite: 1 von 1" oder "Seite 1 von 1"
        text = re.sub(r'(?i)\bSeite\s*:?\s*\d+\s*von\s*\d+\b', '', text)
        # Löscht "Seite 1" oder "Seite: 1"
        text = re.sub(r'(?i)\bSeite\s*:?\s*\d+\b', '', text)
        # Löscht "Datum: 15.07.2020"
        text = re.sub(r'(?i)\bDatum\s*:\s*\d{1,2}\.\d{1,2}\.\d{2,4}\b', '', text)
        # Löscht "am 15.07.2020"
        text = re.sub(r'(?i)\bam\s+\d{1,2}\.\d{1,2}\.\d{2,4}\b', '', text)
        # Löscht versehentliche Depotnummern
        text = re.sub(r'(?i)\bDepot\s*:?\s*\d+\b', '', text)
        
        # Doppelte Leerzeichen aufräumen, die durch das Löschen entstanden sind
        text = re.sub(r'\s+', ' ', text)
        return text.strip(' ,|')

    def parse_text(self, text: str) -> List[Dict[str, Any]]:
        """Parst einen kompletten PDF-Text in eine Liste normalisierter Transaktionen."""
        self.transactions = []
        self.transaktionen = []
        
        if not text or not text.strip():
            logger.warning("Leerer Text an den Parser übergeben")
            return self.transactions
            
        # 1. Brokername: Der erste nicht-leere String im PDF ist verbindlich.
        zeilen = [zeile.strip() for zeile in text.split('\n') if zeile.strip()]
        self.global_broker = zeilen[0] if zeilen else "Nil"
        
        # 2. Datum und Depot
        self.global_date = self._extract_global_date(text)
        self.global_depot = self._extract_global_depot(text)
        self.global_target_sum = None
        self.global_time = self._extract_global_time(text)
        self.global_marketplace = self._extract_global_marketplace(text)
        
        # 3. Kontakt-Daten extrahieren
        self.global_email = self._extract_regex(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', text)
        self.global_website = self._extract_regex(r'(www\.[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', text)
        self.global_phone = self._extract_regex(r'Tel\.?[^\d]*([\d\s\-\(\)/]{8,20})', text)
        self.global_fax = self._extract_regex(r'Fax[^\d]*([\d\s\-\(\)/]{8,20})', text)
        
        # 4. Adressen intelligent trennen (Kunde vs. Firma)
        self.company_address = "Nil"
        self.customer_address = "Nil"
        self.customer_name = "Nil"
        
        # Investbank hat die Firmenadresse oft in einer Zeile mit | getrennt
        inv_match = re.search(r'\|\s*([^|\n]+)\s*\|\s*(\d{5}\s+[^|\n]+)', text)
        if inv_match:
            street = self._bereinige_adress_teil(inv_match.group(1))
            city = self._bereinige_adress_teil(inv_match.group(2))
            self.company_address = f"{street}, {city}"
            
        # Wir suchen nach allen Adress-Blöcken (Name -> Straße+Nr -> PLZ+Stadt)
        blocks = re.findall(r'([A-ZÄÖÜ][^\n]*?)\s*\n\s*([A-ZÄÖÜ][^\n]*?\s\d+[a-zA-Z]?)\s*\n\s*(\d{5}\s+[A-ZÄÖÜ][^\n]*)', text)
        for block in blocks:
            name, street_raw, city_raw = block
            
            # WICHTIG: Hier schicken wir Straße und Stadt durch die Waschanlage!
            street_clean = self._bereinige_adress_teil(street_raw)
            city_clean = self._bereinige_adress_teil(city_raw)
            
            addr = f"{street_clean}, {city_clean}"
            name_clean = name.strip()
            
            # Gehört der Block zur Firma?
            if any(kw in name_clean for kw in ["Handelsrepublik", "Finance Free", "Investbank", "GmbH", "AG", "Capital"]):
                if self.company_address == "Nil":
                    self.company_address = addr
            else:
                # Gehört der Block zum Kunden (z.B. Reiner Zufall)
                if self.customer_address == "Nil":
                    self.customer_address = addr
                    self.customer_name = name_clean
        
        # Nachdem globale Metadaten gefunden wurden, werden die eigentlichen
        # Transaktionszeilen erkannt und mit diesen Metadaten angereichert.
        self._parse_by_lines(text)
        
        for t in self.transactions:
            t['target_sum'] = self.global_target_sum
            
        return self.transactions
        
    def _extract_regex(self, pattern: str, text: str) -> str:
        """Liest den ersten Treffer eines Regex aus oder gibt Nil zurueck."""
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).strip() if match else "Nil"

    def _extract_global_date(self, text: str) -> Optional[str]:
        """Findet das Dokumentdatum und normalisiert zweistellige Jahreszahlen."""
        match = re.search(r'Datum:\s*(\d{1,2})\.(\d{1,2})\.(\d{2,4})', text, re.IGNORECASE)
        if match:
            day, month, year_str = match.groups()
            year = int(year_str)
            year = 2000 + year if year < 100 else year
            return f"{int(day):02d}.{int(month):02d}.{year:04d}"
        
        match = re.search(r'am\s+(\d{1,2})\.(\d{1,2})\.(\d{2,4})', text, re.IGNORECASE)
        if match:
            day, month, year_str = match.groups()
            year = int(year_str)
            year = 2000 + year if year < 100 else year
            return f"{int(day):02d}.{int(month):02d}.{year:04d}"
            
        return None

    def _extract_global_depot(self, text: str) -> str:
        """Extrahiert die Depotnummer, falls sie im Dokumentkopf vorhanden ist."""
        match = re.search(r'Depot[^\d]*(\d{6,15})', text, re.IGNORECASE)
        if match:
            return match.group(1)
        return "Nil"

    def _extract_global_time(self, text: str) -> str:
        """Extrahiert eine Uhrzeit aus typischen Header-/Detailfeldern."""
        patterns = [
            r'(?i)\b(?:uhrzeit|zeit|handelszeit|ausführungszeit|ausfuehrungszeit)\s*[:\-]?\s*(\d{1,2}[:.]\d{2}(?::\d{2})?)\b',
            r'(?i)\bum\s+(\d{1,2}[:.]\d{2}(?::\d{2})?)\s*uhr\b',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return self._normalize_time(match.group(1))
        return "Nil"

    def _extract_global_marketplace(self, text: str) -> str:
        """Extrahiert Handelsplatz/Boerse aus haeufigen Formulierungen."""
        patterns = [
            r'(?i)\b(?:handelsplatz|börse|boerse|marktplatz|ausführungsplatz|ausfuehrungsplatz)\s*[:\-]?\s*([^\n\r;|]+)',
            r'(?i)\b(?:auf|an der)\s+(xetra|tradegate(?:\s+exchange)?|gettex|ls\s+exchange|lang\s*&?\s*schwarz|quotrix|börse\s+stuttgart|boerse\s+stuttgart|frankfurter\s+wertpapierbörse|frankfurter\s+wertpapierboerse|euronext|nyse|nasdaq)\b',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return self._normalize_marketplace(match.group(1))
        return "Nil"

    def _normalize_time(self, value: str) -> str:
        value = str(value or "").strip().replace(".", ":")
        return value if re.match(r'^\d{1,2}:\d{2}(?::\d{2})?$', value) else "Nil"

    def _normalize_marketplace(self, value: str) -> str:
        cleaned = re.sub(r'\s+', ' ', str(value or "")).strip(" ,.;:-")
        if not cleaned:
            return "Nil"
        # Abschneiden bei typischen Feldtrennern aus PDF-Tabellen.
        cleaned = re.split(r'\s{2,}|\s\|\s|;|,(?=\s*[A-ZÄÖÜ])', cleaned)[0].strip()
        return cleaned or "Nil"

    def _extract_time_and_marketplace(self, line: str, line_num: int) -> tuple[str, str]:
        """Sucht Uhrzeit und Handelsplatz in Zeile + Nachbarschaft."""
        context_lines = [line]
        for offset in (-2, -1, 1, 2):
            idx = line_num + offset
            if 0 <= idx < len(self._lines):
                neighbor = self._lines[idx].strip()
                if neighbor:
                    context_lines.append(neighbor)
        context_text = "\n".join(context_lines)

        local_time = self._extract_global_time(context_text)
        local_marketplace = self._extract_global_marketplace(context_text)

        time_value = local_time if local_time != "Nil" else self.global_time
        market_value = local_marketplace if local_marketplace != "Nil" else self.global_marketplace
        return time_value, market_value

    def _to_float(self, s: str) -> Optional[float]:
        s = re.sub(r'[€$a-zA-Z()]', '', s).strip()
        if not s:
            return None
        if not re.match(r'^-?\d+[.,\d]*$', s):
            return None
        try:
            if len(s) >= 3 and s[-3] == ',':
                return float(s.replace('.', '').replace(',', '.'))
            if len(s) >= 3 and s[-3] == '.':
                return float(s.replace(',', ''))
            if ',' in s and '.' not in s:
                return float(s.replace(',', '.'))
            return float(s)
        except ValueError:
            return None

    def _parse_by_lines(self, text: str):
        """Durchlaeuft alle Textzeilen und merkt sich das zuletzt erkannte Datum."""
        lines = text.split('\n')
        self._lines = lines
        last_seen_date = self.global_date
        
        for line_num, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            for pattern in self.date_patterns:
                match = pattern.search(line)
                if match:
                    groups = match.groups()
                    if len(groups[0]) == 4:
                        year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                    else:
                        day, month, year_str = int(groups[0]), int(groups[1]), groups[2]
                        year = int(year_str)
                        year = 2000 + year if year < 100 else year
                        
                    last_seen_date = f"{day:02d}.{month:02d}.{year:04d}"
                    break
            
            transaction = self._parse_line(line, line_num, last_seen_date)
            if transaction:
                self.transactions.append(transaction)
                self.transaktionen.append(transaction)  # Duplikat für Kompatibilität
    
    def _parse_line(self, line: str, line_num: int, current_date: Optional[str]) -> Optional[Dict[str, Any]]:
        """Erkennt aus einer einzelnen Zeile entweder Position, Gebuehr oder Zielsumme."""
        if self._is_non_transaction_line(line):
            return None
            
        tokens = line.split()
        if len(tokens) < 2:
            return None
            
        date_to_use = current_date or "Nil"
            
        base_info = {
            'line_number': line_num + 1,
            'raw_line': line,
            'broker': self.global_broker,
            'date': date_to_use, 
            'company_address': self.company_address,
            'company_email': self.global_email,
            'company_website': self.global_website,
            'company_phone': self.global_phone,
            'company_fax': self.global_fax,
            'customer_name': self.customer_name,
            'customer_address': self.customer_address,
            'depot': self.global_depot
        }
        uhrzeit, handelsplatz = self._extract_time_and_marketplace(line, line_num)
        base_info['uhrzeit'] = uhrzeit
        base_info['handelsplatz'] = handelsplatz
            
        # 1. AKTIEN-POSITIONEN
        if len(tokens) >= 4:
            anzahl = self._to_float(tokens[-3])
            kurs = self._to_float(tokens[-2])
            betrag_gelesen = self._to_float(tokens[-1])
            
            if anzahl is not None and kurs is not None and betrag_gelesen is not None:
                raw_name = " ".join(tokens[:-3])
                for pattern in self.date_patterns:
                    raw_name = pattern.sub('', raw_name).strip()
                    
                name = re.sub(r'\s+', ' ', raw_name)
                calculated_betrag = round(anzahl * kurs, 2)
                
                info = base_info.copy()
                info.update({
                    'position': name,
                    'kurs': kurs,
                    'anzahl': anzahl,
                    'amount': calculated_betrag,
                    'description': f"Depot: {self.global_depot} | Datum: {date_to_use}"
                })
                return info

        # 2. GEBÜHREN
        betrag = self._to_float(tokens[-1])
        if betrag is not None:
            raw_name = " ".join(tokens[:-1])
            if any(kw in raw_name.lower() for kw in ['fremdkostenzuschlag', 'provision', 'spesen', 'kosten', 'makler']):
                for pattern in self.date_patterns:
                    raw_name = pattern.sub('', raw_name).strip()
                name = re.sub(r'\s+', ' ', raw_name)
                
                info = base_info.copy()
                info.update({
                    'position': name,
                    'kurs': None,
                    'anzahl': None,
                    'amount': betrag,
                    'description': f"Depot: {self.global_depot} | Datum: {date_to_use} (Gebühr)",
                })
                return info

        # 3. ZIELSUMME
        if len(tokens) >= 3:
            betrag = self._to_float(tokens[-1])
            date_match = re.match(r'(\d{1,2})\.(\d{1,2})\.(\d{2,4})', tokens[-2])
            
            if betrag is not None and date_match:
                konto = " ".join(tokens[:-2])
                if konto.isdigit():
                    self.global_target_sum = betrag
                    return None

        return None
    
    def _is_non_transaction_line(self, line: str) -> bool:
        """Filtert Kopfzeilen, Tabellenueberschriften und sonstige Nicht-Buchungen."""
        if len(line) < 5: return True
        skip_patterns = [
            r'^--- page', r'^seite', r'^page',
            r'^kontoauszug', r'^kontostand', r'^kaufbeleg', r'^wertpapierabrechnung',
            r'^übersicht', r'^abrechnung', r'^buchung', 
            r'kauf um', r'auf xetra', 
            r'^position', r'betrag in eur'
        ]
        line_lower = line.lower()
        for pattern in skip_patterns:
            if re.search(pattern, line_lower): return True
        return False

# Alias für Rückwärtskompatibilität
FinancialParser = FinanzParser
