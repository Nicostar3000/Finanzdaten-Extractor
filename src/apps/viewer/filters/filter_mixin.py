"""Filter-Mixin fuer `DataViewerApp`."""

from datetime import datetime

import tkinter as tk
from tkinter import ttk, messagebox

from ....ui.widgets import CheckDropdown, InfoTooltip
from ....common.formatting import clean_csv, natural_sort_key


class FilterMixin:
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
        if hasattr(self, "date_start_entry"):
            self.date_start_entry.config(state=state)
            self.date_end_entry.config(state=state)
        if hasattr(self, "date_start_cal_btn"):
            self.date_start_cal_btn.config(state=state)
            self.date_end_cal_btn.config(state=state)
        if refresh:
            self._on_filter_changed()

    def _cancel_filter_refresh_debounce(self):
        if self._filter_refresh_job is not None:
            self.root.after_cancel(self._filter_refresh_job)
            self._filter_refresh_job = None

    def _on_filter_changed(self):
        if not hasattr(self, "details_notebook"):
            return
        self._cancel_filter_refresh_debounce()
        self._filter_refresh_job = self.root.after(100, self._apply_debounced_filter_refresh)

    def _apply_debounced_filter_refresh(self):
        self._filter_refresh_job = None
        self._refresh_filtered_views()

    def _reset_filters(self):
        self._cancel_filter_refresh_debounce()
        if hasattr(self, "broker_dropdown"):
            self.broker_dropdown.select_all()
        if hasattr(self, "position_dropdown"):
            self.position_dropdown.apply_filter("")
            self.position_dropdown.select_all()
        if hasattr(self, "depot_dropdown"):
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
        if not hasattr(self, "broker_dropdown"):
            return

        brokers = sorted({transaction.get("broker", "Unbekannt") for transaction in self.all_transactions})
        depots = sorted(
            {
                str(transaction.get("depot", "Nil"))
                for transaction in self.all_transactions
                if transaction.get("depot") not in [None, "", "Nil"]
            },
            key=natural_sort_key,
        )
        positions = sorted(
            {
                clean_csv(transaction.get("position", "Unbekannt"))
                for transaction in self.all_transactions
                if clean_csv(transaction.get("position", "Unbekannt")) != "Nil"
            },
            key=natural_sort_key,
        )

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
            return float(text.replace(".", "").replace(",", "."))
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
        if not hasattr(self, "broker_dropdown"):
            return None
        return self.broker_dropdown.get_selected()

    def _get_segment_size(self):
        raw_value = str(self.segment_size_var.get() if hasattr(self, "segment_size_var") else "10 %")
        try:
            return int(raw_value.replace("%", "").strip())
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
        if not hasattr(self, "top_x_box"):
            return
        seg_zero = self._get_segment_size() == 0
        if self.top_x_enabled_var.get() and seg_zero:
            self.top_x_box.configure(state="readonly")
        else:
            self.top_x_box.configure(state="disabled")

    def _get_pie_nav_default_text(self):
        if self._get_segment_size() == 0:
            return "Eine Position pro Segment (Klick fuer Detail / Filter)"
        return f"Klicke auf einen {self._get_segment_size()}%-Bereich, um seine Aktien zu sehen"

    def _get_active_filter_kwargs(self):
        date_start = date_end = None
        if hasattr(self, "date_filter_mode") and self.date_filter_mode.get() == "range":
            date_start = self._parse_filter_date(self.date_start_var.get())
            date_end = self._parse_filter_date(self.date_end_var.get())

        top_x = None
        if (
            hasattr(self, "top_x_enabled_var")
            and self.top_x_enabled_var.get()
            and self._get_segment_size() == 0
        ):
            try:
                top_x = int(self.top_x_var.get())
            except ValueError:
                top_x = None

        selected_positions = self.position_dropdown.get_selected() if hasattr(self, "position_dropdown") else None
        selected_depots = self.depot_dropdown.get_selected() if hasattr(self, "depot_dropdown") else None

        return {
            "selected_broker": self._get_selected_brokers(),
            "selected_positions": selected_positions,
            "selected_depots": selected_depots,
            "date_start": date_start,
            "date_end": date_end,
            "amount_min": self._parse_filter_float(self.amount_min_var.get()) if hasattr(self, "amount_min_var") else None,
            "amount_max": self._parse_filter_float(self.amount_max_var.get()) if hasattr(self, "amount_max_var") else None,
            "quantity_min": self._parse_filter_float(self.quantity_min_var.get()) if hasattr(self, "quantity_min_var") else None,
            "quantity_max": self._parse_filter_float(self.quantity_max_var.get()) if hasattr(self, "quantity_max_var") else None,
            "top_x": top_x,
        }

