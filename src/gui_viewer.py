"""
GUI Data Viewer Modul für den PDF Financial Data Extractor
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import os
import math
import logging
from datetime import datetime, timedelta
import matplotlib.dates as mdates

from .core import PDFExtractor, FinancialParser, FileSelector
from .csv_export import write_transactions_csv
from .ui.widgets import CheckDropdown, InfoTooltip, bind_mousewheel_to_canvas, set_tooltip_style
from .portfolio_analysis import (
    attach_source_file,
    build_broker_info_data,
    build_line_chart_data,
    build_pie_bucket_data,
    build_position_chart_data,
    calculate_file_validation_sums,
    combine_positions,
    filter_transactions,
    get_bucket_positions,
    group_transactions_by_file,
    summarize_transactions,
)
from .transaction_service import extract_transactions_from_pdfs
from .utils import clean_csv, format_quantity, natural_sort_key

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataViewerApp:
    """
    Detail-GUI fuer Tabellen, Validierung, Diagramme und CSV-Export.

    Die Klasse haelt alle geladenen Transaktionen in self.all_transactions. Filter
    und Diagramme arbeiten darauf, ohne die Originaldaten zu veraendern.
    """

    def __init__(self, root, extracted_data=None, restored_pdf_selection=None):
        self.root = root
        self.root.title("PDF Finanzdaten Extraktor")
        self._maximize_viewer_window()
        self._restore_pdf_snapshot = restored_pdf_selection
        
        self.file_selector = FileSelector()
        self.pdf_extraktor = PDFExtractor()
        self.finanz_parser = FinancialParser()
        
        self.extracted_data = extracted_data or {}
        self.all_transactions = []
        self._pie_hover_entries = []
        self._pie_hover_annotation = None
        self._pie_hover_axes = None
        self._active_pie_wedge = None
        self._pie_drag_start = None
        self._pie_drag_xlim = None
        self._pie_drag_ylim = None
        self._pie_default_xlim = None
        self._pie_default_ylim = None
        self._pie_selected_bucket = None
        self._pie_selected_position = None
        self._pie_chart_data = {}
        self._pie_bucket_data = []
        self._pie_total_amount = 1.0
        self._pie_animation_after_id = None
        self._pie_animation_state = None
        self._pie_press_event = None
        self._pie_active_entry = None
        self._pie_last_hover_xy = None
        self._filter_refresh_job = None
        self._dark_mode = tk.BooleanVar(value=False)

        if self.extracted_data:
            self._process_extracted_data()
        
        self.create_widgets()
    
    def _format_currency(self, amount: float) -> str:
        if amount is None: return ""
        us_format = f"{amount:,.2f}"
        ger_format = us_format.replace(',', 'X').replace('.', ',').replace('X', '.')
        return f"{ger_format} €"

    def _format_quantity(self, quantity: float) -> str:
        return format_quantity(quantity)

    def _process_extracted_data(self):
        results = self.extracted_data.get('results', [])
        for result in results:
            if result.get('success'):
                transactions = result.get('transactions', [])
                self.all_transactions.extend(attach_source_file(transactions, result.get('file', '')))
    
    def load_from_pdfs(self, pdf_files):
        """Laedt PDF-Dateien direkt in den Viewer und aktualisiert danach alle Ansichten."""
        self.all_transactions = extract_transactions_from_pdfs(pdf_files)
        self._refresh_display()

    def _maximize_viewer_window(self):
        """Maximiert das Fenster (Windows: zoomed, Linux: -zoomed, sonst Bildschirmgroesse)."""
        try:
            self.root.state("zoomed")
        except tk.TclError:
            try:
                self.root.attributes("-zoomed", True)
            except tk.TclError:
                try:
                    w = self.root.winfo_screenwidth()
                    h = self.root.winfo_screenheight()
                    self.root.geometry(f"{w}x{h}+0+0")
                except tk.TclError:
                    self.root.geometry("1400x900")
    
    def create_widgets(self):
        """Baut die Hauptaufteilung aus Zusammenfassung, Diagrammen und Tabellen."""
        shell = ttk.Frame(self.root)
        shell.pack(fill=tk.BOTH, expand=True)

        top_bar = ttk.Frame(shell)
        top_bar.pack(fill=tk.X, padx=10, pady=(8, 0))
        self._back_to_pdf_btn = ttk.Button(
            top_bar,
            text="← Zurück zur PDF-Auswahl",
            command=self._return_to_pdf_selection,
        )
        self._back_to_pdf_btn.pack(side=tk.LEFT)
        ttk.Frame(top_bar).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._theme_toggle_btn = ttk.Button(
            top_bar,
            text="\U0001f319",
            width=4,
            command=self._toggle_dark_mode,
        )
        self._theme_toggle_btn.pack(side=tk.RIGHT)
        InfoTooltip(self._theme_toggle_btn, "Dunkelmodus ein- oder ausschalten (Mond / Sonne).")

        main_container = ttk.Frame(shell)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 10))

        v_paned = ttk.PanedWindow(main_container, orient=tk.VERTICAL)
        v_paned.pack(fill=tk.BOTH, expand=True)

        top_frame = ttk.Frame(v_paned)
        v_paned.add(top_frame, weight=1)

        h_paned = ttk.PanedWindow(top_frame, orient=tk.HORIZONTAL)
        h_paned.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(h_paned, width=600)
        h_paned.add(left_frame, weight=1)

        right_frame = ttk.Frame(h_paned)
        h_paned.add(right_frame, weight=1)

        self._create_top_left_panel(left_frame)
        self._create_top_right_panel(right_frame)

        bottom_frame = ttk.Frame(v_paned)
        v_paned.add(bottom_frame, weight=1)

        self._create_bottom_panel(bottom_frame)

        self._apply_ui_theme()

    def _dropdown_popup_theme_colors(self):
        if self._dark_mode.get():
            return {"link_fg": "#9db9ff", "popup_bg": "#3a3d42"}
        return {"link_fg": "#0a5fbf", "popup_bg": None}

    def _chart_theme(self):
        if self._dark_mode.get():
            return {
                "fig_face": "#2b2b2b",
                "ax_face": "#2b2b2b",
                "tick": "#dddddd",
                "grid": "#666666",
                "pie_wedge_edge": "#4a4a4a",
                "pie_label": "#e8e8e8",
                "pie_connector": "#999999",
                "pie_pct": "#ffffff",
                "pie_title": "#f0f0f0",
                "pie_rest": (0.24, 0.24, 0.24),
                "placeholder": "#c8c8c8",
                "legend_face": "#383838",
                "legend_edge": "#555555",
            }
        return {
            "fig_face": "#ffffff",
            "ax_face": "#ffffff",
            "tick": "#222222",
            "grid": "#bbbbbb",
            "pie_wedge_edge": "#ffffff",
            "pie_label": "#222222",
            "pie_connector": "#666666",
            "pie_pct": "#ffffff",
            "pie_title": "#222222",
            "pie_rest": (0.90, 0.90, 0.90),
            "placeholder": "#444444",
            "legend_face": "#fafafa",
            "legend_edge": "#cccccc",
        }

    def _chart_annotation_colors(self):
        if self._dark_mode.get():
            return {"face": "#3d3d3d", "edge": "#888888", "arrow": "#cccccc"}
        return {"face": "white", "edge": "#333333", "arrow": "#333333"}

    def _toggle_dark_mode(self):
        self._dark_mode.set(not self._dark_mode.get())
        self._apply_ui_theme()

    def _apply_ui_theme(self):
        dark = self._dark_mode.get()
        style = ttk.Style(self.root)
        style.theme_use("clam")

        if dark:
            bg, fg = "#2b2b2b", "#e8e8e8"
            input_bg, input_fg = "#3a3a3a", "#e8e8e8"
            tree_bg, tree_fg = "#323232", "#e4e4e4"
            sel_bg, sel_fg = "#3d5a80", "#ffffff"
            tab_bg, tab_fg = "#3a3a3a", "#cccccc"
            tab_sel_bg, tab_sel_fg = "#4a6fa5", "#ffffff"
            btn_bg, btn_fg = "#454545", "#e8e8e8"
            set_tooltip_style({"bg": "#2f3240", "fg": "#f2f2f2"})
        else:
            bg, fg = "#f0f0f0", "#222222"
            input_bg, input_fg = "#ffffff", "#000000"
            tree_bg, tree_fg = "#ffffff", "#000000"
            sel_bg, sel_fg = "#3474b5", "#ffffff"
            tab_bg, tab_fg = "#e8e8e8", "#222222"
            tab_sel_bg, tab_sel_fg = "#ffffff", "#000000"
            btn_bg, btn_fg = "#dcdcdc", "#222222"
            set_tooltip_style({"bg": "#ffffe8", "fg": "#101010"})

        self.root.configure(background=bg)

        style.configure(".", background=bg, foreground=fg)
        style.configure("TFrame", background=bg, foreground=fg)
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("TLabelframe", background=bg, foreground=fg)
        style.configure("TLabelframe.Label", background=bg, foreground=fg)
        style.configure("TButton", background=btn_bg, foreground=btn_fg)
        style.map(
            "TButton",
            background=[("active", sel_bg), ("pressed", sel_bg)],
            foreground=[("disabled", "#888888")],
        )
        style.configure("TCheckbutton", background=bg, foreground=fg)
        style.configure("TRadiobutton", background=bg, foreground=fg)
        style.configure("TEntry", fieldbackground=input_bg, foreground=input_fg, insertcolor=input_fg)
        style.configure("TCombobox", fieldbackground=input_bg, foreground=input_fg, background=btn_bg)
        style.map("TCombobox", fieldbackground=[("readonly", input_bg)])
        style.configure("TNotebook", background=bg)
        style.configure("TNotebook.Tab", background=tab_bg, foreground=tab_fg, padding=[8, 3])
        style.map(
            "TNotebook.Tab",
            background=[("selected", tab_sel_bg)],
            foreground=[("selected", tab_sel_fg)],
        )
        style.configure(
            "Treeview",
            background=tree_bg,
            fieldbackground=tree_bg,
            foreground=tree_fg,
        )
        style.configure("Treeview.Heading", background=btn_bg, foreground=fg)
        style.map(
            "Treeview",
            background=[("selected", sel_bg)],
            foreground=[("selected", sel_fg)],
        )
        style.configure("TPanedwindow", background=bg)
        style.configure("TSeparator", background="#555555" if dark else "#c0c0c0")

        self._theme_toggle_btn.configure(text="\u2600" if dark else "\U0001f319")

        if hasattr(self, "warn_tree"):
            self.warn_tree.tag_configure("error", foreground="#ff8585" if dark else "red")
            self.warn_tree.tag_configure("ok", foreground="#7dce82" if dark else "green")
        if hasattr(self, "broker_info_tree"):
            self.broker_info_tree.tag_configure("top", background="#2d4a2d" if dark else "#eef7ee")
            self.broker_info_tree.tag_configure("negative", foreground="#ff8a80" if dark else "#b71c1c")

        if hasattr(self, "pie_fig"):
            if self.all_transactions:
                self._update_charts()
            else:
                self._show_placeholder()

    def _return_to_pdf_selection(self):
        if not messagebox.askyesno(
            "PDF-Auswahl",
            "Zurück zur PDF-Auswahl wechseln? Die aktuelle Diagrammansicht wird geschlossen.",
        ):
            return
        snap = getattr(self, "_restore_pdf_snapshot", None)
        self.root.destroy()
        new_root = tk.Tk()
        from .gui import DateiAuswahlApp

        DateiAuswahlApp(new_root, restore_snapshot=snap)
        new_root.mainloop()

    def _sort_treeview(self, tree, col, reverse):
        data = [(tree.set(child, col), child) for child in tree.get_children('')]
        if col in ["amount", "kurs", "anzahl", "avg_kurs", "ist_sum", "soll_sum", "diff", "transactions", "positions", "depots", "purchases", "fees", "net", "share"]:
            def get_numeric(val_str):
                if not val_str or val_str == "Nil" or val_str == "Fehlt im PDF" or val_str == "-": return 0.0
                clean_str = val_str.replace('€', '').replace('%', '').strip()
                if col in ["amount", "kurs", "avg_kurs", "ist_sum", "soll_sum", "diff", "purchases", "fees", "net", "share"]:
                    clean_str = clean_str.replace('.', '').replace(',', '.')
                else:
                    clean_str = clean_str.replace(',', '.')
                try: return float(clean_str)
                except ValueError: return 0.0
            data.sort(key=lambda x: get_numeric(x[0]), reverse=reverse)
        else:
            data.sort(key=lambda x: x[0].lower(), reverse=reverse)
            
        for index, item in enumerate(data): tree.move(item[1], '', index)
        tree.heading(col, command=lambda _col=col: self._sort_treeview(tree, _col, not reverse))
    
    def _create_top_left_panel(self, parent):
        title_label = ttk.Label(parent, text="Finanzielle Zusammenfassung", font=("Segoe UI", 14, "bold"))
        title_label.pack(pady=(0, 10))
        
        summary_frame = ttk.LabelFrame(parent, text="Übersicht", padding=10)
        summary_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.summary_labels = {}
        summary_items = [
            ("Transaktionen gesamt:", "total_transactions"),
            ("Summe Käufe:", "total_credits"),
            ("Summe Gebühren:", "total_debits"),
            ("Netto-Betrag:", "net_amount"),
        ]
        
        for label_text, key in summary_items:
            row_frame = ttk.Frame(summary_frame)
            row_frame.pack(fill=tk.X, pady=2)
            ttk.Label(row_frame, text=label_text, font=("Segoe UI", 10)).pack(side=tk.LEFT)
            value_label = ttk.Label(row_frame, text="0,00 €", font=("Segoe UI", 10, "bold"))
            value_label.pack(side=tk.RIGHT)
            self.summary_labels[key] = value_label
        
        file_frame = ttk.LabelFrame(parent, text="Verarbeitete Dateien", padding=10)
        file_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        columns = ("file", "transactions", "amount")
        self.file_tree = ttk.Treeview(file_frame, columns=columns, show="headings", height=5)
        
        self.file_tree.heading("file", text="Dateiname", command=lambda: self._sort_treeview(self.file_tree, "file", False))
        self.file_tree.heading("transactions", text="Transaktionen", command=lambda: self._sort_treeview(self.file_tree, "transactions", False))
        self.file_tree.heading("amount", text="Gesamtbetrag", command=lambda: self._sort_treeview(self.file_tree, "amount", False))
        
        self.file_tree.column("file", width=150)
        self.file_tree.column("transactions", width=80)
        self.file_tree.column("amount", width=100)
        self.file_tree.pack(fill=tk.BOTH, expand=True)

    def _create_bottom_panel(self, parent):
        export_btn = ttk.Button(parent, text="Als CSV exportieren", command=self._export_to_csv)
        export_btn.pack(side=tk.BOTTOM, pady=(8, 0))

        self._create_filter_panel(parent)

        self.details_notebook = ttk.Notebook(parent)
        self.details_notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(5, 0))
        
        # TAB 1: Transaktionsdetails
        tab_all = ttk.Frame(self.details_notebook)
        self.details_notebook.add(tab_all, text="Transaktionsdetails")
        
        trans_columns = ("broker", "position", "anzahl", "kurs", "amount", "date", "depot")
        self.trans_tree = ttk.Treeview(tab_all, columns=trans_columns, show="headings", height=10)
        
        self.trans_tree.heading("broker", text="Broker", command=lambda: self._sort_treeview(self.trans_tree, "broker", False))
        self.trans_tree.heading("position", text="Position", command=lambda: self._sort_treeview(self.trans_tree, "position", False))
        self.trans_tree.heading("anzahl", text="Stückzahl", command=lambda: self._sort_treeview(self.trans_tree, "anzahl", False))
        self.trans_tree.heading("kurs", text="Kurs pro Stück [€]", command=lambda: self._sort_treeview(self.trans_tree, "kurs", False))
        self.trans_tree.heading("amount", text="Endbetrag [€]", command=lambda: self._sort_treeview(self.trans_tree, "amount", False))
        self.trans_tree.heading("date", text="Transaktionsdatum", command=lambda: self._sort_treeview(self.trans_tree, "date", False))
        self.trans_tree.heading("depot", text="Depotnummer", command=lambda: self._sort_treeview(self.trans_tree, "depot", False))
        
        self.trans_tree.column("broker", width=150)
        self.trans_tree.column("position", width=200)
        self.trans_tree.column("anzahl", width=90, anchor="e")
        self.trans_tree.column("kurs", width=130, anchor="e") 
        self.trans_tree.column("amount", width=120, anchor="e")
        self.trans_tree.column("date", width=120)
        self.trans_tree.column("depot", width=120)
        
        trans_scroll = ttk.Scrollbar(tab_all, orient="vertical", command=self.trans_tree.yview)
        self.trans_tree.configure(yscrollcommand=trans_scroll.set)
        self.trans_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        trans_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # TAB 2: Zusammengefasste Positionen
        tab_combined = ttk.Frame(self.details_notebook)
        self.details_notebook.add(tab_combined, text="Zusammengefasste Positionen")
        
        comb_columns = ("position", "anzahl", "amount", "avg_kurs")
        self.combined_tree = ttk.Treeview(tab_combined, columns=comb_columns, show="headings", height=10)
        self.combined_tree.heading("position", text="Position", command=lambda: self._sort_treeview(self.combined_tree, "position", False))
        self.combined_tree.heading("anzahl", text="Gesamtstückzahl", command=lambda: self._sort_treeview(self.combined_tree, "anzahl", False))
        self.combined_tree.heading("amount", text="Investierter Gesamtbetrag [€]", command=lambda: self._sort_treeview(self.combined_tree, "amount", False))
        self.combined_tree.heading("avg_kurs", text="Gewichteter Einstandskurs [€]", command=lambda: self._sort_treeview(self.combined_tree, "avg_kurs", False))
        self.combined_tree.column("position", width=300)
        self.combined_tree.column("anzahl", width=130, anchor="e")
        self.combined_tree.column("amount", width=190, anchor="e")
        self.combined_tree.column("avg_kurs", width=200, anchor="e")
        
        comb_scroll = ttk.Scrollbar(tab_combined, orient="vertical", command=self.combined_tree.yview)
        self.combined_tree.configure(yscrollcommand=comb_scroll.set)
        self.combined_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        comb_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # TAB 3: Warnungen / Validierung
        tab_warn = ttk.Frame(self.details_notebook)
        self.details_notebook.add(tab_warn, text="Warnungen / Validierung")
        
        warn_columns = ("file", "ist_sum", "soll_sum", "diff", "status")
        self.warn_tree = ttk.Treeview(tab_warn, columns=warn_columns, show="headings", height=10)
        self.warn_tree.heading("file", text="Datei", command=lambda: self._sort_treeview(self.warn_tree, "file", False))
        self.warn_tree.heading("ist_sum", text="Ist (Berechnet)", command=lambda: self._sort_treeview(self.warn_tree, "ist_sum", False))
        self.warn_tree.heading("soll_sum", text="Soll (PDF)", command=lambda: self._sort_treeview(self.warn_tree, "soll_sum", False))
        self.warn_tree.heading("diff", text="Differenz", command=lambda: self._sort_treeview(self.warn_tree, "diff", False))
        self.warn_tree.heading("status", text="Status", command=lambda: self._sort_treeview(self.warn_tree, "status", False))
        
        self.warn_tree.column("file", width=250)
        self.warn_tree.column("ist_sum", width=120, anchor="e")
        self.warn_tree.column("soll_sum", width=120, anchor="e")
        self.warn_tree.column("diff", width=120, anchor="e")
        self.warn_tree.column("status", width=100, anchor="center")
        
        self.warn_tree.tag_configure("error", foreground="red")
        self.warn_tree.tag_configure("ok", foreground="green")
        
        warn_scroll = ttk.Scrollbar(tab_warn, orient="vertical", command=self.warn_tree.yview)
        self.warn_tree.configure(yscrollcommand=warn_scroll.set)
        self.warn_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        warn_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        tab_broker = ttk.Frame(self.details_notebook)
        self.details_notebook.add(tab_broker, text="Brokerinformationen")
        self._create_broker_info_panel(tab_broker)

    def _toggle_filter_panel(self):
        self._filter_panel_expanded = not self._filter_panel_expanded
        if self._filter_panel_expanded:
            self._filter_body.pack(fill=tk.X, pady=(2, 0))
            self._filter_toggle_btn.configure(text="▲ Filter einklappen")
        else:
            self._filter_body.pack_forget()
            self._filter_toggle_btn.configure(text="▼ Filter anzeigen")

    def _create_filter_panel(self, parent):
        self._filter_panel_expanded = False
        outer = ttk.Frame(parent)
        outer.pack(side=tk.TOP, fill=tk.X, pady=(0, 2))

        toggle_row = ttk.Frame(outer)
        toggle_row.pack(fill=tk.X)
        self._filter_toggle_btn = ttk.Button(
            toggle_row,
            text="▼ Filter anzeigen",
            command=self._toggle_filter_panel,
        )
        self._filter_toggle_btn.pack(side=tk.LEFT)
        ttk.Button(toggle_row, text="Zurücksetzen", command=self._reset_filters).pack(side=tk.RIGHT)

        self._filter_body = ttk.Frame(outer)
        filter_frame = ttk.LabelFrame(self._filter_body, text="Filter", padding=4)
        filter_frame.pack(fill=tk.X)
        for col in range(4):
            filter_frame.columnconfigure(col, weight=1)

        self.date_filter_mode = tk.StringVar(value="all")
        self.date_start_var = tk.StringVar()
        self.date_end_var = tk.StringVar()
        self.segment_size_var = tk.StringVar(value="10 %")
        self.amount_min_var = tk.StringVar()
        self.amount_max_var = tk.StringVar()
        self.top_x_enabled_var = tk.BooleanVar(value=False)
        self.top_x_var = tk.StringVar(value="5")
        self.quantity_min_var = tk.StringVar()
        self.quantity_max_var = tk.StringVar()

        broker_section = self._create_filter_section(
            filter_frame,
            "Broker",
            "Wähle aus, welche Broker in der Analyse berücksichtigt werden sollen.",
            0,
            0,
        )
        self.broker_dropdown = CheckDropdown(
            broker_section,
            on_change=self._on_filter_changed,
            colors_fn=self._dropdown_popup_theme_colors,
        )

        date_section = self._create_filter_section(
            filter_frame,
            "Datum",
            "Begrenzt die Analyse auf einen Zeitraum (dd.mm.jjjj oder jjjj-mm-tt). "
            "Neben jedem Feld öffnet die Schaltfläche „…“ einen Kalender.",
            0,
            1,
        )
        rad_row = ttk.Frame(date_section)
        rad_row.pack(fill=tk.X)
        ttk.Radiobutton(
            rad_row,
            text="Gesamt",
            variable=self.date_filter_mode,
            value="all",
            command=self._on_date_filter_changed,
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Radiobutton(
            rad_row,
            text="Zeitraum",
            variable=self.date_filter_mode,
            value="range",
            command=self._on_date_filter_changed,
        ).pack(side=tk.LEFT)
        date_inputs = ttk.Frame(date_section)
        date_inputs.pack(fill=tk.X, pady=(2, 0))
        ttk.Label(date_inputs, text="Von").pack(side=tk.LEFT, padx=(0, 2))
        self.date_start_entry = ttk.Entry(date_inputs, textvariable=self.date_start_var, width=9)
        self.date_start_entry.pack(side=tk.LEFT, padx=(0, 2))
        self.date_start_entry.insert(0, "")
        self.date_start_cal_btn = ttk.Button(
            date_inputs,
            text="\u2026",
            width=2,
            command=lambda: self._open_date_picker(self.date_start_var),
        )
        self.date_start_cal_btn.pack(side=tk.LEFT)
        InfoTooltip(self.date_start_cal_btn, "Kalender öffnen (dd.mm.jjjj)")
        ttk.Label(date_inputs, text="\u2013").pack(side=tk.LEFT, padx=4)
        ttk.Label(date_inputs, text="Bis").pack(side=tk.LEFT, padx=(0, 2))
        self.date_end_entry = ttk.Entry(date_inputs, textvariable=self.date_end_var, width=9)
        self.date_end_entry.pack(side=tk.LEFT, padx=(0, 2))
        self.date_end_entry.insert(0, "")
        self.date_end_cal_btn = ttk.Button(
            date_inputs,
            text="\u2026",
            width=2,
            command=lambda: self._open_date_picker(self.date_end_var),
        )
        self.date_end_cal_btn.pack(side=tk.LEFT)
        InfoTooltip(self.date_end_cal_btn, "Kalender öffnen (dd.mm.jjjj)")
        self.date_start_var.trace_add("write", lambda *_args: self._on_filter_changed())
        self.date_end_var.trace_add("write", lambda *_args: self._on_filter_changed())
        self._on_date_filter_changed(refresh=False)

        position_section = self._create_filter_section(
            filter_frame,
            "Position",
            "Wähle Wertpapiere über die Liste. Die Analyse aktualisiert sich, sobald du die Liste schließt.",
            0,
            2,
        )
        self.position_dropdown = CheckDropdown(
            position_section,
            on_change=self._on_filter_changed,
            colors_fn=self._dropdown_popup_theme_colors,
        )

        segment_section = self._create_filter_section(
            filter_frame,
            "Segmentgröße",
            "Legt fest, wie das Kreisdiagramm gruppiert wird. 0 % = eine Scheibe pro Position (keine Prozent-Buckets).",
            0,
            3,
        )
        self.segment_size_box = ttk.Combobox(
            segment_section,
            textvariable=self.segment_size_var,
            values=["0 %", "5 %", "10 %", "20 %", "25 %", "50 %"],
            state="readonly",
            width=9,
        )
        self.segment_size_box.pack(fill=tk.X)
        self.segment_size_box.bind("<<ComboboxSelected>>", self._on_segment_size_changed)

        amount_section = self._create_filter_section(
            filter_frame,
            "Betrag",
            "Filtert Positionen nach ihrer Investitionshöhe.",
            1,
            0,
        )
        self._create_range_inputs(amount_section, self.amount_min_var, self.amount_max_var, "Mindestbetrag", "Maximalbetrag")
        top_frame = ttk.Frame(amount_section)
        top_frame.pack(fill=tk.X, pady=(2, 0))
        top_left = ttk.Frame(top_frame)
        top_left.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.top_x_checkbox = ttk.Checkbutton(
            top_left,
            text="Top-X",
            variable=self.top_x_enabled_var,
            command=self._on_top_x_toggle,
        )
        self.top_x_checkbox.pack(side=tk.LEFT)
        top_x_info = ttk.Label(top_left, text="i", anchor="center", width=2, relief="groove")
        top_x_info.pack(side=tk.LEFT, padx=(4, 0))
        InfoTooltip(
            top_x_info,
            "Top-X größte Positionen: nur bei Segmentgröße 0 %. "
            "Beim Aktivieren wird die Segmentgröße automatisch auf 0 % gesetzt.",
        )
        self.top_x_box = ttk.Combobox(top_frame, textvariable=self.top_x_var, values=["5", "10", "20"], state="readonly", width=4)
        self.top_x_box.pack(side=tk.RIGHT)
        self.top_x_box.bind("<<ComboboxSelected>>", lambda _event: self._on_filter_changed())
        self._sync_top_x_widgets_state()

        quantity_section = self._create_filter_section(
            filter_frame,
            "Stückzahl",
            "Zeigt nur Positionen, deren Stückzahl im angegebenen Bereich liegt.",
            1,
            1,
        )
        self._create_range_inputs(quantity_section, self.quantity_min_var, self.quantity_max_var, "Minimale Stückzahl", "Maximale Stückzahl")

        depot_section = self._create_filter_section(
            filter_frame,
            "Depotnummer",
            "Wähle Depots über die Liste. Die Analyse aktualisiert sich, sobald du die Liste schließt.",
            1,
            2,
            columnspan=2,
        )
        self.depot_dropdown = CheckDropdown(
            depot_section,
            on_change=self._on_filter_changed,
            colors_fn=self._dropdown_popup_theme_colors,
        )

    def _create_filter_section(self, parent, title, info_text, row, column, columnspan=1):
        section = ttk.LabelFrame(parent, padding=3)
        section.grid(row=row, column=column, columnspan=columnspan, sticky="nsew", padx=2, pady=2)
        header = ttk.Frame(section)
        header.pack(fill=tk.X, pady=(0, 2))
        ttk.Label(header, text=title, font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT)
        info = ttk.Label(header, text="i", anchor="center", width=2, relief="groove")
        info.pack(side=tk.RIGHT)
        InfoTooltip(info, info_text)
        return section

    def _create_range_inputs(self, parent, min_var, max_var, min_placeholder, max_placeholder):
        row = ttk.Frame(parent)
        row.pack(fill=tk.X)
        min_entry = ttk.Entry(row, textvariable=min_var, width=12)
        min_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        max_entry = ttk.Entry(row, textvariable=max_var, width=12)
        max_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        min_entry.insert(0, "")
        max_entry.insert(0, "")
        ttk.Label(parent, text=f"{min_placeholder} / {max_placeholder}", font=("Segoe UI", 7)).pack(anchor="w", pady=(0, 0))
        min_var.trace_add("write", lambda *_args: self._on_filter_changed())
        max_var.trace_add("write", lambda *_args: self._on_filter_changed())

    def _on_date_filter_changed(self, refresh=True):
        state = "normal" if self.date_filter_mode.get() == "range" else "disabled"
        if hasattr(self, 'date_start_entry'):
            self.date_start_entry.config(state=state)
            self.date_end_entry.config(state=state)
        if hasattr(self, 'date_start_cal_btn'):
            self.date_start_cal_btn.config(state=state)
            self.date_end_cal_btn.config(state=state)
        if refresh:
            self._on_filter_changed()

    def _cancel_filter_refresh_debounce(self):
        if self._filter_refresh_job is not None:
            self.root.after_cancel(self._filter_refresh_job)
            self._filter_refresh_job = None

    def _on_filter_changed(self):
        if not hasattr(self, 'details_notebook'):
            return
        self._cancel_filter_refresh_debounce()
        self._filter_refresh_job = self.root.after(100, self._apply_debounced_filter_refresh)

    def _apply_debounced_filter_refresh(self):
        self._filter_refresh_job = None
        self._refresh_filtered_views()

    def _reset_filters(self):
        self._cancel_filter_refresh_debounce()
        if hasattr(self, 'broker_dropdown'):
            self.broker_dropdown.select_all()
        if hasattr(self, 'position_dropdown'):
            self.position_dropdown.apply_filter("")
            self.position_dropdown.select_all()
        if hasattr(self, 'depot_dropdown'):
            self.depot_dropdown.apply_filter("")
            self.depot_dropdown.select_all()
        self.date_filter_mode.set("all")
        self.date_start_var.set("")
        self.date_end_var.set("")
        self.segment_size_var.set("10 %")
        self.amount_min_var.set("")
        self.amount_max_var.set("")
        self.top_x_enabled_var.set(False)
        self.top_x_var.set("5")
        self.quantity_min_var.set("")
        self.quantity_max_var.set("")
        self._on_date_filter_changed(refresh=False)
        self._sync_top_x_widgets_state()
        self._refresh_filtered_views()

    def _update_filter_options(self):
        if not hasattr(self, 'broker_dropdown'):
            return

        brokers = sorted({transaction.get('broker', 'Unbekannt') for transaction in self.all_transactions})
        depots = sorted({
            str(transaction.get('depot', 'Nil'))
            for transaction in self.all_transactions
            if transaction.get('depot') not in [None, "", "Nil"]
        }, key=natural_sort_key)
        positions = sorted({
            clean_csv(transaction.get('position', 'Unbekannt'))
            for transaction in self.all_transactions
            if clean_csv(transaction.get('position', 'Unbekannt')) != "Nil"
        }, key=natural_sort_key)

        self.broker_dropdown.set_items(brokers, preserve=True)
        self.position_dropdown.set_items(positions, preserve=True)
        self.position_dropdown.apply_filter("")
        self.depot_dropdown.set_items(depots, preserve=True)
        self.depot_dropdown.apply_filter("")

    def _parse_filter_float(self, text):
        text = str(text or "").strip()
        if not text:
            return None
        try:
            return float(text.replace('.', '').replace(',', '.'))
        except ValueError:
            return None

    def _parse_filter_date(self, text):
        text = str(text or "").strip()
        if not text:
            return None
        for date_format in ("%d.%m.%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, date_format)
            except ValueError:
                continue
        return None

    def _open_date_picker(self, string_var):
        try:
            from tkcalendar import Calendar
        except ImportError:
            messagebox.showinfo(
                "Kalender",
                "Für den Kalender wird das Paket tkcalendar benötigt.\n"
                "Installation im Projektordner: pip install tkcalendar",
            )
            return

        top = tk.Toplevel(self.root)
        top.title("Datum wählen")
        top.transient(self.root)
        top.grab_set()

        parsed = self._parse_filter_date(string_var.get())
        if parsed:
            cal = Calendar(
                top,
                selectmode="day",
                year=parsed.year,
                month=parsed.month,
                day=parsed.day,
                date_pattern="dd.mm.yyyy",
            )
        else:
            now = datetime.now()
            cal = Calendar(
                top,
                selectmode="day",
                year=now.year,
                month=now.month,
                day=now.day,
                date_pattern="dd.mm.yyyy",
            )
        cal.pack(padx=10, pady=10)

        bar = ttk.Frame(top)
        bar.pack(pady=(0, 10))

        def apply():
            string_var.set(cal.get_date())
            top.destroy()

        ttk.Button(bar, text="Übernehmen", command=apply).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Abbrechen", command=top.destroy).pack(side=tk.LEFT, padx=4)

    def _get_selected_brokers(self):
        if not hasattr(self, 'broker_dropdown'):
            return None
        return self.broker_dropdown.get_selected()

    def _get_segment_size(self):
        raw_value = str(self.segment_size_var.get() if hasattr(self, 'segment_size_var') else "10 %")
        try:
            return int(raw_value.replace('%', '').strip())
        except ValueError:
            return 10

    def _on_segment_size_changed(self, _event=None):
        if self._get_segment_size() != 0:
            self.top_x_enabled_var.set(False)
        self._sync_top_x_widgets_state()
        self._on_filter_changed()

    def _on_top_x_toggle(self):
        if self.top_x_enabled_var.get():
            self.segment_size_var.set("0 %")
        self._sync_top_x_widgets_state()
        self._on_filter_changed()

    def _sync_top_x_widgets_state(self):
        if not hasattr(self, 'top_x_box'):
            return
        seg_zero = self._get_segment_size() == 0
        if self.top_x_enabled_var.get() and seg_zero:
            self.top_x_box.configure(state='readonly')
        else:
            self.top_x_box.configure(state='disabled')

    def _get_pie_nav_default_text(self):
        if self._get_segment_size() == 0:
            return "Eine Position pro Segment (Klick fuer Detail / Filter)"
        return f"Klicke auf einen {self._get_segment_size()}%-Bereich, um seine Aktien zu sehen"

    def _get_active_filter_kwargs(self):
        date_start = date_end = None
        if hasattr(self, 'date_filter_mode') and self.date_filter_mode.get() == "range":
            date_start = self._parse_filter_date(self.date_start_var.get())
            date_end = self._parse_filter_date(self.date_end_var.get())

        top_x = None
        if (
            hasattr(self, 'top_x_enabled_var')
            and self.top_x_enabled_var.get()
            and self._get_segment_size() == 0
        ):
            try:
                top_x = int(self.top_x_var.get())
            except ValueError:
                top_x = None

        selected_positions = self.position_dropdown.get_selected() if hasattr(self, 'position_dropdown') else None
        selected_depots = self.depot_dropdown.get_selected() if hasattr(self, 'depot_dropdown') else None

        return {
            'selected_broker': self._get_selected_brokers(),
            'selected_positions': selected_positions,
            'selected_depots': selected_depots,
            'date_start': date_start,
            'date_end': date_end,
            'amount_min': self._parse_filter_float(self.amount_min_var.get()) if hasattr(self, 'amount_min_var') else None,
            'amount_max': self._parse_filter_float(self.amount_max_var.get()) if hasattr(self, 'amount_max_var') else None,
            'quantity_min': self._parse_filter_float(self.quantity_min_var.get()) if hasattr(self, 'quantity_min_var') else None,
            'quantity_max': self._parse_filter_float(self.quantity_max_var.get()) if hasattr(self, 'quantity_max_var') else None,
            'top_x': top_x,
        }

    def _create_top_right_panel(self, parent):
        title_label = ttk.Label(parent, text="Datenvisualisierung", font=("Segoe UI", 14, "bold"))
        title_label.pack(pady=(0, 10))
        self.right_notebook = ttk.Notebook(parent)
        self.right_notebook.pack(fill=tk.BOTH, expand=True)
        self.pie_frame = ttk.Frame(self.right_notebook)
        self.right_notebook.add(self.pie_frame, text="Kuchendiagramm (Positionen)")
        self.line_frame = ttk.Frame(self.right_notebook)
        self.right_notebook.add(self.line_frame, text="Zeitverlauf (Portfolio)")
        self._create_empty_charts()
    
    def _create_empty_charts(self):
        self.pie_toolbar = ttk.Frame(self.pie_frame)
        self.pie_toolbar.pack(fill=tk.X, padx=5, pady=(0, 5))
        self.pie_nav_var = tk.StringVar(value=self._get_pie_nav_default_text())
        self.pie_nav_label = ttk.Label(self.pie_toolbar, textvariable=self.pie_nav_var, font=("Segoe UI", 9, "bold"))
        self.pie_nav_label.pack(side=tk.LEFT)
        self.pie_reset_button = ttk.Button(
            self.pie_toolbar,
            text="Ansicht zuruecksetzen",
            command=self._reset_pie_view,
        )
        self.pie_reset_button.pack(side=tk.RIGHT)

        self.pie_fig = Figure(figsize=(6, 4))
        self.pie_canvas = FigureCanvasTkAgg(self.pie_fig, master=self.pie_frame)
        self.pie_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.pie_canvas.mpl_connect("motion_notify_event", self._on_pie_motion)
        self.pie_canvas.mpl_connect("figure_leave_event", self._on_pie_leave)
        self.pie_canvas.mpl_connect("button_press_event", self._on_pie_press)
        self.pie_canvas.mpl_connect("button_release_event", self._on_pie_release)
        self.pie_canvas.mpl_connect("scroll_event", self._on_pie_scroll)
        
        self.line_fig = Figure(figsize=(6, 4))
        self.line_canvas = FigureCanvasTkAgg(self.line_fig, master=self.line_frame)
        self.line_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self._show_placeholder()

    def _create_broker_info_panel(self, parent):
        self.broker_info_cards = {}
        self._broker_company_info = {}
        self._selected_broker_info_item = None
        self.broker_company_vars = {
            "address": tk.StringVar(value="-"),
            "phone": tk.StringVar(value="-"),
            "fax": tk.StringVar(value="-"),
            "email": tk.StringVar(value="-"),
            "website": tk.StringVar(value="-"),
        }

        hover_frame = ttk.LabelFrame(parent, text="Firmendaten zur ausgewählten Brokerzeile", padding=(10, 8))
        hover_frame.pack(fill=tk.X, padx=8, pady=(8, 4))

        hover_grid = ttk.Frame(hover_frame)
        hover_grid.pack(fill=tk.X)
        hover_items = [
            ("Anschrift", "address"),
            ("Telefon", "phone"),
            ("Fax", "fax"),
            ("E-Mail", "email"),
            ("Webseite", "website"),
        ]
        for index, (label, key) in enumerate(hover_items):
            row, col = divmod(index, 2)
            ttk.Label(hover_grid, text=f"{label}:", font=("Segoe UI", 9, "bold")).grid(row=row, column=col * 2, sticky="w", padx=(0, 5), pady=2)
            ttk.Label(hover_grid, textvariable=self.broker_company_vars[key]).grid(row=row, column=col * 2 + 1, sticky="w", padx=(0, 18), pady=2)
        hover_grid.columnconfigure(1, weight=1)
        hover_grid.columnconfigure(3, weight=1)

        cards_frame = ttk.Frame(parent, padding=(8, 4, 8, 4))
        cards_frame.pack(fill=tk.X)

        card_specs = [
            ("broker_count", "Broker", "0"),
            ("top_broker", "Größter Broker", "-"),
            ("purchase_total", "Summe Käufe", "0,00 €"),
            ("fee_total", "Summe Gebühren", "0,00 €"),
        ]

        for index, (key, title, value) in enumerate(card_specs):
            card = ttk.LabelFrame(cards_frame, text=title, padding=(10, 8))
            card.grid(row=0, column=index, sticky="nsew", padx=(0, 8 if index < len(card_specs) - 1 else 0))
            cards_frame.columnconfigure(index, weight=1)
            value_label = ttk.Label(card, text=value, font=("Segoe UI", 11, "bold"))
            value_label.pack(anchor="w")
            self.broker_info_cards[key] = value_label

        table_frame = ttk.LabelFrame(parent, text="Brokerübersicht", padding=8)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))

        columns = ("broker", "transactions", "positions", "depots", "purchases", "fees", "net", "share")
        self.broker_info_tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=8)

        headings = {
            "broker": "Broker",
            "transactions": "Transaktionen",
            "positions": "Positionen",
            "depots": "Depots",
            "purchases": "Käufe [€]",
            "fees": "Gebühren [€]",
            "net": "Netto [€]",
            "share": "Anteil Käufe",
        }
        for col, text in headings.items():
            self.broker_info_tree.heading(col, text=text, command=lambda _col=col: self._sort_treeview(self.broker_info_tree, _col, False))

        self.broker_info_tree.column("broker", width=150)
        self.broker_info_tree.column("transactions", width=95, anchor="e")
        self.broker_info_tree.column("positions", width=80, anchor="e")
        self.broker_info_tree.column("depots", width=70, anchor="e")
        self.broker_info_tree.column("purchases", width=110, anchor="e")
        self.broker_info_tree.column("fees", width=105, anchor="e")
        self.broker_info_tree.column("net", width=105, anchor="e")
        self.broker_info_tree.column("share", width=90, anchor="e")
        self.broker_info_tree.tag_configure("top", background="#eef7ee")
        self.broker_info_tree.tag_configure("negative", foreground="#b71c1c")

        broker_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.broker_info_tree.yview)
        self.broker_info_tree.configure(yscrollcommand=broker_scroll.set)
        self.broker_info_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        broker_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.broker_info_tree.bind("<<TreeviewSelect>>", self._on_broker_info_select)
    
    def _show_placeholder(self):
        # Sicherstellen, dass Chart-Attribute existieren
        if not hasattr(self, 'pie_fig') or not hasattr(self, 'line_fig'):
            return

        self._pie_hover_entries = []
        self._pie_hover_annotation = None
        self._pie_hover_axes = None
        self._active_pie_wedge = None
        self._pie_drag_start = None
        self._pie_drag_xlim = None
        self._pie_drag_ylim = None
        self._pie_default_xlim = None
        self._pie_default_ylim = None
        self._pie_selected_bucket = None
        self._pie_selected_position = None
        self._pie_chart_data = {}
        self._pie_bucket_data = []
        self._pie_total_amount = 1.0
        self._pie_active_entry = None
        self._pie_last_hover_xy = None
        self._cancel_pie_animation()
        if hasattr(self, 'pie_nav_var'):
            self.pie_nav_var.set(self._get_pie_nav_default_text())
        self._clear_broker_info_panel()

        placeholder_text = "Keine Daten vorhanden\n\nLade PDFs, um die Visualisierung zu sehen"
        ct = self._chart_theme()
        for fig, canvas in [(self.pie_fig, self.pie_canvas), (self.line_fig, self.line_canvas)]:
            fig.clear()
            fig.patch.set_facecolor(ct["fig_face"])
            ax = fig.add_subplot(111)
            ax.set_facecolor(ct["ax_face"])
            ax.text(0.5, 0.5, placeholder_text, ha="center", va="center", fontsize=12, color=ct["placeholder"])
            ax.set_axis_off()
            canvas.draw()

    def _clear_broker_info_panel(self):
        if not hasattr(self, 'broker_info_tree'):
            return

        defaults = {
            "broker_count": "0",
            "top_broker": "-",
            "purchase_total": "0,00 €",
            "fee_total": "0,00 €",
        }
        for key, value in defaults.items():
            if key in self.broker_info_cards:
                self.broker_info_cards[key].config(text=value)

        for item in self.broker_info_tree.get_children():
            self.broker_info_tree.delete(item)
        self._broker_company_info = {}
        self._clear_selected_broker_info()

    def _clear_selected_broker_info(self):
        if not hasattr(self, 'broker_company_vars'):
            return

        self._selected_broker_info_item = None
        for value in self.broker_company_vars.values():
            value.set("-")

    def _on_broker_info_select(self, _event=None):
        if not hasattr(self, 'broker_info_tree'):
            return

        selection = self.broker_info_tree.selection()
        if not selection:
            self._clear_selected_broker_info()
            return
        item_id = selection[0]
        if item_id == self._selected_broker_info_item:
            return

        values = self.broker_info_tree.item(item_id, "values")
        if not values:
            self._clear_selected_broker_info()
            return

        self._selected_broker_info_item = item_id
        broker_name = values[0]
        company_info = self._broker_company_info.get(broker_name, {})
        self.broker_company_vars["address"].set(company_info.get("company_address") or "-")
        self.broker_company_vars["phone"].set(company_info.get("company_phone") or "-")
        self.broker_company_vars["fax"].set(company_info.get("company_fax") or "-")
        self.broker_company_vars["email"].set(company_info.get("company_email") or "-")
        self.broker_company_vars["website"].set(company_info.get("company_website") or "-")

    def _get_filtered_transactions(self):
        """Kombiniert Brokerfilter und aktive Kreisdiagramm-Auswahl."""
        selected_bucket = getattr(self, '_pie_selected_bucket', None)
        filter_kwargs = self._get_active_filter_kwargs()
        return filter_transactions(
            self.all_transactions,
            **filter_kwargs,
            selected_position=getattr(self, '_pie_selected_position', None),
            bucket_positions=self._get_bucket_positions(selected_bucket) if selected_bucket is not None else None,
        )
            
    def _get_broker_filtered_transactions(self):
        return filter_transactions(self.all_transactions, **self._get_active_filter_kwargs())

    def _refresh_display(self):
        # Sicherstellen, dass alle Widgets erstellt wurden
        if not hasattr(self, 'broker_dropdown'):
            return

        if not self.all_transactions: return
        self._cancel_filter_refresh_debounce()
        self._update_filter_options()
        self._refresh_filtered_views()

    def _refresh_filtered_views(self):
        """Aktualisiert alle sichtbaren Bereiche nach Filter- oder Datenaenderungen."""
        self._clear_pie_position_filter(redraw=False, clear_bucket=True)
        self._update_summary()
        self._update_file_tree()
        self._update_transaction_tree()
        self._update_charts()
    
    def _update_summary(self):
        # Sicherstellen, dass summary_labels existiert
        if not hasattr(self, 'summary_labels'):
            return

        active_transactions = self._get_filtered_transactions()
        summary = summarize_transactions(active_transactions)
        
        self.summary_labels["total_transactions"].config(text=str(summary['total']))
        self.summary_labels["total_credits"].config(text=self._format_currency(summary['purchases']))
        self.summary_labels["total_debits"].config(text=self._format_currency(summary['fees']))
        self.summary_labels["net_amount"].config(text=self._format_currency(summary['net']))
        self.summary_labels["net_amount"].config(foreground="green" if summary['net'] >= 0 else "red")
    
    def _update_file_tree(self):
        # Sicherstellen, dass file_tree existiert
        if not hasattr(self, 'file_tree'):
            return

        active_transactions = self._get_filtered_transactions()
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)
        file_data = group_transactions_by_file(active_transactions)
            
        for filename, data in sorted(file_data.items(), key=lambda item: natural_sort_key(item[0])):
            self.file_tree.insert("", tk.END, values=(filename, data['count'], self._format_currency(data['amount'])))
    
    def _update_transaction_tree(self):
        # Sicherstellen, dass alle Widgets erstellt wurden
        if not hasattr(self, 'trans_tree') or not hasattr(self, 'combined_tree') or not hasattr(self, 'warn_tree'):
            return

        active_transactions = self._get_filtered_transactions()
        for item in self.trans_tree.get_children(): self.trans_tree.delete(item)
        
        for t in active_transactions:
            broker = clean_csv(t.get('broker', ''))[:30]
            position = t.get('position', t.get('date', 'Nil'))
            
            kurs_val = t.get('kurs')
            kurs_str = self._format_currency(kurs_val) if kurs_val is not None else ""
            
            anzahl_val = t.get('anzahl')
            anzahl_str = (f"{int(anzahl_val)}" if anzahl_val.is_integer() else f"{anzahl_val}".replace('.', ',')) if anzahl_val is not None else ""
            
            amount_val = t.get('amount')
            amount_str = self._format_currency(amount_val) if amount_val is not None else ""
            
            trans_date = clean_csv(t.get('date', ''))
            depot = clean_csv(t.get('depot', ''))
            
            self.trans_tree.insert("", tk.END, values=(broker, position, anzahl_str, kurs_str, amount_str, trans_date, depot))
            
        for item in self.combined_tree.get_children(): self.combined_tree.delete(item)
        combined_data = combine_positions(active_transactions)
            
        for pos, data in sorted(combined_data.items()):
            anzahl_val = data['anzahl']
            anzahl_str = (f"{int(anzahl_val)}" if anzahl_val.is_integer() else f"{anzahl_val}".replace('.', ',')) if anzahl_val > 0 else ""
            avg_kurs = (data['amount'] / anzahl_val) if anzahl_val > 0 else None
            avg_kurs_str = self._format_currency(avg_kurs) if avg_kurs is not None else ""
            self.combined_tree.insert("", tk.END, values=(pos, anzahl_str, self._format_currency(data['amount']), avg_kurs_str))
            
        for item in self.warn_tree.get_children(): self.warn_tree.delete(item)
        file_sums = calculate_file_validation_sums(active_transactions)

        for filename, sums in sorted(file_sums.items(), key=lambda item: natural_sort_key(item[0])):
            ist_val = sums['ist']
            soll_val = sums['soll']
            
            if soll_val is None:
                soll_str, diff_str, status, tag = "Fehlt im PDF", "-", "Unbekannt", ""
            else:
                soll_str = self._format_currency(soll_val)
                diff = abs(ist_val - soll_val)
                diff_str = self._format_currency(diff)
                if diff < 0.02:
                    status, tag, diff_str = "OK", "ok", "0,00 €"
                else:
                    status, tag = "FEHLER", "error"
            
            item = self.warn_tree.insert("", tk.END, values=(filename, self._format_currency(ist_val), soll_str, diff_str, status))
            if tag: self.warn_tree.item(item, tags=(tag,))

    def _build_position_chart_data(self, transactions):
        """Verdichtet Transaktionen zu Positionssummen fuer das Kreisdiagramm."""
        return build_position_chart_data(transactions)

    def _build_pie_bucket_data(self, position_data):
        """Fasst Positionen in groessere Prozentbereiche fuer bessere Lesbarkeit zusammen."""
        return build_pie_bucket_data(position_data, segment_size=self._get_segment_size())

    def _get_bucket_positions(self, bucket_index):
        return get_bucket_positions(getattr(self, '_pie_bucket_data', []), bucket_index)

    def _get_position_color_meta(self, position):
        if self._pie_selected_bucket is not None:
            positions = self._get_bucket_positions(self._pie_selected_bucket)
        else:
            positions = list(getattr(self, '_pie_chart_data', {}).keys())

        try:
            color_index = positions.index(position)
        except ValueError:
            color_index = 0

        return color_index, max(len(positions), 1)

    def _reset_pie_view(self):
        if self._pie_selected_position:
            self._clear_pie_position_filter(redraw=True, animate=True, clear_bucket=False)
            return

        if self._pie_selected_bucket is not None:
            self._clear_pie_position_filter(redraw=True, animate=True, clear_bucket=True)
            return

        if self._pie_hover_axes is None or self._pie_default_xlim is None or self._pie_default_ylim is None:
            return
        self._pie_hover_axes.set_xlim(self._pie_default_xlim)
        self._pie_hover_axes.set_ylim(self._pie_default_ylim)
        self._pie_drag_start = None
        self._pie_drag_xlim = None
        self._pie_drag_ylim = None
        self._hide_pie_annotation()
        self.pie_canvas.draw_idle()

    def _cancel_pie_animation(self):
        if getattr(self, '_pie_animation_after_id', None) is not None:
            try:
                self.root.after_cancel(self._pie_animation_after_id)
            except tk.TclError:
                pass
        self._pie_animation_after_id = None
        self._pie_animation_state = None
        self._pie_active_entry = None
        self._pie_last_hover_xy = None

    def _clear_pie_position_filter(self, redraw=True, animate=False, clear_bucket=False):
        if not getattr(self, '_pie_selected_position', None) and (not clear_bucket or self._pie_selected_bucket is None):
            return

        previous_position = self._pie_selected_position
        previous_bucket = self._pie_selected_bucket
        self._pie_selected_position = None
        if clear_bucket:
            self._pie_selected_bucket = None
        self._hide_pie_annotation()

        if animate and redraw:
            if previous_position:
                self._animate_pie_focus(previous_position, expand=False, target_type="position")
            elif previous_bucket is not None:
                self._animate_pie_focus(previous_bucket, expand=False, target_type="bucket")
        elif redraw:
            self._update_pie_chart()

        self._update_summary()
        self._update_file_tree()
        self._update_transaction_tree()

    def _apply_pie_bucket_filter(self, bucket_index):
        if bucket_index is None or bucket_index == self._pie_selected_bucket:
            return

        self._pie_selected_position = None
        self._hide_pie_annotation()

        def show_bucket_positions():
            self._pie_selected_bucket = bucket_index
            self._update_pie_chart()
            self._update_summary()
            self._update_file_tree()
            self._update_transaction_tree()

        self._animate_pie_focus(bucket_index, expand=True, target_type="bucket", on_complete=show_bucket_positions)

    def _apply_pie_position_filter(self, position):
        if not position or position == self._pie_selected_position:
            return

        self._hide_pie_annotation()

        def show_position():
            self._pie_selected_position = position
            self._update_pie_chart()
            self._update_summary()
            self._update_file_tree()
            self._update_transaction_tree()

        self._animate_pie_focus(position, expand=True, target_type="position", on_complete=show_position)

    def _ensure_pie_hover_annotation(self, ax):
        self._pie_hover_axes = ax
        cab = self._chart_annotation_colors()
        self._pie_hover_annotation = ax.annotate(
            "",
            xy=(0, 0),
            xytext=(15, 15),
            textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.4", fc=cab["face"], ec=cab["edge"], alpha=0.95),
            arrowprops=dict(arrowstyle="->", color=cab["arrow"]),
        )
        self._pie_hover_annotation.set_fontweight("bold")
        self._pie_hover_annotation.set_fontsize(10)
        self._pie_hover_annotation.set_color(self._chart_theme()["tick"])
        self._pie_hover_annotation.set_visible(False)

    def _hide_pie_annotation(self):
        needs_draw = False
        if self._pie_hover_annotation is not None and self._pie_hover_annotation.get_visible():
            self._pie_hover_annotation.set_visible(False)
            needs_draw = True

        if self._active_pie_wedge is not None:
            self._active_pie_wedge.set_alpha(1.0)
            self._active_pie_wedge = None
            needs_draw = True

        self._pie_active_entry = None
        self._pie_last_hover_xy = None
        if needs_draw:
            self.pie_canvas.draw_idle()

    def _set_active_pie_wedge(self, wedge):
        if self._active_pie_wedge is wedge:
            return

        if self._active_pie_wedge is not None:
            self._active_pie_wedge.set_alpha(1.0)

        self._active_pie_wedge = wedge
        if self._active_pie_wedge is not None:
            self._active_pie_wedge.set_alpha(0.8)

    def _on_pie_press(self, event):
        if event.button == 3:
            self._reset_pie_view()
            return

        if event.inaxes != self._pie_hover_axes or event.button != 1:
            return
        if event.xdata is None or event.ydata is None:
            return

        pressed_entry = None
        for entry in self._pie_hover_entries:
            contains, _ = entry['wedge'].contains(event)
            if contains:
                pressed_entry = entry
                break

        self._pie_press_event = {
            'x': event.x,
            'y': event.y,
            'entry': pressed_entry,
        }
        self._pie_drag_start = (event.x, event.y)
        self._pie_drag_xlim = self._pie_hover_axes.get_xlim()
        self._pie_drag_ylim = self._pie_hover_axes.get_ylim()
        self._hide_pie_annotation()

    def _on_pie_release(self, event):
        """Unterscheidet Klicks zum Filtern von Drag-Bewegungen im Diagramm."""
        press_event = self._pie_press_event
        self._pie_drag_start = None
        self._pie_drag_xlim = None
        self._pie_drag_ylim = None
        self._pie_press_event = None

        if event.button != 1 or not press_event or not press_event['entry']:
            return

        moved = abs(event.x - press_event['x']) + abs(event.y - press_event['y'])
        if moved <= 6:
            entry = press_event['entry']
            if entry.get('type') == 'bucket':
                self._apply_pie_bucket_filter(entry.get('bucket_index'))
            elif entry.get('type') == 'position':
                self._apply_pie_position_filter(entry['label'])

    def _on_pie_scroll(self, event):
        if event.inaxes != self._pie_hover_axes:
            return
        if event.xdata is None or event.ydata is None:
            return

        scale_factor = 0.85 if event.button == 'up' else 1.15
        current_xlim = self._pie_hover_axes.get_xlim()
        current_ylim = self._pie_hover_axes.get_ylim()

        new_xlim = (
            event.xdata - (event.xdata - current_xlim[0]) * scale_factor,
            event.xdata + (current_xlim[1] - event.xdata) * scale_factor,
        )
        new_ylim = (
            event.ydata - (event.ydata - current_ylim[0]) * scale_factor,
            event.ydata + (current_ylim[1] - event.ydata) * scale_factor,
        )

        self._pie_hover_axes.set_xlim(new_xlim)
        self._pie_hover_axes.set_ylim(new_ylim)
        self._hide_pie_annotation()
        self.pie_canvas.draw_idle()

    def _on_pie_motion(self, event):
        if self._pie_drag_start is not None:
            if event.inaxes != self._pie_hover_axes:
                return

            axes_bbox = self._pie_hover_axes.bbox
            if axes_bbox.width <= 0 or axes_bbox.height <= 0:
                return

            x_span = self._pie_drag_xlim[1] - self._pie_drag_xlim[0]
            y_span = self._pie_drag_ylim[1] - self._pie_drag_ylim[0]
            delta_x = (event.x - self._pie_drag_start[0]) * x_span / axes_bbox.width
            delta_y = (event.y - self._pie_drag_start[1]) * y_span / axes_bbox.height
            self._pie_hover_axes.set_xlim(
                self._pie_drag_xlim[0] - delta_x,
                self._pie_drag_xlim[1] - delta_x,
            )
            self._pie_hover_axes.set_ylim(
                self._pie_drag_ylim[0] - delta_y,
                self._pie_drag_ylim[1] - delta_y,
            )
            self.pie_canvas.draw_idle()
            return

        if not self._pie_hover_entries or self._pie_hover_annotation is None:
            return

        if event.inaxes != self._pie_hover_axes:
            self._hide_pie_annotation()
            return

        for entry in self._pie_hover_entries:
            contains, _ = entry['wedge'].contains(event)
            if not contains:
                continue

            if entry.get('type') == 'bucket':
                bucket_info = entry['data']
                tooltip = self._format_pie_tooltip(entry['label'], [
                    f"Anteil am Portfolio: {entry['percent']:.1f}%",
                    f"Aktien: {bucket_info['count']}",
                    f"Investierter Betrag: {self._format_currency(bucket_info['amount'])}",
                ])
            else:
                position_info = entry['data']
                if position_info['kurs_basis'] > 0:
                    avg_kurs = self._format_currency(position_info['kurs_gewicht'] / position_info['kurs_basis'])
                elif position_info['kurs_fallback'] is not None:
                    avg_kurs = self._format_currency(position_info['kurs_fallback'])
                else:
                    avg_kurs = "Nicht verfuegbar"

                tooltip = self._format_pie_tooltip(entry['label'], [
                    f"Anteil am Portfolio: {entry['percent']:.1f}%",
                    f"Stückzahl: {self._format_quantity(position_info['anzahl'])}",
                    f"Durchschnittlicher Einstandskurs: {avg_kurs}",
                    f"Investierter Betrag: {self._format_currency(position_info['amount'])}",
                ])

            self._set_active_pie_wedge(entry['wedge'])
            redraw_needed = self._pie_active_entry is not entry
            last_xy = self._pie_last_hover_xy
            if last_xy is None:
                redraw_needed = True
            else:
                pixel_distance = abs(event.x - last_xy[0]) + abs(event.y - last_xy[1])
                if pixel_distance >= 28:
                    redraw_needed = True

            if redraw_needed:
                self._pie_active_entry = entry
                self._pie_last_hover_xy = (event.x, event.y)
                self._pie_hover_annotation.xy = (event.xdata, event.ydata)
                if self._pie_hover_annotation.get_text() != tooltip:
                    self._pie_hover_annotation.set_text(tooltip)
                self._pie_hover_annotation.set_visible(True)
                self.pie_canvas.draw_idle()
            return

        self._hide_pie_annotation()

    def _on_pie_leave(self, _event):
        self._pie_drag_start = None
        self._pie_drag_xlim = None
        self._pie_drag_ylim = None
        self._hide_pie_annotation()
    
    def _update_charts(self):
        """Zeichnet alle Diagramme anhand der aktuell gefilterten Daten neu."""
        # Sicherstellen, dass Chart-Attribute existieren
        if not hasattr(self, 'pie_fig') or not hasattr(self, 'line_fig'):
            return

        active_transactions = self._get_broker_filtered_transactions()
        if not active_transactions:
            self._show_placeholder()
            return
        self._update_pie_chart()
        self._update_line_chart()
        self._update_broker_info()
    
    def _update_pie_chart(self):
        # Sicherstellen, dass pie_fig existiert
        if not hasattr(self, 'pie_fig'):
            return

        self.pie_fig.clear()
        self._pie_hover_entries = []
        self._pie_hover_annotation = None
        self._pie_hover_axes = None
        self._active_pie_wedge = None
        self._pie_drag_start = None
        self._pie_drag_xlim = None
        self._pie_drag_ylim = None
        self._pie_active_entry = None
        self._pie_last_hover_xy = None
        self._cancel_pie_animation()

        position_data = self._build_position_chart_data(self._get_broker_filtered_transactions())
        if not position_data:
            ct = self._chart_theme()
            self.pie_fig.patch.set_facecolor(ct["fig_face"])
            ax = self.pie_fig.add_subplot(111)
            ax.set_facecolor(ct["ax_face"])
            ax.set_axis_off()
            self.pie_canvas.draw()
            return

        self._pie_chart_data = position_data
        self._pie_bucket_data = self._build_pie_bucket_data(position_data)
        self._pie_total_amount = sum(entry['amount'] for entry in position_data.values()) or 1.0
        self._draw_pie_chart()

    def _get_pie_display_items(self):
        position_data = getattr(self, '_pie_chart_data', {})
        total_amount = getattr(self, '_pie_total_amount', 1.0) or 1.0
        selected_position = getattr(self, '_pie_selected_position', None)

        if selected_position in position_data:
            entry = position_data[selected_position]
            color_index, color_count = self._get_position_color_meta(selected_position)
            return [
                {
                    'type': 'position',
                    'label': selected_position,
                    'amount': entry['amount'],
                    'percent': (entry['amount'] / total_amount) * 100,
                    'data': entry,
                    'color_index': color_index,
                    'color_count': color_count,
                }
            ]

        if self._pie_selected_bucket is None:
            color_count = max(len(getattr(self, '_pie_bucket_data', [])), 1)
            return [
                {
                    'type': 'bucket',
                    'label': bucket['label'],
                    'amount': bucket['amount'],
                    'percent': (bucket['amount'] / total_amount) * 100,
                    'bucket_index': bucket['index'],
                    'positions': bucket['positions'],
                    'count': bucket['count'],
                    'data': bucket,
                    'color_index': bucket['index'],
                    'color_count': color_count,
                }
                for bucket in getattr(self, '_pie_bucket_data', [])
            ]

        bucket_positions = self._get_bucket_positions(self._pie_selected_bucket)
        allowed_positions = set(bucket_positions)
        position_color_index = {
            position: index for index, position in enumerate(bucket_positions)
        }
        color_count = max(len(bucket_positions), 1)
        return [
            {
                'type': 'position',
                'label': label,
                'amount': entry['amount'],
                'percent': (entry['amount'] / total_amount) * 100,
                'data': entry,
                'color_index': position_color_index.get(label, 0),
                'color_count': color_count,
            }
            for label, entry in position_data.items()
            if label in allowed_positions
        ]

    def _shorten_pie_label(self, label, max_length=22):
        label = str(label)
        if len(label) <= max_length:
            return label
        return label[:max_length - 1].rstrip() + "."

    def _spread_pie_labels(self, texts, min_gap=0.10):
        """Verteilt Aussenlabels vertikal, damit kleine Segmente lesbar bleiben."""
        sides = {'left': [], 'right': []}
        for text in texts:
            x, y = text.get_position()
            side = 'right' if x >= 0 else 'left'
            sides[side].append((text, x, y))

        for side, entries in sides.items():
            if len(entries) <= 1:
                continue

            entries.sort(key=lambda item: item[2])
            adjusted = []
            last_y = -1.28
            for text, x, y in entries:
                new_y = max(y, last_y + min_gap)
                adjusted.append((text, x, new_y))
                last_y = new_y

            overflow = adjusted[-1][2] - 1.28
            if overflow > 0:
                adjusted = [(text, x, y - overflow) for text, x, y in adjusted]

            for text, x, y in adjusted:
                text.set_position((1.35 if side == 'right' else -1.35, y))
                text.set_ha('left' if side == 'right' else 'right')
                text.set_va('center')

    def _format_pie_tooltip(self, title, lines):
        return "\n".join([str(title)] + lines)

    def _draw_pie_chart(self, focus_key=None, progress=0.0, focus_type=None, final_bucket_view=False):
        """Zeichnet das interaktive Kreisdiagramm inklusive Fokusanimation."""
        position_data = getattr(self, '_pie_chart_data', {})
        if not position_data:
            return

        total_amount = getattr(self, '_pie_total_amount', 1.0) or 1.0
        is_animating = focus_key is not None and 0.0 < progress < 1.0
        display_items = self._get_pie_display_items()
        if not display_items:
            return

        if final_bucket_view:
            display_items = [
                item for item in display_items
                if item.get('type') == 'position'
            ]

        labels = [item['label'] for item in display_items]
        color_map = matplotlib.colormaps['tab20']
        colors = [
            color_map(item.get('color_index', index) / max(item.get('color_count', len(labels)), 1))
            for index, item in enumerate(display_items)
        ]
        display_labels = labels[:]
        text_labels = ["" for _ in display_labels] if is_animating else [self._shorten_pie_label(label) for label in display_labels]
        display_sizes = [item['amount'] for item in display_items]
        display_colors = colors
        display_lookup = {
            (item.get('type'), item.get('bucket_index') if item.get('type') == 'bucket' else item['label']): (index, item)
            for index, item in enumerate(display_items)
        }

        focus_lookup_key = (focus_type, focus_key)
        if focus_lookup_key in display_lookup:
            focus_index, focus_item = display_lookup[focus_lookup_key]
            focus_color = colors[focus_index]
            focus_amount = focus_item['amount']
            other_amount = max(total_amount - focus_amount, 0.0)

            if progress >= 1.0:
                display_labels = [focus_item['label']]
                text_labels = [self._shorten_pie_label(focus_item['label'], max_length=28)]
                display_sizes = [1.0]
                display_colors = [focus_color]
                display_items = [focus_item]
            else:
                display_labels = [focus_item['label'], "__rest__"]
                text_labels = ["", ""]
                display_sizes = [
                    focus_amount + (total_amount - focus_amount) * progress,
                    other_amount * (1.0 - progress),
                ]
                rest_rgb = self._chart_theme()["pie_rest"]
                display_colors = [focus_color, (*rest_rgb, max(0.35 * (1.0 - progress), 0.0))]
                display_items = [focus_item, {'type': 'rest', 'label': '__rest__', 'amount': other_amount, 'percent': 0.0}]

        self.pie_fig.clear()
        self._pie_hover_entries = []
        self._pie_hover_annotation = None
        self._pie_hover_axes = None
        self._active_pie_wedge = None
        ct = self._chart_theme()
        ax = self.pie_fig.add_subplot(111)
        self.pie_fig.patch.set_facecolor(ct["fig_face"])
        ax.set_facecolor(ct["ax_face"])
        wedges, texts, autotexts = ax.pie(
            display_sizes,
            labels=text_labels,
            autopct=lambda pct: "",
            colors=display_colors,
            startangle=90,
            pctdistance=0.75,
            labeldistance=1.20,
            rotatelabels=False,
            wedgeprops=dict(linewidth=1.5, edgecolor=ct["pie_wedge_edge"]),
        )

        for text in texts:
            text.set_fontsize(8 if len(display_items) > 6 else 9)
            text.set_color(ct["pie_label"])
            text.set_fontweight("bold")
        if not is_animating:
            self._spread_pie_labels(texts, min_gap=0.13 if len(display_items) > 6 else 0.10)
            for wedge, text in zip(wedges, texts):
                if not text.get_text():
                    continue
                angle = math.radians((wedge.theta1 + wedge.theta2) / 2)
                ax.annotate(
                    "",
                    xy=(math.cos(angle), math.sin(angle)),
                    xytext=text.get_position(),
                    arrowprops=dict(
                        arrowstyle="-",
                        color=ct["pie_connector"],
                        lw=0.8,
                        shrinkA=0,
                        shrinkB=0,
                        connectionstyle="arc3,rad=0.12",
                    ),
                    zorder=0,
                )

        for wedge, autotext, item in zip(wedges, autotexts, display_items):
            label = item['label']
            if label == "__rest__":
                autotext.set_text("")
                wedge.set_alpha(max(0.35 * (1.0 - progress), 0.0))
                continue

            autotext.set_text(f"{item['percent']:.1f}%")
            autotext.set_color(ct["pie_pct"])
            autotext.set_fontsize(11 if focus_key is not None else 10)
            autotext.set_fontweight('bold')

        selected_brokers = self._get_selected_brokers() or set()
        if hasattr(self, 'pie_nav_var'):
            if self._pie_selected_position:
                self.pie_nav_var.set(f"Fokus: {self._pie_selected_position} | Zurueck per Knopf oder Rechtsklick")
            elif self._pie_selected_bucket is not None:
                bucket_label = next((bucket['label'] for bucket in self._pie_bucket_data if bucket['index'] == self._pie_selected_bucket), "Bereich")
                self.pie_nav_var.set(f"{bucket_label}: Aktie anklicken fuer Details | Zurueck per Knopf oder Rechtsklick")
            else:
                self.pie_nav_var.set(self._get_pie_nav_default_text())
        total_brokers = len(getattr(self.broker_dropdown, 'items', [])) if hasattr(self, 'broker_dropdown') else 0
        if not selected_brokers or len(selected_brokers) == total_brokers:
            title = "Portfolio-Aufteilung nach Positionen"
        elif len(selected_brokers) == 1:
            title = f"Portfolio-Aufteilung fuer {next(iter(selected_brokers))}"
        else:
            title = f"Portfolio-Aufteilung fuer {len(selected_brokers)} Broker"
        ax.set_title(title, fontsize=12, fontweight="bold", color=ct["pie_title"])
        ax.set_aspect('equal', adjustable='box')
        ax.set_xlim(-1.75, 1.75)
        ax.set_ylim(-1.55, 1.55)
        self._pie_default_xlim = ax.get_xlim()
        self._pie_default_ylim = ax.get_ylim()
        self._ensure_pie_hover_annotation(ax)

        for wedge, item in zip(wedges, display_items):
            if item['label'] == "__rest__":
                continue
            self._pie_hover_entries.append({
                'wedge': wedge,
                'label': item['label'],
                'percent': item['percent'],
                'data': item['data'],
                'type': item['type'],
                'bucket_index': item.get('bucket_index'),
            })

        if is_animating:
            self.pie_fig.subplots_adjust(left=0.03, right=0.97, top=0.90, bottom=0.03)
        else:
            self.pie_fig.tight_layout()
        self.pie_canvas.draw_idle()

    def _animate_pie_focus(self, focus_key, expand=True, target_type="position", on_complete=None):
        """Animiert das Hinein- und Herauszoomen eines Kreisdiagrammsegments."""
        current_items = self._get_pie_display_items()
        if not any(
            item.get('type') == target_type and (item.get('bucket_index') if target_type == "bucket" else item.get('label')) == focus_key
            for item in current_items
        ):
            self._update_pie_chart()
            return

        self._cancel_pie_animation()
        steps = 12
        interval_ms = 18
        self._pie_animation_state = {
            'step': 0,
            'steps': steps,
            'focus_key': focus_key,
            'target_type': target_type,
            'expand': expand,
            'on_complete': on_complete,
        }

        def animate_step():
            state = self._pie_animation_state
            if not state:
                return

            raw_progress = state['step'] / state['steps']
            eased = 1 - (1 - raw_progress) ** 3
            progress = eased if state['expand'] else 1.0 - eased
            self._draw_pie_chart(
                focus_key=state['focus_key'],
                focus_type=state['target_type'],
                progress=progress,
            )

            if state['step'] >= state['steps']:
                self._pie_animation_after_id = None
                self._pie_animation_state = None
                if state['on_complete'] is not None:
                    state['on_complete']()
                else:
                    self._update_pie_chart()
                return

            state['step'] += 1
            self._pie_animation_after_id = self.root.after(interval_ms, animate_step)

        animate_step()
    
    def _update_line_chart(self):
        # Sicherstellen, dass line_fig existiert
        if not hasattr(self, 'line_fig'):
            return

        self.line_fig.clear()
        ct = self._chart_theme()
        self.line_fig.patch.set_facecolor(ct["fig_face"])
        broker_data, all_dates = build_line_chart_data(self._get_filtered_transactions())

        ax = self.line_fig.add_subplot(111)
        ax.set_facecolor(ct["ax_face"])
        if not broker_data:
            self.line_canvas.draw_idle()
            return

        color_palette = ['#2196F3', '#4CAF50', '#FF9800', '#9C27B0', '#F44336', '#00BCD4', '#FFC107']
        for color_idx, (broker_name, dates_dict) in enumerate(broker_data.items()):
            sorted_dates = sorted(dates_dict.keys())
            cumulative_amounts, current_sum = [], 0
            for d in sorted_dates:
                current_sum += dates_dict[d]
                cumulative_amounts.append(current_sum)
            ax.plot(sorted_dates, cumulative_amounts, marker='o', linestyle='-', linewidth=2, markersize=6, 
                    label=broker_name, color=color_palette[color_idx % len(color_palette)])
            
        ax.set_xlabel('Datum', fontsize=10, color=ct["tick"])
        ax.set_ylabel('Ausgabewert (€)', fontsize=10, color=ct["tick"])
        ax.set_title('Portfolio-Wachstum über Zeit', fontsize=12, fontweight='bold', color=ct["pie_title"])
        ax.tick_params(colors=ct["tick"], labelcolor=ct["tick"])
        for spine in ax.spines.values():
            spine.set_color(ct["grid"])

        if all_dates:
            min_d, max_d = min(all_dates), max(all_dates)
            ax.set_xlim(min_d - timedelta(days=1), max_d + timedelta(days=1))
            unique_dates = sorted(list(set(all_dates)))
            if len(unique_dates) <= 15: ax.set_xticks(unique_dates)
        
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m.%Y'))
        self.line_fig.autofmt_xdate() 
        leg = ax.legend(facecolor=ct["legend_face"], edgecolor=ct["legend_edge"])
        if leg:
            for text in leg.get_texts():
                text.set_color(ct["tick"])
        ax.grid(True, color=ct["grid"], alpha=0.35)
        self.line_fig.tight_layout()
        self.line_canvas.draw()

    def _update_broker_info(self):
        if not hasattr(self, 'broker_info_tree'):
            return

        for item in self.broker_info_tree.get_children():
            self.broker_info_tree.delete(item)

        broker_data = build_broker_info_data(self._get_filtered_transactions())
        if not broker_data:
            self._clear_broker_info_panel()
            return
        self._broker_company_info = {
            entry['broker']: {
                'company_address': entry.get('company_address', ''),
                'company_phone': entry.get('company_phone', ''),
                'company_fax': entry.get('company_fax', ''),
                'company_email': entry.get('company_email', ''),
                'company_website': entry.get('company_website', ''),
            }
            for entry in broker_data
        }
        self._clear_selected_broker_info()

        purchase_total = sum(entry['purchases'] for entry in broker_data)
        fee_total = sum(entry['fees'] for entry in broker_data)
        top_broker = broker_data[0]['broker']

        self.broker_info_cards["broker_count"].config(text=str(len(broker_data)))
        self.broker_info_cards["top_broker"].config(text=top_broker[:28])
        self.broker_info_cards["purchase_total"].config(text=self._format_currency(purchase_total))
        self.broker_info_cards["fee_total"].config(text=self._format_currency(fee_total))

        for index, entry in enumerate(broker_data):
            tags = []
            if index == 0:
                tags.append("top")
            if entry['net'] < 0:
                tags.append("negative")

            self.broker_info_tree.insert(
                "",
                tk.END,
                values=(
                    entry['broker'],
                    entry['transactions'],
                    entry['position_count'],
                    entry['depot_count'],
                    self._format_currency(entry['purchases']),
                    self._format_currency(entry['fees']),
                    self._format_currency(entry['net']),
                    f"{entry['purchase_share']:.1f}%".replace('.', ','),
                ),
                tags=tuple(tags),
            )
    
    def _export_to_csv(self):
        """Exportiert die im Viewer aktuell gefilterten Transaktionen als CSV."""
        active_transactions = self._get_filtered_transactions()
        if not active_transactions:
            messagebox.showwarning("Keine Daten", "Keine Daten zum Exportieren vorhanden.")
            return
        
        if hasattr(self, '_is_exporting') and self._is_exporting: return 
        self._is_exporting = True
        
        try:
            file_path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV Dateien", "*.csv"), ("Alle Dateien", "*.*")],
                title="Finanzdaten exportieren"
            )
            if not file_path: return 
            saved_path = write_transactions_csv(active_transactions, file_path)
            messagebox.showinfo("Export abgeschlossen", f"Daten erfolgreich exportiert:\n{saved_path}")
            
        except Exception as e:
            messagebox.showerror("Exportfehler", f"Fehler beim Exportieren:\n{str(e)}")
            
        finally:
            self._is_exporting = False


def show_data_viewer(extracted_data=None):
    """Oeffnet den Viewer optional mit bereits extrahierten Daten."""
    root = tk.Tk()
    app = DataViewerApp(root, extracted_data=extracted_data, restored_pdf_selection=None)
    root.mainloop() 
    return app


def load_and_view(pdf_files):
    """Oeffnet den Viewer und laedt die uebergebenen PDFs."""
    root = tk.Tk()
    app = DataViewerApp(root, restored_pdf_selection=None)
    app.load_from_pdfs(pdf_files)
    root.mainloop() 
    return app
