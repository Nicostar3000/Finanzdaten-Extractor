import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys
import subprocess
from pathlib import Path
import logging

# Import core modules
from .core import FileSelector
from .csv_export import write_transactions_csv
from .portfolio_analysis import build_extracted_data
from .transaction_service import extract_pdf_result, extract_pdf_results, flatten_successful_transactions
from .gui_viewer import DataViewerApp, load_and_view
from .utils import natural_sort_key

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DateiAuswahlApp:
    """
    Erste GUI-Stufe fuer die PDF-Auswahl.

    Diese Ansicht sammelt PDF-Dateien, bietet direkten CSV-Export und kann die
    ausgewaehlten Dateien an den detaillierten DataViewer mit Diagrammen uebergeben.
    """

    def __init__(self, root, restore_snapshot=None):
        self.root = root
        self.root.title("PDF Auswahl-Tool")
        self.root.geometry("750x500")

        # Macht das Fenster zu einem Tool-Fenster (entfernt Minimieren/Maximieren)
        # und verhindert manuelles Ändern der Größe
        self.root.attributes('-toolwindow', True)
        self.root.resizable(False, False)

        # Versucht ein moderneres Design (Theme) anzuwenden, falls verfügbar
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")

        self.aktueller_pfad = tk.StringVar()
        self.current_path = self.aktueller_pfad
        self.inserted_items = []
        
        # Initialisiere Kernmodule
        self.datei_auswahl = FileSelector()
        
        # Diese Variable speichert die finale Liste der Pfade vor dem Schließen
        self.final_pdf_pfade = []
        
        # Speichere extrahierte Daten für jede PDF
        self.extrahierte_daten = {}

        self.erstelle_widgets()
        if restore_snapshot:
            self._apply_restore_snapshot(restore_snapshot)
        self.bind_mousewheel()

    def _apply_restore_snapshot(self, snapshot):
        """Stellt die zuletzt angezeigte PDF-Liste und Checkbox-Zustaende wieder her."""
        self.inserted_items.clear()
        for widget in list(self.scrollable_frame.winfo_children()):
            widget.destroy()
        for entry in snapshot:
            path = Path(entry["path"])
            if not path.exists():
                continue
            checked = bool(entry.get("checked", True))
            if path.is_dir() or path.suffix.lower() == ".pdf":
                self.create_row(path, checked=checked)
        self.refresh_list_sorting()

    def erstelle_widgets(self):
        # --- OBERER BEREICH (Eingabeleiste und Buttons) ---
        oberer_bereich = ttk.Frame(self.root, padding=(10, 10, 10, 5))
        oberer_bereich.pack(fill=tk.X)

        self.pfad_eingabe = ttk.Entry(oberer_bereich, textvariable=self.aktueller_pfad, font=("Segoe UI", 10))
        self.pfad_eingabe.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        # Wenn man 'Enter' im Textfeld drückt, wird der Pfad eingefügt
        self.pfad_eingabe.bind("<Return>", lambda e: self.fuege_inhalt_ein(self.aktueller_pfad.get()))

        # Ein einzelner Dropdown-Button zum Durchsuchen
        durchsuchen_menue_btn = ttk.Menubutton(oberer_bereich, text="Durchsuchen ▾")
        durchsuchen_menue = tk.Menu(durchsuchen_menue_btn, tearoff=0)
        
        durchsuchen_menue.add_command(label="📁 Ordner auswählen...", command=self.browse_folder)
        durchsuchen_menue.add_command(label="📄 PDF Dateien auswählen...", command=self.browse_file)
        
        durchsuchen_menue_btn["menu"] = durchsuchen_menue
        durchsuchen_menue_btn.pack(side=tk.RIGHT)

        # --- UNTERER BEREICH (Bestätigungs-Button) ---
        unterer_bereich = ttk.Frame(self.root, padding=10)
        unterer_bereich.pack(side=tk.BOTTOM, fill=tk.X)

        #aktion_btn = ttk.Button(unterer_bereich, text="Bestätigen & Daten extrahieren", command=self.submit_and_close)
        #aktion_btn.pack(fill=tk.X, ipady=5) 

        # Button to open data viewer
        anzeigen_btn = ttk.Button(unterer_bereich, text="📊 Daten anzeigen & visualisieren", command=self.open_data_viewer)
        anzeigen_btn.pack(fill=tk.X, ipady=5, pady=(5, 0))

        export_btn = ttk.Button(unterer_bereich, text="Als CSV speichern", command=self.export_selected_to_csv)
        export_btn.pack(fill=tk.X, ipady=5, pady=(5, 0))

        # --- MITTLERER BEREICH (Scrollbare Liste) ---
        listen_container = tk.Frame(self.root, bg="white", bd=1, relief="sunken")
        listen_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.canvas = tk.Canvas(listen_container, bg="white", highlightthickness=0)
        scrollbar = ttk.Scrollbar(listen_container, orient="vertical", command=self.canvas.yview)
        
        self.scrollable_frame = tk.Frame(self.canvas, bg="white")

        # Passt den Scrollbereich automatisch an den Inhalt an
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw", width=self.canvas.winfo_width())
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfig(1, width=e.width))
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def bind_mousewheel(self):
        # Bindet das Mausrad je nach Betriebssystem (Windows/Mac vs Linux)
        if sys.platform == "linux":
            self.root.bind_all("<Button-4>", self._on_mousewheel)
            self.root.bind_all("<Button-5>", self._on_mousewheel)
        else:
            self.root.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        # Verhindert das Scrollen, wenn die Liste noch nicht lang genug ist
        if self.scrollable_frame.winfo_height() <= self.canvas.winfo_height():
            return

        if sys.platform == "win32":
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        elif sys.platform == "darwin":
            self.canvas.yview_scroll(int(-1 * event.delta), "units")
        else:
            if event.num == 4:
                self.canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self.canvas.yview_scroll(1, "units")

    def browse_folder(self):
        selected_directory = filedialog.askdirectory()
        if selected_directory:
            self.aktueller_pfad.set(selected_directory)
            self.insert_contents(selected_directory)

    def browse_file(self):
        # Erlaubt die Auswahl von einer oder mehreren PDF-Dateien
        selected_files = filedialog.askopenfilenames(
            title="PDF Dateien auswählen",
            filetypes=[("PDF Dateien", "*.pdf"), ("Alle Dateien", "*.*")]
        )
        if selected_files:
            for file_path in selected_files:
                self.insert_contents(file_path)

    def natural_sort_key(self, path_obj):
        # Sorgt dafür, dass "Datei 10" nach "Datei 2" kommt (natürliche Sortierung)
        return (not path_obj.is_dir(), natural_sort_key(path_obj.name))

    def insert_contents(self, path_str):
        # Entfernt eventuelle Anführungszeichen, falls der Pfad aus Windows kopiert wurde
        path_str = path_str.strip("\"'")

        if not path_str.strip():
            return

        target_path = Path(path_str)
        if not target_path.exists():
            messagebox.showwarning("Ungültiger Pfad", "Dieser Pfad existiert nicht.")
            return

        if target_path.is_dir():
            try:
                pdf_files = self.datei_auswahl.hole_dateien_aus_verzeichnis(str(target_path))
                if not pdf_files:
                    messagebox.showwarning("Keine PDFs gefunden", f"Im Ordner wurden keine PDF-Dateien gefunden:\n{target_path}")
                    return

                for pdf_file in pdf_files:
                    self.create_row(Path(pdf_file))
            except PermissionError:
                messagebox.showerror("Zugriffsfehler", f"Kein Zugriff auf den Inhalt von:\n{target_path}")
        else:
            # Wenn es eine einzelne Datei ist, prüfen, ob es wirklich ein PDF ist
            if target_path.suffix.lower() == ".pdf":
                self.create_row(target_path)
            else:
                messagebox.showwarning("Falsches Format", "Nur PDF-Dateien sind erlaubt.")

        # Textfeld wieder leeren
        self.aktueller_pfad.set("")
        # Die gesamte Liste optisch neu sortieren
        self.refresh_list_sorting()

    def create_row(self, path, checked=True):
        # Verhindert, dass dieselbe Datei mehrfach eingefügt wird
        if any(item["path"] == str(path) for item in self.inserted_items):
            return

        # Trennlinie über jeder Zeile (außer der ersten)
        if self.inserted_items:
            separator = ttk.Separator(self.scrollable_frame, orient="horizontal")
            separator.pack(fill=tk.X, padx=5)

        row_frame = tk.Frame(self.scrollable_frame, bg="white", pady=2)
        
        # Checkbox auf der linken Seite
        is_checked = tk.BooleanVar(value=checked)

        # Hilfsfunktion: Zeile ausgrauen oder aktivieren je nach Checkbox-Zustand
        def toggle_row_appearance(*args):
            if is_checked.get():
                row_frame.config(bg="white")
                lbl.config(fg="black", bg="white", font=("Segoe UI", 9, "normal"))
                chk.config(bg="white", activebackground="white")
            else:
                row_frame.config(bg="#f5f5f5")
                lbl.config(fg="#aaaaaa", bg="#f5f5f5", font=("Segoe UI", 9, "normal"))
                chk.config(bg="#f5f5f5", activebackground="#f5f5f5")

        chk = tk.Checkbutton(row_frame, variable=is_checked, bg="white", activebackground="white",
                             command=toggle_row_appearance)
        chk.pack(side=tk.LEFT)

        # Icon und Dateiname in der Mitte
        icon = "📁" if path.is_dir() else "📄"
        lbl_text = f"{icon} {path.name}   ({path.parent})"
        
        lbl = tk.Label(row_frame, text=lbl_text, bg="white", fg="black", anchor="w", cursor="hand2")
        lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Hover-Effekte nur wenn die Zeile aktiv (angehakt) ist
        def on_enter(e):
            if is_checked.get():
                lbl.config(fg="blue", font=("Segoe UI", 9, "underline"))

        def on_leave(e):
            if is_checked.get():
                lbl.config(fg="black", font=("Segoe UI", 9, "normal"))
            else:
                lbl.config(fg="#aaaaaa", font=("Segoe UI", 9, "normal"))

        lbl.bind("<Enter>", on_enter)
        lbl.bind("<Leave>", on_leave)
        
        # Öffnet die Datei/den Ordner bei einem Klick
        lbl.bind("<Button-1>", lambda e, p=path: self.open_item(p))

        # Roter 'X' Button zum Entfernen
        del_btn = tk.Button(row_frame, text="✖", fg="red", bg="white", font=("Arial", 9, "bold"), 
                            relief="flat", cursor="hand2", overrelief="raised")
        del_btn.pack(side=tk.RIGHT, padx=(5, 0))
        del_btn.config(command=lambda f=row_frame, p=str(path): self.remove_item(f, p))

        # 'Expand' Button, der nur bei Ordnern angezeigt wird
        if path.is_dir():
            expand_btn = tk.Button(row_frame, text="🔽 Entpacken", bg="#f0f0f0", font=("Segoe UI", 8),
                                   relief="flat", cursor="hand2", overrelief="raised")
            expand_btn.pack(side=tk.RIGHT, padx=5)
            expand_btn.config(command=lambda f=row_frame, p=str(path): self.expand_folder(f, p))

        # Fügt das Element zu unserer internen Liste hinzu
        self.inserted_items.append({
            "path": str(path), 
            "var": is_checked, 
            "frame": row_frame
        })
        if not checked:
            toggle_row_appearance()

    def refresh_list_sorting(self):
        # Sortiert die interne Liste im Hintergrund neu
        self.inserted_items.sort(key=lambda item: self.natural_sort_key(Path(item["path"])))
        
        # Alle Widgets aus dem scrollable_frame entfernen und neu aufbauen
        for widget in self.scrollable_frame.winfo_children():
            widget.pack_forget()

        for i, item in enumerate(self.inserted_items):
            if i > 0:
                # Trennlinie vor jedem Element außer dem ersten wiederherstellen
                separator = ttk.Separator(self.scrollable_frame, orient="horizontal")
                separator.pack(fill=tk.X, padx=5)
            item["frame"].pack(fill=tk.X, padx=5, pady=2)

    def expand_folder(self, frame, path_str):
        # Entfernt den Ordner aus der Liste und fügt stattdessen seinen Inhalt ein
        self.remove_item(frame, path_str)
        self.insert_contents(path_str)

    def remove_item(self, frame, path_str):
        # Löscht das UI-Element und entfernt es aus der internen Liste
        frame.destroy()
        self.inserted_items = [item for item in self.inserted_items if item["path"] != path_str]
        # Trennlinien neu aufbauen nach Entfernen eines Elements
        self.refresh_list_sorting()

    def _extract_financial_data(self, pdf_path: str) -> dict:
        return extract_pdf_result(pdf_path)

    def submit_and_close(self):
        pdf_list = self._get_selected_pdf_paths()

        if not pdf_list:
            messagebox.showwarning("Achtung", "Es wurden keine PDFs ausgewählt!")
            return
        
        extracted_results = extract_pdf_results(pdf_list)
        
        self.extracted_data = build_extracted_data(pdf_list, extracted_results)
        self.final_pdf_paths = pdf_list
        self._show_extraction_summary(extracted_results)
        self.root.destroy() 

    def _show_extraction_summary(self, extracted_results):
        total_files = len(extracted_results)
        successful = sum(1 for r in extracted_results if r.get('success'))
        failed = [r for r in extracted_results if not r.get('success')]
        total_transactions = sum(len(r.get('transactions', [])) for r in extracted_results if r.get('success'))
        message_lines = [
            f"Ausgewählte PDF-Dateien: {total_files}",
            f"Erfolgreich verarbeitet: {successful}",
            f"Transaktionen insgesamt: {total_transactions}"
        ]
        if failed:
            message_lines.append("")
            message_lines.append("Einige Dateien konnten nicht verarbeitet werden:")
            for result in failed:
                name = Path(result.get('file', '')).name or "Unbekannt"
                error = result.get('error', "Unbekannter Fehler")
                message_lines.append(f"- {name}: {error}")

        messagebox.showinfo("Extraktionsübersicht", "\n".join(message_lines))

    def _get_selected_pdf_paths(self):
        pdf_list = []
        for item in self.inserted_items:
            if item["var"].get() == True:
                file_path = Path(item["path"])
                if file_path.is_file() and file_path.suffix.lower() == ".pdf":
                    pdf_list.append(str(file_path))
        return pdf_list

    def _extract_transactions_from_pdfs(self, pdf_list):
        return flatten_successful_transactions(extract_pdf_results(pdf_list))

    def export_selected_to_csv(self):
        """Exportiert die aktuell markierten PDFs direkt aus der Auswahl-GUI."""
        pdf_list = self._get_selected_pdf_paths()
        if not pdf_list:
            messagebox.showwarning("Achtung", "Es wurden keine PDFs ausgewählt!")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Dateien", "*.csv"), ("Alle Dateien", "*.*")],
            title="Finanzdaten exportieren"
        )
        if not file_path:
            return

        transactions = self._extract_transactions_from_pdfs(pdf_list)
        if not transactions:
            messagebox.showwarning("Keine Daten", "Keine Daten zum Exportieren vorhanden.")
            return

        try:
            saved_path = write_transactions_csv(transactions, file_path)
            messagebox.showinfo("Export abgeschlossen", f"Daten erfolgreich exportiert:\n{saved_path}")
        except Exception as e:
            messagebox.showerror("Exportfehler", f"Fehler beim Exportieren:\n{str(e)}")

    def open_item(self, path):
        try:
            if sys.platform == "win32":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.call(["open", str(path)])
            else:
                subprocess.call(["xdg-open", str(path)])
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte nicht geöffnet werden:\n{path}\n\n{str(e)}")
    
    def open_data_viewer(self):
        """Oeffnet die Diagramm-/Tabellenansicht mit den markierten PDFs."""
        pdf_list = self._get_selected_pdf_paths()
        
        if not pdf_list:
            messagebox.showwarning("Achtung", "Es wurden keine PDFs ausgewählt!")
            return

        selection_snapshot = [
            {"path": item["path"], "checked": bool(item["var"].get())}
            for item in self.inserted_items
        ]

        self.root.destroy()
        root = tk.Tk()
        app = DataViewerApp(root, restored_pdf_selection=selection_snapshot)
        app.load_from_pdfs(pdf_list)
        root.mainloop()


def get_pdf_paths():
    """Startet die Auswahl-GUI und gibt danach die gewaehlten PDF-Pfade zurueck."""
    root = tk.Tk()
    app = DateiAuswahlApp(root)
    root.mainloop()
    return app.final_pdf_pfade


def extract_financial_data():
    """Startet die Auswahl-GUI und gibt die extrahierten Rohdaten zurueck."""
    root = tk.Tk()
    app = DateiAuswahlApp(root)
    root.mainloop()
    return app.extrahierte_daten
