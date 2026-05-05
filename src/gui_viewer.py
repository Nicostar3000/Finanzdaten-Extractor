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
from .apps.viewer.charts.chart_mixin import ChartMixin
from .apps.viewer.filters.filter_mixin import FilterMixin
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


class DataViewerApp(FilterMixin, ChartMixin):
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
