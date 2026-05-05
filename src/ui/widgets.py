"""Gemeinsame Tkinter-Widgets und UI-Helfer."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# Wird von aufrufenden UIs (z. B. Viewer) gesetzt, um Tooltip-Farben an Themes
# anzupassen. Diese globale Referenz wird absichtlich direkt verwendet, damit
# Theme-Umschaltungen ohne Neuanlage der Tooltips wirken.
TOOLTIP_STYLE = {"bg": "#ffffe8", "fg": "#101010"}


def set_tooltip_style(style: dict) -> None:
    """Aktualisiert die Tooltip-Farben (in-place)."""
    if not isinstance(style, dict):
        return
    TOOLTIP_STYLE.clear()
    TOOLTIP_STYLE.update(style)


def bind_mousewheel_to_canvas(canvas: tk.Canvas, root_widget: tk.Misc) -> None:
    """Bindet Mausrad-Scrolling an ein Widget und alle Kinder.

    Scrollbars werden ausgelassen, damit das Rad nicht doppelt mit der Leiste reagiert.
    """

    def on_wheel(event):
        if getattr(event, "delta", 0):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        elif getattr(event, "num", None) == 5:
            canvas.yview_scroll(1, "units")
        elif getattr(event, "num", None) == 4:
            canvas.yview_scroll(-1, "units")
        return "break"

    def recur(widget):
        if isinstance(widget, (ttk.Scrollbar, tk.Scrollbar)):
            return
        widget.bind("<MouseWheel>", on_wheel)
        widget.bind("<Button-4>", on_wheel)
        widget.bind("<Button-5>", on_wheel)
        for child in widget.winfo_children():
            recur(child)

    recur(root_widget)
    canvas.bind("<MouseWheel>", on_wheel)
    canvas.bind("<Button-4>", on_wheel)
    canvas.bind("<Button-5>", on_wheel)


class InfoTooltip:
    """Kleiner Hover-Tooltip fuer Info-Blasen."""

    def __init__(self, widget: tk.Misc, text: str):
        self.widget = widget
        self.text = text
        self.window = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event=None):
        if self.window is not None:
            return
        x = self.widget.winfo_rootx() + 18
        y = self.widget.winfo_rooty() + 18
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            self.window,
            text=self.text,
            justify=tk.LEFT,
            background=TOOLTIP_STYLE["bg"],
            foreground=TOOLTIP_STYLE["fg"],
            relief=tk.SOLID,
            borderwidth=1,
            font=("Segoe UI", 9),
            wraplength=280,
            padx=8,
            pady=5,
        )
        label.pack()

    def _hide(self, _event=None):
        if self.window is not None:
            self.window.destroy()
            self.window = None


class CheckDropdown:
    """Dropdown mit Checkboxen und maximal fuenf sichtbaren Eintraegen."""

    def __init__(self, parent, on_change=None, width=20, colors_fn=None):
        self.parent = parent
        self._root = parent.winfo_toplevel()
        self.on_change = on_change
        self._colors_fn = colors_fn
        self.items = []
        self.filtered_items = []
        self.vars = {}
        self.popup = None
        self._focus_out_job = None
        self._pending_change = False
        self.button = ttk.Button(parent, text="Alle ausgewählt", width=width, command=self._toggle_popup)
        self.button.pack(fill=tk.X)

    def set_items(self, items, preserve=False):
        if self.popup is not None:
            self._close_popup()
        old_selected = self.get_selected()
        self.items = list(dict.fromkeys(str(item) for item in items if str(item)))
        if preserve and old_selected:
            selected = set(old_selected).intersection(self.items)
        else:
            selected = set(self.items)
        self.vars = {item: tk.BooleanVar(value=item in selected) for item in self.items}
        self.apply_filter("")
        self._update_button_text()

    def apply_filter(self, query):
        query = (query or "").lower().strip()
        self.filtered_items = [item for item in self.items if query in item.lower()]
        if self.popup is not None:
            self._render_popup()

    def get_selected(self):
        return {item for item, var in self.vars.items() if var.get()}

    def select_all(self):
        for var in self.vars.values():
            var.set(True)
        self._changed()

    def select_none(self):
        for var in self.vars.values():
            var.set(False)
        self._changed()

    def select_all_shown(self):
        """Waehlt alle aktuell in der Liste sichtbaren (gefilterten) Eintraege."""
        for item in self.filtered_items:
            var = self.vars.get(item)
            if var is not None:
                var.set(True)
        self._changed()

    def select_none_shown(self):
        """Waehlt alle aktuell sichtbaren Eintraege ab."""
        for item in self.filtered_items:
            var = self.vars.get(item)
            if var is not None:
                var.set(False)
        self._changed()

    def _cancel_focus_out_job(self):
        if self._focus_out_job is not None:
            self._root.after_cancel(self._focus_out_job)
            self._focus_out_job = None

    def _flush_pending_change(self):
        if not self._pending_change:
            return
        self._pending_change = False
        if self.on_change is not None:
            self.on_change()

    def _toggle_popup(self):
        if self.popup is not None:
            self._close_popup()
            return
        self._pending_change = False
        self.popup = tk.Toplevel(self.parent)
        self.popup.wm_overrideredirect(True)
        x = self.button.winfo_rootx()
        y = self.button.winfo_rooty() + self.button.winfo_height()
        self.popup.wm_geometry(f"+{x}+{y}")
        self._render_popup()
        self.popup.bind("<FocusOut>", self._on_popup_focus_out)
        self.popup.bind("<Escape>", lambda _event: self._close_popup())
        self.popup.focus_force()

    def _guess_popup_bg(self, _widget):
        try:
            return self.popup.cget("background")
        except (tk.TclError, ValueError):
            try:
                return ttk.Style().lookup("TFrame", "background", default="SystemButtonFace")
            except tk.TclError:
                return "SystemButtonFace"

    def _on_popup_focus_out(self, _event=None):
        # FocusOut feuert auf Windows oft, bevor der Klick ein Kind-Widget fokussiert.
        self._cancel_focus_out_job()
        self._focus_out_job = self._root.after(10, self._close_if_focus_left_popup)

    def _widget_under_popup(self, widget):
        while widget is not None:
            if widget == self.popup:
                return True
            try:
                widget = widget.master
            except tk.TclError:
                break
        return False

    def _close_if_focus_left_popup(self):
        self._focus_out_job = None
        if self.popup is None:
            return
        try:
            fw = self._root.focus_get()
        except tk.TclError:
            fw = None
        if fw is None:
            self._close_popup()
            return
        try:
            if fw.winfo_toplevel() == self.popup or self._widget_under_popup(fw):
                return
        except tk.TclError:
            pass
        self._close_popup()

    def _render_popup(self):
        for child in self.popup.winfo_children():
            child.destroy()

        container = ttk.Frame(self.popup, padding=3)
        container.pack(fill=tk.BOTH, expand=True)

        toolbar = ttk.Frame(container)
        toolbar.pack(fill=tk.X, pady=(0, 1))
        cols = self._colors_fn() if self._colors_fn else None
        link_fg = cols["link_fg"] if cols else "#0a5fbf"
        sep_bg = cols["popup_bg"] if cols and cols.get("popup_bg") else self._guess_popup_bg(toolbar)
        link_kw = dict(
            master=toolbar,
            font=("Segoe UI", 9, "underline"),
            fg=link_fg,
            cursor="hand2",
            bg=sep_bg,
        )
        lbl_all = tk.Label(text="Alle auswählen", **link_kw)
        lbl_all.pack(side=tk.LEFT)
        lbl_all.bind("<Button-1>", lambda _e: self.select_all_shown())
        tk.Label(toolbar, text="  ·  ", font=("Segoe UI", 9), bg=sep_bg, fg=link_fg).pack(side=tk.LEFT)
        lbl_none = tk.Label(text="Keine", **link_kw)
        lbl_none.pack(side=tk.LEFT)
        lbl_none.bind("<Button-1>", lambda _e: self.select_none_shown())
        ttk.Separator(container, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 2))

        list_height = min(max(len(self.filtered_items), 1), 5) * 22
        canvas = tk.Canvas(container, width=230, height=list_height, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        for item in self.filtered_items:
            ttk.Checkbutton(inner, text=item, variable=self.vars[item], command=self._changed).pack(
                anchor="w",
                fill=tk.X,
                pady=0,
            )

        bind_mousewheel_to_canvas(canvas, container)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        if cols and cols.get("popup_bg"):
            try:
                self.popup.configure(background=cols["popup_bg"])
                canvas.configure(background=cols["popup_bg"])
            except tk.TclError:
                pass

    def _close_popup(self):
        self._flush_pending_change()
        self._cancel_focus_out_job()
        if self.popup is not None:
            self.popup.destroy()
            self.popup = None

    def _changed(self):
        self._update_button_text()
        if self.popup is not None:
            self._pending_change = True
            return
        if self.on_change is not None:
            self.on_change()

    def _update_button_text(self):
        selected_count = len(self.get_selected())
        total = len(self.items)
        if total == 0:
            text = "Keine Einträge"
        elif selected_count == total:
            text = "Alle ausgewählt"
        elif selected_count == 0:
            text = "Keine ausgewählt"
        else:
            text = f"{selected_count} von {total} ausgewählt"
        self.button.config(text=text)

