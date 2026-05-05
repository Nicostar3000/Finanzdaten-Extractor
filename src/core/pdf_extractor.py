"""
PDF-Extraktor-Modul

Stellt Funktionen zur Textextraktion aus PDF-Dateien bereit.
Unterstützt einfache Textextraktion.
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging

# Logging konfigurieren
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PDFExtraktor:
    """
    Eine Klasse zur Textextraktion aus PDF-Dateien.
    
    Attribute:
        unterstuetzte_formate (List[str]): Liste der unterstützten Dateiformate.
    """
    
    unterstuetzte_formate = ['.pdf']
    
    def __init__(self):
        """Initialisiert den PDFExtraktor."""
        self._pypdf = None
        self._importiere_pypdf()
    
    def _importiere_pypdf(self):
        """Versucht pypdf zu importieren."""
        try:
            import pypdf
            self._pypdf = pypdf
            logger.info("Verwende pypdf für PDF-Extraktion")
        except ImportError:
            logger.error("pypdf ist nicht verfügbar")
            self._pypdf = None
    
    def ist_gueltige_pdf(self, datei_pfad: str) -> bool:
        """
        Prüft, ob eine Datei eine gültige PDF ist.
        
        Args:
            datei_pfad (str): Pfad zur PDF-Datei.
            
        Returns:
            bool: True wenn die Datei eine gültige PDF ist, False sonst.
        """
        pfad = Path(datei_pfad)
        if not pfad.exists():
            logger.error(f"Datei existiert nicht: {datei_pfad}")
            return False
        if pfad.suffix.lower() not in self.unterstuetzte_formate:
            logger.error(f"Nicht unterstütztes Dateiformat: {pfad.suffix}")
            return False
        return True
    
    def extrahiere_text(self, datei_pfad: str) -> str:
        """
        Extrahiert den gesamten Text aus einer PDF-Datei.
        
        Args:
            datei_pfad (str): Pfad zur PDF-Datei.
            
        Returns:
            str: Extrahierter Text aus der PDF.
        """
        if not self.ist_gueltige_pdf(datei_pfad):
            return ""
        
        text = ""
        
        # Die Extraktion bleibt hinter einer Methode gekapselt, damit spaeter bei
        # Bedarf eine andere Bibliothek ergaenzt werden kann.
        if self._pypdf:
            text = self._extrahiere_mit_pypdf(datei_pfad)
        else:
            logger.error("Keine PDF-Extraktionsbibliothek verfügbar")
            return ""
        
        return text
    
    def _extrahiere_mit_pypdf(self, datei_pfad: str) -> str:
        """Extrahiert Text mit pypdf."""
        text = ""
        try:
            with open(datei_pfad, 'rb') as datei:
                reader = self._pypdf.PdfReader(datei)
                for seiten_num, seite in enumerate(reader.pages, 1):
                    seiten_text = seite.extract_text()
                    if seiten_text:
                        # WICHTIG: Die "--- Seite ---" Marker wurden entfernt,
                        # damit der Firmenname als erste Zeile gelesen werden kann!
                        text += seiten_text + "\n"
                logger.info(f"Text aus {datei_pfad} extrahiert ({len(reader.pages)} Seiten)")
        except Exception as e:
            logger.error(f"Fehler beim Extrahieren mit pypdf: {e}")
            return ""
        return text
    
    def hole_pdf_info(self, datei_pfad: str) -> Dict[str, Any]:
        """
        Holt grundlegende Informationen über eine PDF-Datei.
        
        Args:
            datei_pfad (str): Pfad zur PDF-Datei.
            
        Returns:
            Dict mit PDF-Metadaten (Seiten, etc.).
        """
        if not self.ist_gueltige_pdf(datei_pfad):
            return {}
        
        info = {
            'datei_pfad': datei_pfad,
            'datei_name': Path(datei_pfad).name,
            'datei_groesse': os.path.getsize(datei_pfad) if os.path.exists(datei_pfad) else 0
        }
        
        if self._pypdf:
            try:
                with open(datei_pfad, 'rb') as datei:
                    reader = self._pypdf.PdfReader(datei)
                    info['seiten_anzahl'] = len(reader.pages)
                    info['metadaten'] = reader.metadata if hasattr(reader, 'metadata') else {}
            except Exception as e:
                logger.error(f"Fehler beim Holen der PDF-Info: {e}")
                info['seiten_anzahl'] = 0
        
        return info


def extrahiere_text_aus_datei(datei_pfad: str) -> str:
    """Komfortfunktion fuer Aufrufer, die keine Extraktor-Instanz halten muessen."""
    extraktor = PDFExtraktor()
    return extraktor.extrahiere_text(datei_pfad)


def extrahiere_text_aus_verzeichnis(verzeichnis_pfad: str) -> Dict[str, str]:
    """Extrahiert alle PDFs in einem Ordner in ein Mapping Dateiname -> Text."""
    extraktor = PDFExtraktor()
    ergebnisse = {}
    
    verzeichnis_pfad = Path(verzeichnis_pfad)
    if not verzeichnis_pfad.is_dir():
        logger.error(f"Kein Verzeichnis: {verzeichnis_pfad}")
        return ergebnisse
    
    for pdf_datei in sorted(verzeichnis_pfad.glob("*.pdf")):
        text = extraktor.extrahiere_text(str(pdf_datei))
        ergebnisse[pdf_datei.name] = text
    
    return ergebnisse

# Alias für Rückwärtskompatibilität
PDFExtractor = PDFExtraktor
