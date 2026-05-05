"""Chart-Mixin fuer `DataViewerApp`.

Enthaelt Pie- und Line-Chart-Logik, um `gui_viewer.py` zu entlasten.
"""

import math
from datetime import timedelta

import matplotlib
import matplotlib.dates as mdates

from ....analysis.portfolio import build_line_chart_data


class ChartMixin:
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
            contains, _ = entry["wedge"].contains(event)
            if contains:
                pressed_entry = entry
                break

        self._pie_press_event = {
            "x": event.x,
            "y": event.y,
            "entry": pressed_entry,
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

        if event.button != 1 or not press_event or not press_event["entry"]:
            return

        moved = abs(event.x - press_event["x"]) + abs(event.y - press_event["y"])
        if moved <= 6:
            entry = press_event["entry"]
            if entry.get("type") == "bucket":
                self._apply_pie_bucket_filter(entry.get("bucket_index"))
            elif entry.get("type") == "position":
                self._apply_pie_position_filter(entry["label"])

    def _on_pie_scroll(self, event):
        if event.inaxes != self._pie_hover_axes:
            return
        if event.xdata is None or event.ydata is None:
            return

        scale_factor = 0.85 if event.button == "up" else 1.15
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
            contains, _ = entry["wedge"].contains(event)
            if not contains:
                continue

            if entry.get("type") == "bucket":
                bucket_info = entry["data"]
                tooltip = self._format_pie_tooltip(
                    entry["label"],
                    [
                        f"Anteil am Portfolio: {entry['percent']:.1f}%",
                        f"Aktien: {bucket_info['count']}",
                        f"Investierter Betrag: {self._format_currency(bucket_info['amount'])}",
                    ],
                )
            else:
                position_info = entry["data"]
                if position_info["kurs_basis"] > 0:
                    avg_kurs = self._format_currency(position_info["kurs_gewicht"] / position_info["kurs_basis"])
                elif position_info["kurs_fallback"] is not None:
                    avg_kurs = self._format_currency(position_info["kurs_fallback"])
                else:
                    avg_kurs = "Nicht verfuegbar"

                tooltip = self._format_pie_tooltip(
                    entry["label"],
                    [
                        f"Anteil am Portfolio: {entry['percent']:.1f}%",
                        f"Stückzahl: {self._format_quantity(position_info['anzahl'])}",
                        f"Durchschnittlicher Einstandskurs: {avg_kurs}",
                        f"Investierter Betrag: {self._format_currency(position_info['amount'])}",
                    ],
                )

            self._set_active_pie_wedge(entry["wedge"])
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
        if not hasattr(self, "pie_fig") or not hasattr(self, "line_fig"):
            return

        active_transactions = self._get_broker_filtered_transactions()
        if not active_transactions:
            self._show_placeholder()
            return
        self._update_pie_chart()
        self._update_line_chart()
        self._update_broker_info()

    def _update_pie_chart(self):
        if not hasattr(self, "pie_fig"):
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
        self._pie_total_amount = sum(entry["amount"] for entry in position_data.values()) or 1.0
        self._draw_pie_chart()

    def _get_pie_display_items(self):
        position_data = getattr(self, "_pie_chart_data", {})
        total_amount = getattr(self, "_pie_total_amount", 1.0) or 1.0
        selected_position = getattr(self, "_pie_selected_position", None)

        if selected_position in position_data:
            entry = position_data[selected_position]
            color_index, color_count = self._get_position_color_meta(selected_position)
            return [
                {
                    "type": "position",
                    "label": selected_position,
                    "amount": entry["amount"],
                    "percent": (entry["amount"] / total_amount) * 100,
                    "data": entry,
                    "color_index": color_index,
                    "color_count": color_count,
                }
            ]

        if self._pie_selected_bucket is None:
            color_count = max(len(getattr(self, "_pie_bucket_data", [])), 1)
            return [
                {
                    "type": "bucket",
                    "label": bucket["label"],
                    "amount": bucket["amount"],
                    "percent": (bucket["amount"] / total_amount) * 100,
                    "bucket_index": bucket["index"],
                    "positions": bucket["positions"],
                    "count": bucket["count"],
                    "data": bucket,
                    "color_index": bucket["index"],
                    "color_count": color_count,
                }
                for bucket in getattr(self, "_pie_bucket_data", [])
            ]

        bucket_positions = self._get_bucket_positions(self._pie_selected_bucket)
        allowed_positions = set(bucket_positions)
        position_color_index = {position: index for index, position in enumerate(bucket_positions)}
        color_count = max(len(bucket_positions), 1)
        return [
            {
                "type": "position",
                "label": label,
                "amount": entry["amount"],
                "percent": (entry["amount"] / total_amount) * 100,
                "data": entry,
                "color_index": position_color_index.get(label, 0),
                "color_count": color_count,
            }
            for label, entry in position_data.items()
            if label in allowed_positions
        ]

    def _shorten_pie_label(self, label, max_length=22):
        label = str(label)
        if len(label) <= max_length:
            return label
        return label[: max_length - 1].rstrip() + "."

    def _spread_pie_labels(self, texts, min_gap=0.10):
        """Verteilt Aussenlabels vertikal, damit kleine Segmente lesbar bleiben."""
        sides = {"left": [], "right": []}
        for text in texts:
            x, y = text.get_position()
            side = "right" if x >= 0 else "left"
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
                text.set_position((1.35 if side == "right" else -1.35, y))
                text.set_ha("left" if side == "right" else "right")
                text.set_va("center")

    def _format_pie_tooltip(self, title, lines):
        return "\n".join([str(title)] + lines)

    def _draw_pie_chart(self, focus_key=None, progress=0.0, focus_type=None, final_bucket_view=False):
        """Zeichnet das interaktive Kreisdiagramm inklusive Fokusanimation."""
        position_data = getattr(self, "_pie_chart_data", {})
        if not position_data:
            return

        total_amount = getattr(self, "_pie_total_amount", 1.0) or 1.0
        is_animating = focus_key is not None and 0.0 < progress < 1.0
        display_items = self._get_pie_display_items()
        if not display_items:
            return

        if final_bucket_view:
            display_items = [item for item in display_items if item.get("type") == "position"]

        labels = [item["label"] for item in display_items]
        color_map = matplotlib.colormaps["tab20"]
        colors = [
            color_map(item.get("color_index", index) / max(item.get("color_count", len(labels)), 1))
            for index, item in enumerate(display_items)
        ]
        display_labels = labels[:]
        text_labels = (
            ["" for _ in display_labels]
            if is_animating
            else [self._shorten_pie_label(label) for label in display_labels]
        )
        display_sizes = [item["amount"] for item in display_items]
        display_colors = colors
        display_lookup = {
            (item.get("type"), item.get("bucket_index") if item.get("type") == "bucket" else item["label"]): (index, item)
            for index, item in enumerate(display_items)
        }

        focus_lookup_key = (focus_type, focus_key)
        if focus_lookup_key in display_lookup:
            focus_index, focus_item = display_lookup[focus_lookup_key]
            focus_color = colors[focus_index]
            focus_amount = focus_item["amount"]
            other_amount = max(total_amount - focus_amount, 0.0)

            if progress >= 1.0:
                display_labels = [focus_item["label"]]
                text_labels = [self._shorten_pie_label(focus_item["label"], max_length=28)]
                display_sizes = [1.0]
                display_colors = [focus_color]
                display_items = [focus_item]
            else:
                display_labels = [focus_item["label"], "__rest__"]
                text_labels = ["", ""]
                display_sizes = [
                    focus_amount + (total_amount - focus_amount) * progress,
                    other_amount * (1.0 - progress),
                ]
                rest_rgb = self._chart_theme()["pie_rest"]
                display_colors = [focus_color, (*rest_rgb, max(0.35 * (1.0 - progress), 0.0))]
                display_items = [
                    focus_item,
                    {"type": "rest", "label": "__rest__", "amount": other_amount, "percent": 0.0},
                ]

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
            label = item["label"]
            if label == "__rest__":
                autotext.set_text("")
                wedge.set_alpha(max(0.35 * (1.0 - progress), 0.0))
                continue

            autotext.set_text(f"{item['percent']:.1f}%")
            autotext.set_color(ct["pie_pct"])
            autotext.set_fontsize(11 if focus_key is not None else 10)
            autotext.set_fontweight("bold")

        selected_brokers = self._get_selected_brokers() or set()
        if hasattr(self, "pie_nav_var"):
            if self._pie_selected_position:
                self.pie_nav_var.set(f"Fokus: {self._pie_selected_position} | Zurueck per Knopf oder Rechtsklick")
            elif self._pie_selected_bucket is not None:
                bucket_label = next(
                    (bucket["label"] for bucket in self._pie_bucket_data if bucket["index"] == self._pie_selected_bucket),
                    "Bereich",
                )
                self.pie_nav_var.set(f"{bucket_label}: Aktie anklicken fuer Details | Zurueck per Knopf oder Rechtsklick")
            else:
                self.pie_nav_var.set(self._get_pie_nav_default_text())
        total_brokers = len(getattr(self.broker_dropdown, "items", [])) if hasattr(self, "broker_dropdown") else 0
        if not selected_brokers or len(selected_brokers) == total_brokers:
            title = "Portfolio-Aufteilung nach Positionen"
        elif len(selected_brokers) == 1:
            title = f"Portfolio-Aufteilung fuer {next(iter(selected_brokers))}"
        else:
            title = f"Portfolio-Aufteilung fuer {len(selected_brokers)} Broker"
        ax.set_title(title, fontsize=12, fontweight="bold", color=ct["pie_title"])
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlim(-1.75, 1.75)
        ax.set_ylim(-1.55, 1.55)
        self._pie_default_xlim = ax.get_xlim()
        self._pie_default_ylim = ax.get_ylim()
        self._ensure_pie_hover_annotation(ax)

        for wedge, item in zip(wedges, display_items):
            if item["label"] == "__rest__":
                continue
            self._pie_hover_entries.append(
                {
                    "wedge": wedge,
                    "label": item["label"],
                    "percent": item["percent"],
                    "data": item["data"],
                    "type": item["type"],
                    "bucket_index": item.get("bucket_index"),
                }
            )

        if is_animating:
            self.pie_fig.subplots_adjust(left=0.03, right=0.97, top=0.90, bottom=0.03)
        else:
            self.pie_fig.tight_layout()
        self.pie_canvas.draw_idle()

    def _animate_pie_focus(self, focus_key, expand=True, target_type="position", on_complete=None):
        """Animiert das Hinein- und Herauszoomen eines Kreisdiagrammsegments."""
        current_items = self._get_pie_display_items()
        if not any(
            item.get("type") == target_type
            and (item.get("bucket_index") if target_type == "bucket" else item.get("label")) == focus_key
            for item in current_items
        ):
            self._update_pie_chart()
            return

        self._cancel_pie_animation()
        steps = 12
        interval_ms = 18
        self._pie_animation_state = {
            "step": 0,
            "steps": steps,
            "focus_key": focus_key,
            "target_type": target_type,
            "expand": expand,
            "on_complete": on_complete,
        }

        def animate_step():
            state = self._pie_animation_state
            if not state:
                return

            raw_progress = state["step"] / state["steps"]
            eased = 1 - (1 - raw_progress) ** 3
            progress = eased if state["expand"] else 1.0 - eased
            self._draw_pie_chart(
                focus_key=state["focus_key"],
                focus_type=state["target_type"],
                progress=progress,
            )

            if state["step"] >= state["steps"]:
                self._pie_animation_after_id = None
                self._pie_animation_state = None
                if state["on_complete"] is not None:
                    state["on_complete"]()
                else:
                    self._update_pie_chart()
                return

            state["step"] += 1
            self._pie_animation_after_id = self.root.after(interval_ms, animate_step)

        animate_step()

    def _update_line_chart(self):
        if not hasattr(self, "line_fig"):
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

        color_palette = ["#2196F3", "#4CAF50", "#FF9800", "#9C27B0", "#F44336", "#00BCD4", "#FFC107"]
        for color_idx, (broker_name, dates_dict) in enumerate(broker_data.items()):
            sorted_dates = sorted(dates_dict.keys())
            cumulative_amounts, current_sum = [], 0
            for d in sorted_dates:
                current_sum += dates_dict[d]
                cumulative_amounts.append(current_sum)
            ax.plot(
                sorted_dates,
                cumulative_amounts,
                marker="o",
                linestyle="-",
                linewidth=2,
                markersize=6,
                label=broker_name,
                color=color_palette[color_idx % len(color_palette)],
            )

        ax.set_xlabel("Datum", fontsize=10, color=ct["tick"])
        ax.set_ylabel("Ausgabewert (€)", fontsize=10, color=ct["tick"])
        ax.set_title("Portfolio-Wachstum über Zeit", fontsize=12, fontweight="bold", color=ct["pie_title"])
        ax.tick_params(colors=ct["tick"], labelcolor=ct["tick"])
        for spine in ax.spines.values():
            spine.set_color(ct["grid"])

        if all_dates:
            min_d, max_d = min(all_dates), max(all_dates)
            ax.set_xlim(min_d - timedelta(days=1), max_d + timedelta(days=1))
            unique_dates = sorted(list(set(all_dates)))
            if len(unique_dates) <= 15:
                ax.set_xticks(unique_dates)

        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m.%Y"))
        self.line_fig.autofmt_xdate()
        leg = ax.legend(facecolor=ct["legend_face"], edgecolor=ct["legend_edge"])
        if leg:
            for text in leg.get_texts():
                text.set_color(ct["tick"])
        ax.grid(True, color=ct["grid"], alpha=0.35)
        self.line_fig.tight_layout()
        self.line_canvas.draw()

