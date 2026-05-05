"""
Datei-Auswahl-Modul

Stellt gemeinsame Funktionen zur Datei- und Ordnerauswahl für GUI- und CLI-Schnittstellen bereit.
Unterstützt die Auswahl von PDF-Dateien, Ordnern mit PDFs und Filteroperationen.
"""

import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
import re
import logging

# Logging konfigurieren
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DateiAuswahl:
    """
    Eine Klasse zur Handhabung von Datei- und Ordnerauswahl-Operationen.
    
    Bietet eine einheitliche Schnittstelle zur Auswahl von PDF-Dateien und Ordnern,
    die sowohl von GUI- als auch CLI-Schnittstellen verwendet werden kann.
    
    Attribute:
        unterstuetzte_formate (List[str]): Liste der unterstützten Dateiformate.
    """
    
    unterstuetzte_formate = ['.pdf']
    
    def __init__(self):
        """Initialisiert den DateiAuswahl."""
        self.ausgewaehlte_dateien = []
        self._sortier_reihenfolge = 'natürlich'
    
    def waehle_dateien(self, datei_pfade: List[str]) -> List[str]:
        """
        Wählt PDF-Dateien aus einer Liste von Pfaden aus.
        
        Args:
            datei_pfade (List[str]): Liste der zu filternden Dateipfade.
            
        Returns:
            Liste der gültigen PDF-Dateipfade.
        """
        gueltige_dateien = []
        
        for pfad_str in datei_pfade:
            pfad = Path(pfad_str.strip('"'))
            
            if not pfad.exists():
                logger.warning(f"Pfad existiert nicht: {pfad_str}")
                continue
            
            if pfad.is_file() and pfad.suffix.lower() in self.unterstuetzte_formate:
                gueltige_dateien.append(str(pfad))
            elif pfad.is_dir():
                # Wenn es ein Ordner ist, alle PDF-Dateien daraus holen
                pdf_dateien = self.hole_dateien_aus_verzeichnis(str(pfad))
                gueltige_dateien.extend(pdf_dateien)
        
        self.ausgewaehlte_dateien = gueltige_dateien
        return self.ausgewaehlte_dateien
    
    def waehle_ordner(self, ordner_pfad: str) -> List[str]:
        """
        Wählt alle PDF-Dateien aus einem Ordner aus.
        
        Args:
            ordner_pfad (str): Pfad zum Ordner.
            
        Returns:
            Liste der PDF-Dateipfade im Ordner.
        """
        dateien = self.hole_dateien_aus_verzeichnis(ordner_pfad)
        self.ausgewaehlte_dateien = dateien
        return dateien
    
    def hole_dateien_aus_verzeichnis(self, verzeichnis_pfad: str) -> List[str]:
        """
        Holt alle PDF-Dateien aus einem Verzeichnis, rekursiv.
        
        Args:
            verzeichnis_pfad (str): Pfad zum Verzeichnis.
            
        Returns:
            Liste der PDF-Dateipfade, natürlich sortiert.
        """
        verzeichnis_pfad = Path(verzeichnis_pfad)
        
        if not verzeichnis_pfad.is_dir():
            logger.error(f"Kein Verzeichnis: {verzeichnis_pfad}")
            return []
        
        # Rekursives Suchen erlaubt es, Broker-Unterordner unveraendert zu importieren.
        pdf_dateien = [str(datei_pfad) for datei_pfad in verzeichnis_pfad.rglob('*.pdf')]
        pdf_dateien.sort(key=self._natuerlicher_sortier_schluessel)
        
        return pdf_dateien
    
    def _natuerlicher_sortier_schluessel(self, pfad_obj) -> tuple:
        """
        Erzeugt einen Sortierschlüssel für natürliches Sortieren.
        
        Args:
            pfad_obj: Pfad-Objekt oder String.
            
        Returns:
            Tuple für Sortierung.
        """
        if isinstance(pfad_obj, str):
            pfad_obj = Path(pfad_obj)
        
        name_klein = pfad_obj.name.lower()
        teile = [int(text) if text.isdigit() else text for text in re.split(r'(\d+)', name_klein)]
        return (not pfad_obj.is_dir(), teile)
    
    def hole_ausgewaehlte_dateien(self) -> List[str]:
        """
        Holt die aktuell ausgewählten Dateien.
        
        Returns:
            Liste der ausgewählten Dateipfade.
        """
        return self.ausgewaehlte_dateien
    
    def auswahl_leeren(self):
        """Leert die aktuelle Auswahl."""
        self.ausgewaehlte_dateien = []
    
    def datei_hinzufuegen(self, datei_pfad: str) -> bool:
        """
        Fügt eine einzelne Datei zur Auswahl hinzu.
        
        Args:
            datei_pfad (str): Pfad zur Datei.
            
        Returns:
            True wenn erfolgreich hinzugefügt, False sonst.
        """
        pfad = Path(datei_pfad.strip('"'))
        
        if not pfad.exists():
            logger.warning(f"Datei existiert nicht: {datei_pfad}")
            return False
        
        if pfad.is_file() and pfad.suffix.lower() in self.unterstuetzte_formate:
            if str(pfad) not in self.ausgewaehlte_dateien:
                self.ausgewaehlte_dateien.append(str(pfad))
                return True
        
        return False
    
    def datei_entfernen(self, datei_pfad: str) -> bool:
        """
        Entfernt eine Datei aus der Auswahl.
        
        Args:
            datei_pfad (str): Pfad zur zu entfernenden Datei.
            
        Returns:
            True wenn entfernt, False sonst.
        """
        pfad_str = str(Path(datei_pfad.strip('"')))
        
        if pfad_str in self.ausgewaehlte_dateien:
            self.ausgewaehlte_dateien.remove(pfad_str)
            return True
        
        return False
    
    def hole_datei_info(self, datei_pfad: str) -> Dict[str, Any]:
        """
        Holt Informationen über eine Datei.
        
        Args:
            datei_pfad (str): Pfad zur Datei.
            
        Returns:
            Dictionary mit Dateiinformationen.
        """
        pfad = Path(datei_pfad)
        
        if not pfad.exists():
            return {}

        # Erweiterungspunkt fuer spaetere GUI-Details wie Groesse, Aenderungsdatum
        # oder Vorschauinformationen.
        
# Alias für Rückwärtskompatibilität
FileSelector = DateiAuswahl
