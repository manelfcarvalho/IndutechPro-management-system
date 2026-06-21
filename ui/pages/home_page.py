"""Dashboard principal da aplicacao."""

import calendar
import os
import sys
import tkinter as tk
from collections import defaultdict
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ui.theme import (
    BORDER,
    BRAND,
    PANEL_BG,
    PRIMARY,
    SUCCESS,
    TEXT,
    TEXT_MUTED,
    TEXT_SUBTLE,
    WARNING,
    button_style,
    font,
    keep_custom_style,
)
from ui.utils import run_db_operation


class HomePage(ctk.CTkFrame):
    """Pagina inicial com resumo operacional, metricas e graficos."""

    PERIODS = (
        ("today", "Hoje"),
        ("week", "Semana"),
        ("month", "Mes"),
        ("year", "Ano"),
        ("all", "Todas"),
    )

    WEEKDAYS = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom")
    MONTHS = ("Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez")

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="#151617")
        self.app = app
        self.selected_period = "month"
        self.period_buttons = {}
        self.metric_cards = []
        self.dashboard_data = None
        self.content_frame = None
        self.metrics_frame = None
        self.charts_frame = None
        self.money_canvas = None
        self.profit_canvas = None
        self._money_draw_after_id = None
        self._profit_draw_after_id = None
        self.money_hover_points = []
        self.profit_hover_points = []

        self.setup_ui()
        self.refresh_data()

    def setup_ui(self):
        """Configura uma dashboard visual e leve."""
        scrollable = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        scrollable.pack(fill="both", expand=True, padx=0, pady=0)

        main_container = ctk.CTkFrame(scrollable, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=22, pady=18)

        self._create_header(main_container)

        self.content_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True)

    def _create_header(self, parent):
        header = ctk.CTkFrame(
            parent,
            fg_color=PANEL_BG,
            corner_radius=14,
            border_width=1,
            border_color=BORDER,
        )
        header.pack(fill="x", pady=(0, 18))
        header.grid_columnconfigure(0, weight=1)

        title_stack = ctk.CTkFrame(header, fg_color="transparent")
        title_stack.grid(row=0, column=0, sticky="ew", padx=18, pady=14)

        date_label = ctk.CTkLabel(
            title_stack,
            text=self._format_today_label(),
            font=font(11, "bold"),
            text_color=TEXT_SUBTLE,
            anchor="w",
        )
        date_label.pack(fill="x")

        title_label = ctk.CTkLabel(
            title_stack,
            text="Dashboard",
            font=font(27, "bold"),
            text_color=TEXT,
            anchor="w",
        )
        title_label.pack(fill="x", pady=(2, 0))

        subtitle_label = ctk.CTkLabel(
            title_stack,
            text="Visao simples das reparacoes, receita e componentes usados.",
            font=font(12),
            text_color=TEXT_MUTED,
            anchor="w",
        )
        subtitle_label.pack(fill="x", pady=(2, 0))

        right_stack = ctk.CTkFrame(header, fg_color="transparent")
        right_stack.grid(row=0, column=1, sticky="e", padx=16, pady=12)

        period_frame = ctk.CTkFrame(right_stack, fg_color="#171b20", corner_radius=10)
        period_frame.pack(side="left", padx=(0, 12))

        for key, label in self.PERIODS:
            button = ctk.CTkButton(
                period_frame,
                text=label,
                width=74,
                command=lambda period=key: self.set_period(period),
                **button_style("secondary", compact=True),
            )
            keep_custom_style(button)
            button.pack(side="left", padx=3, pady=3)
            self.period_buttons[key] = button

        backup_buttons = ctk.CTkFrame(right_stack, fg_color="transparent")
        backup_buttons.pack(side="left")

        export_button = ctk.CTkButton(
            backup_buttons,
            text="Exportar",
            command=self.export_master_excel,
            width=96,
            **button_style("primary", compact=True),
        )
        keep_custom_style(export_button)
        export_button.pack(side="left", padx=(0, 8))

        restore_button = ctk.CTkButton(
            backup_buttons,
            text="Restaurar",
            command=self.restore_backup,
            width=96,
            **button_style("warning", compact=True),
        )
        keep_custom_style(restore_button)
        restore_button.pack(side="left")

        self._sync_period_buttons()

    def set_period(self, period):
        if period == self.selected_period:
            return
        self.selected_period = period
        self._sync_period_buttons()
        self.refresh_data(force=True)

    def _sync_period_buttons(self):
        for key, button in self.period_buttons.items():
            if key == self.selected_period:
                button.configure(
                    fg_color=PRIMARY,
                    hover_color="#1D4ED8",
                    text_color="#ffffff",
                )
            else:
                button.configure(
                    fg_color="#171b20",
                    hover_color="#202833",
                    text_color=TEXT_MUTED,
                )

    def refresh_data(self, force=False):
        """Atualiza as metricas e graficos do dashboard."""

        period = self.selected_period

        def db_operation():
            repairs = self.app.db_manager.get_all_repairs(limit=10000)
            return self._build_dashboard_data(repairs, period)

        def callback(data, error):
            if error:
                print(f"Erro ao carregar dashboard: {str(error)}")
                return

            self.dashboard_data = data
            self._render_dashboard(data)

        run_db_operation(self.app.root, db_operation, callback)

    def _build_dashboard_data(self, repairs, period):
        bounds = self._period_bounds(period)
        current_repairs = self._filter_repairs(repairs, bounds["start"], bounds["end"])
        previous_repairs = self._filter_repairs(repairs, bounds["previous_start"], bounds["previous_end"])

        current_parts = self._collect_parts(current_repairs)
        previous_parts = self._collect_parts(previous_repairs)
        component_ids = sorted({ref for ref, _qty in [*current_parts, *previous_parts] if isinstance(ref, int)})
        components = self.app.db_manager.get_components_by_ids(component_ids)
        labor_rates = self._load_labor_rates()

        parts_by_label = defaultdict(int)
        for ref, qty in current_parts:
            if isinstance(ref, int):
                component = components.get(ref, {})
                code = str(component.get("code") or f"#{ref}")
                name = str(component.get("name") or "Componente")
                label = f"{code} - {name}"
            else:
                label = str(ref)
            parts_by_label[label] += int(qty or 0)

        repairs_count = len(current_repairs)
        previous_count = len(previous_repairs)
        revenue = self._paid_revenue(current_repairs)
        previous_revenue = self._paid_revenue(previous_repairs)
        used_parts_qty = sum(parts_by_label.values())
        previous_parts_qty = sum(qty for _ref, qty in previous_parts)
        unpaid_repairs = self._unpaid_repairs_count(current_repairs)
        previous_unpaid_repairs = self._unpaid_repairs_count(previous_repairs)

        money_series = self._money_series(current_repairs, bounds, period)
        profit_series = self._profit_series(current_repairs, bounds, period, components, labor_rates)

        return {
            "period": period,
            "period_label": bounds["label"],
            "metrics": [
                {
                    "title": "Reparacoes",
                    "value": str(repairs_count),
                    "detail": "folhas criadas",
                    "delta": self._delta_text(repairs_count, previous_count, bounds["has_previous"]),
                    "color": PRIMARY,
                },
                {
                    "title": "Dinheiro ganho",
                    "value": self._format_currency(revenue),
                    "detail": "reparacoes pagas",
                    "delta": self._delta_text(revenue, previous_revenue, bounds["has_previous"]),
                    "color": SUCCESS,
                },
                {
                    "title": "Componentes usados",
                    "value": str(used_parts_qty),
                    "detail": "unidades consumidas",
                    "delta": self._delta_text(used_parts_qty, previous_parts_qty, bounds["has_previous"]),
                    "color": WARNING,
                },
                {
                    "title": "Por pagar",
                    "value": str(unpaid_repairs),
                    "detail": "reparacoes nao pagas",
                    "delta": self._delta_text(unpaid_repairs, previous_unpaid_repairs, bounds["has_previous"]),
                    "color": BRAND,
                },
            ],
            "money_series": money_series,
            "profit_series": profit_series,
        }

    def _render_dashboard(self, data):
        if not self.content_frame:
            return

        for widget in self.content_frame.winfo_children():
            widget.destroy()

        summary_bar = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        summary_bar.pack(fill="x", padx=6, pady=(0, 10))

        period_label = ctk.CTkLabel(
            summary_bar,
            text=data["period_label"],
            font=font(13, "bold"),
            text_color=TEXT,
            anchor="w",
        )
        period_label.pack(side="left")

        hint_label = ctk.CTkLabel(
            summary_bar,
            text="Comparacao feita com o periodo anterior equivalente.",
            font=font(11),
            text_color=TEXT_SUBTLE,
            anchor="e",
        )
        hint_label.pack(side="right")

        self.metrics_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.metrics_frame.pack(fill="x", pady=(0, 14))
        self.metric_cards = [
            self._create_metric_card(self.metrics_frame, metric)
            for metric in data["metrics"]
        ]
        self._arrange_metric_cards()
        self.metrics_frame.bind("<Configure>", lambda _event: self._arrange_metric_cards())

        self.charts_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.charts_frame.pack(fill="both", expand=True)

        profit_panel = self._create_chart_panel(
            self.charts_frame,
            title="Lucro estimado",
            subtitle="Margem de componentes + mao de obra paga",
        )
        self.profit_canvas = self._create_canvas(profit_panel)
        self.profit_canvas.bind("<Configure>", lambda _event: self._schedule_profit_chart())
        self.profit_canvas.bind("<Motion>", self._on_profit_motion)
        self.profit_canvas.bind("<Leave>", lambda _event: self._clear_chart_hover(self.profit_canvas))

        money_panel = self._create_chart_panel(
            self.charts_frame,
            title="Dinheiro ganho",
            subtitle="Receita paga acumulada no intervalo",
        )
        self.money_canvas = self._create_canvas(money_panel)
        self.money_canvas.bind("<Configure>", lambda _event: self._schedule_money_chart())
        self.money_canvas.bind("<Motion>", self._on_money_motion)
        self.money_canvas.bind("<Leave>", lambda _event: self._clear_chart_hover(self.money_canvas))

        self.chart_panels = [profit_panel, money_panel]
        self._arrange_chart_panels()
        self.charts_frame.bind("<Configure>", lambda _event: self._arrange_chart_panels())

        self._schedule_profit_chart()
        self._schedule_money_chart()

    def _create_metric_card(self, parent, metric):
        card = ctk.CTkFrame(
            parent,
            height=132,
            fg_color="#1f2227",
            corner_radius=14,
            border_width=1,
            border_color="#2b3138",
        )
        card.grid_propagate(False)
        card.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(
            card,
            text=metric["title"],
            font=font(12, "bold"),
            text_color=TEXT_MUTED,
            anchor="w",
        )
        title_label.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 0))

        if metric.get("delta"):
            delta_text, role = metric["delta"]
            delta_badge = self._create_delta_badge(card, delta_text, role)
            delta_badge.grid(row=0, column=1, sticky="e", padx=(8, 14), pady=(14, 0))

        value_label = ctk.CTkLabel(
            card,
            text=metric["value"],
            font=font(25, "bold"),
            text_color=TEXT,
            anchor="w",
        )
        value_label.grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(10, 0))

        detail_label = ctk.CTkLabel(
            card,
            text=metric["detail"],
            font=font(11),
            text_color=TEXT_SUBTLE,
            anchor="w",
        )
        detail_label.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(7, 16))

        return card

    def _arrange_metric_cards(self):
        if not self.metrics_frame or not self.metric_cards:
            return

        width = max(self.metrics_frame.winfo_width(), 1)
        columns = 2 if width < 980 else 4
        for widget in self.metric_cards:
            widget.grid_forget()
        for index, card in enumerate(self.metric_cards):
            row = index // columns
            col = index % columns
            card.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
        for col in range(4):
            self.metrics_frame.grid_columnconfigure(col, weight=1 if col < columns else 0, uniform="metrics")

    def _create_chart_panel(self, parent, title, subtitle):
        panel = ctk.CTkFrame(
            parent,
            height=370,
            fg_color=PANEL_BG,
            corner_radius=12,
            border_width=1,
            border_color=BORDER,
        )

        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(14, 8))

        title_label = ctk.CTkLabel(
            header,
            text=title,
            font=font(17, "bold"),
            text_color=TEXT,
            anchor="w",
        )
        title_label.pack(fill="x")

        subtitle_label = ctk.CTkLabel(
            header,
            text=subtitle,
            font=font(11),
            text_color=TEXT_SUBTLE,
            anchor="w",
        )
        subtitle_label.pack(fill="x", pady=(2, 0))

        return panel

    def _create_canvas(self, parent):
        canvas = tk.Canvas(
            parent,
            height=290,
            bg=PANEL_BG,
            bd=0,
            highlightthickness=0,
            relief="flat",
        )
        canvas.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        return canvas

    def _arrange_chart_panels(self):
        if not getattr(self, "chart_panels", None) or not self.charts_frame:
            return

        width = max(self.charts_frame.winfo_width(), 1)
        stacked = width < 960
        for panel in self.chart_panels:
            panel.grid_forget()

        if stacked:
            self.charts_frame.grid_columnconfigure(0, weight=1)
            self.charts_frame.grid_columnconfigure(1, weight=0)
            self.chart_panels[0].grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
            self.chart_panels[1].grid(row=1, column=0, sticky="nsew", padx=6, pady=6)
        else:
            for col in range(2):
                self.charts_frame.grid_columnconfigure(col, weight=1, uniform="charts")
            self.chart_panels[0].grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
            self.chart_panels[1].grid(row=0, column=1, sticky="nsew", padx=6, pady=6)

        self.charts_frame.grid_rowconfigure(0, weight=1)
        self.charts_frame.grid_rowconfigure(1, weight=1 if stacked else 0)

    def _schedule_money_chart(self):
        if self._money_draw_after_id:
            self.after_cancel(self._money_draw_after_id)
        self._money_draw_after_id = self.after(80, self._draw_money_chart)

    def _schedule_profit_chart(self):
        if self._profit_draw_after_id:
            self.after_cancel(self._profit_draw_after_id)
        self._profit_draw_after_id = self.after(80, self._draw_profit_chart)

    def _draw_money_chart(self):
        self._money_draw_after_id = None
        if not self.money_canvas or not self.dashboard_data:
            return
        series = self.dashboard_data.get("money_series", [])
        canvas = self.money_canvas
        self.money_hover_points = []
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        if width < 80 or height < 80:
            return

        self._draw_empty_chart_base(canvas, width, height)
        if not series or max(value for _label, value in series) <= 0:
            self._draw_empty_state(canvas, width, height, "Sem dinheiro pago neste periodo")
            return

        left, top, right, bottom = 54, 22, 22, 36
        chart_w = width - left - right
        chart_h = height - top - bottom
        max_value = max(value for _label, value in series) or 1
        y_max = max_value * 1.18

        for step in range(5):
            y = top + (chart_h * step / 4)
            canvas.create_line(left, y, width - right, y, fill="#30343b", width=1, dash=(2, 5))
            value = y_max * (1 - step / 4)
            canvas.create_text(
                left - 8,
                y,
                text=self._short_money(value),
                fill="#8f949c",
                font=("Segoe UI", 8),
                anchor="e",
            )

        point_count = len(series)
        slot = chart_w / max(point_count - 1, 1)
        points = []
        non_zero_points = [(index, value) for index, (_label, value) in enumerate(series) if value > 0]

        for index, (label, value) in enumerate(series):
            x_center = left + slot * index if point_count > 1 else left + chart_w / 2
            ratio = value / y_max
            y_point = top + chart_h * (1 - ratio)
            points.append((x_center, y_point))

            if point_count > 1:
                canvas.create_line(x_center, top, x_center, top + chart_h, fill="#252b33", width=1, dash=(2, 5))

            if point_count <= 12 or index % max(1, point_count // 8) == 0:
                canvas.create_text(
                    x_center,
                    height - 14,
                    text=label,
                    fill="#9aa0a8",
                    font=("Segoe UI", 8),
                    anchor="n",
                )

        baseline = top + chart_h
        if len(non_zero_points) <= 1:
            zero_line_y = baseline
            canvas.create_line(left, zero_line_y, width - right, zero_line_y, fill="#3a414b", width=1)
            if non_zero_points:
                best_index, best_value = non_zero_points[0]
                best_label = series[best_index][0]
                point_x, point_y = points[best_index]
                bar_width = max(18, min(36, chart_w / max(point_count, 1) * 0.34))
                self._draw_vertical_gradient_bar(
                    canvas,
                    point_x - bar_width / 2,
                    point_y,
                    point_x + bar_width / 2,
                    baseline,
                    "#9ec5ff",
                    "#2563eb",
                )
                canvas.create_oval(point_x - 4, point_y - 4, point_x + 4, point_y + 4, fill="#7fb0ff", outline="#dceaff", width=2)
                self._store_hover_point(self.money_hover_points, point_x, point_y, best_value)
            return

        if len(points) > 1:
            area_points = [(left, top + chart_h), *points, (width - right, top + chart_h)]
            canvas.create_polygon(
                *[coord for point in area_points for coord in point],
                fill="#182f4c",
                outline="",
            )

            smooth_points = []
            for point in points:
                smooth_points.extend(point)
            canvas.create_line(*smooth_points, fill="#69a2ff", width=3, smooth=False)

            best_index, (best_label, best_value) = max(enumerate(series), key=lambda item: item[1][1])
            point_x, point_y = points[best_index]
            canvas.create_oval(point_x - 4, point_y - 4, point_x + 4, point_y + 4, fill="#4f8cff", outline="#dceaff", width=2)
            for point_index, (_label, value) in enumerate(series):
                self._store_hover_point(self.money_hover_points, points[point_index][0], points[point_index][1], value)
        elif points:
            point_x, point_y = points[0]
            canvas.create_oval(point_x - 5, point_y - 5, point_x + 5, point_y + 5, fill="#4f8cff", outline="")
            self._store_hover_point(self.money_hover_points, point_x, point_y, series[0][1])

    def _draw_profit_chart(self):
        self._profit_draw_after_id = None
        if not self.profit_canvas or not self.dashboard_data:
            return
        series = self.dashboard_data.get("profit_series", [])
        canvas = self.profit_canvas
        self.profit_hover_points = []
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        if width < 80 or height < 80:
            return

        self._draw_empty_chart_base(canvas, width, height)
        if not series or max(value for _label, value in series) <= 0:
            self._draw_empty_state(canvas, width, height, "Sem lucro pago neste periodo")
            return

        left, top, right, bottom = 48, 24, 20, 52
        chart_w = width - left - right
        chart_h = height - top - bottom
        max_value = max(value for _label, value in series) or 1
        y_max = max_value * 1.18

        for step in range(4):
            y = top + chart_h * step / 3
            value = y_max * (1 - step / 3)
            canvas.create_line(left, y, width - right, y, fill="#30343b", width=1, dash=(2, 5))
            canvas.create_text(
                left - 8,
                y,
                text=self._short_money(value),
                fill="#8f949c",
                font=("Segoe UI", 8),
                anchor="e",
            )

        point_count = len(series)
        slot = chart_w / max(point_count - 1, 1)
        points = []
        for index, (label, value) in enumerate(series):
            x_center = left + slot * index if point_count > 1 else left + chart_w / 2
            ratio = value / y_max
            y_point = top + chart_h * (1 - ratio)
            points.append((x_center, y_point))
            if point_count > 1:
                canvas.create_line(x_center, top, x_center, top + chart_h, fill="#252b33", width=1, dash=(2, 5))
            if point_count <= 12 or index % max(1, point_count // 8) == 0:
                canvas.create_text(
                    x_center,
                    height - 18,
                    text=label,
                    fill="#9aa0a8",
                    font=("Segoe UI", 8),
                    anchor="n",
                )

        baseline = top + chart_h
        non_zero_points = [(index, value) for index, (_label, value) in enumerate(series) if value > 0]
        if len(non_zero_points) <= 1:
            canvas.create_line(left, baseline, width - right, baseline, fill="#3a414b", width=1)
            if non_zero_points:
                point_index, value = non_zero_points[0]
                point_x, point_y = points[point_index]
                bar_width = max(18, min(36, chart_w / max(point_count, 1) * 0.34))
                self._draw_vertical_gradient_bar(
                    canvas,
                    point_x - bar_width / 2,
                    point_y,
                    point_x + bar_width / 2,
                    baseline,
                    "#c7f9dc",
                    "#16a34a",
                )
                canvas.create_oval(point_x - 4, point_y - 4, point_x + 4, point_y + 4, fill="#86efac", outline="#dcfce7", width=2)
                self._store_hover_point(self.profit_hover_points, point_x, point_y, value)
            return

        area_points = [(left, baseline), *points, (width - right, baseline)]
        canvas.create_polygon(
            *[coord for point in area_points for coord in point],
            fill="#123522",
            outline="",
        )
        smooth_points = []
        for point in points:
            smooth_points.extend(point)
        canvas.create_line(*smooth_points, fill="#5ee68b", width=3, smooth=False)
        for index, (_label, value) in enumerate(series):
            x, y = points[index]
            self._store_hover_point(self.profit_hover_points, x, y, value)
        best_index, (_best_label, _best_value) = max(enumerate(series), key=lambda item: item[1][1])
        best_x, best_y = points[best_index]
        canvas.create_oval(best_x - 4, best_y - 4, best_x + 4, best_y + 4, fill="#86efac", outline="#dcfce7", width=2)

    def _create_delta_badge(self, parent, text, role):
        width = max(76, min(104, 34 + len(str(text)) * 7))
        height = 26
        canvas = tk.Canvas(
            parent,
            width=width,
            height=height,
            bg="#1f2227",
            bd=0,
            highlightthickness=0,
            relief="flat",
        )

        def draw(_event=None):
            self._draw_delta_badge(canvas, width, height, text, role)

        canvas.after_idle(draw)
        return canvas

    def _draw_delta_badge(self, canvas, width, height, text, role):
        canvas.delete("all")
        if role == "up":
            start_color, end_color, text_color = "#dffbea", "#baf7d1", "#128044"
        elif role == "down":
            start_color, end_color, text_color = "#ffe6e6", "#ffc7c7", "#b91c1c"
        else:
            start_color, end_color, text_color = "#303640", "#252b33", TEXT_SUBTLE

        radius = height / 2
        for x in range(width):
            color = self._mix_hex(start_color, end_color, x / max(width - 1, 1))
            y0 = 0
            y1 = height
            if x < radius:
                dx = radius - x
                offset = radius - (radius * radius - dx * dx) ** 0.5
                y0 = offset
                y1 = height - offset
            elif x > width - radius:
                dx = x - (width - radius)
                offset = radius - (radius * radius - dx * dx) ** 0.5
                y0 = offset
                y1 = height - offset
            canvas.create_line(x, y0, x, y1, fill=color)

        canvas.create_text(
            width / 2,
            height / 2,
            text=text,
            fill=text_color,
            font=("Segoe UI", 9, "bold"),
            anchor="center",
        )

    def _draw_vertical_gradient_bar(self, canvas, x0, y0, x1, y1, start_color, end_color):
        y0 = max(y0, 0)
        y1 = max(y1, y0 + 1)
        height = max(int(y1 - y0), 1)
        for offset in range(height):
            ratio = offset / max(height - 1, 1)
            color = self._mix_hex(start_color, end_color, ratio)
            y = y0 + offset
            canvas.create_line(x0, y, x1, y, fill=color)

    def _draw_tooltip(self, canvas, point_x, point_y, text, left_limit, right_limit, top_limit):
        bubble_w = max(92, len(text) * 7)
        bubble_h = 28
        bubble_x = min(max(point_x - bubble_w / 2, left_limit), right_limit - bubble_w)
        bubble_y = max(top_limit + 6, point_y - 42)
        canvas.create_rectangle(
            bubble_x,
            bubble_y,
            bubble_x + bubble_w,
            bubble_y + bubble_h,
            fill="#f6f8fb",
            outline="",
            tags=("hover",),
        )
        canvas.create_text(
            bubble_x + bubble_w / 2,
            bubble_y + bubble_h / 2,
            text=text,
            fill="#111827",
            font=("Segoe UI", 9, "bold"),
            tags=("hover",),
        )

    def _store_hover_point(self, points, x, y, value):
        points.append({"x": x, "y": y, "value": value})

    def _on_money_motion(self, event):
        self._show_chart_hover(self.money_canvas, self.money_hover_points, event)

    def _on_profit_motion(self, event):
        self._show_chart_hover(self.profit_canvas, self.profit_hover_points, event)

    def _show_chart_hover(self, canvas, points, event):
        if not canvas or not points:
            return
        nearest = min(points, key=lambda point: abs(point["x"] - event.x))
        if abs(nearest["x"] - event.x) > 24:
            self._clear_chart_hover(canvas)
            return

        self._clear_chart_hover(canvas)
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        top_limit = 22
        canvas.create_line(
            nearest["x"],
            top_limit,
            nearest["x"],
            height - 36,
            fill="#d7dde6",
            width=1,
            dash=(3, 4),
            tags=("hover",),
        )
        canvas.create_oval(
            nearest["x"] - 4,
            nearest["y"] - 4,
            nearest["x"] + 4,
            nearest["y"] + 4,
            fill="#f8fafc",
            outline="#69a2ff",
            width=2,
            tags=("hover",),
        )
        self._draw_tooltip(
            canvas,
            nearest["x"],
            nearest["y"],
            self._format_currency(nearest["value"]),
            54,
            width - 22,
            top_limit,
        )

    def _clear_chart_hover(self, canvas):
        if canvas:
            canvas.delete("hover")

    def _draw_empty_chart_base(self, canvas, width, height):
        canvas.create_rectangle(0, 0, width, height, fill=PANEL_BG, outline="")

    def _draw_empty_state(self, canvas, width, height, text):
        canvas.create_text(
            width / 2,
            height / 2,
            text=text,
            fill=TEXT_SUBTLE,
            font=("Segoe UI", 11, "bold"),
            anchor="center",
        )

    def _period_bounds(self, period):
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if period == "today":
            start = today
            end = start + timedelta(days=1)
            previous_start = start - timedelta(days=1)
            label = f"Hoje, {start.strftime('%d/%m/%Y')}"
        elif period == "week":
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=7)
            previous_start = start - timedelta(days=7)
            label = f"Semana de {start.strftime('%d/%m')} a {(end - timedelta(days=1)).strftime('%d/%m/%Y')}"
        elif period == "month":
            start = today.replace(day=1)
            end = self._add_month(start)
            previous_start = self._add_month(start, -1)
            label = f"{self.MONTHS[start.month - 1]} {start.year}"
        elif period == "year":
            start = today.replace(month=1, day=1)
            end = start.replace(year=start.year + 1)
            previous_start = start.replace(year=start.year - 1)
            label = f"Ano {start.year}"
        else:
            return {
                "start": None,
                "end": None,
                "previous_start": None,
                "previous_end": None,
                "label": "Todas as datas",
                "has_previous": False,
            }

        return {
            "start": start,
            "end": end,
            "previous_start": previous_start,
            "previous_end": start,
            "label": label,
            "has_previous": True,
        }

    def _filter_repairs(self, repairs, start, end):
        if start is None or end is None:
            return list(repairs or [])

        filtered = []
        for repair in repairs or []:
            repair_date = self._parse_date(repair.get("date"))
            if repair_date and start <= repair_date < end:
                filtered.append(repair)
        return filtered

    def _money_series(self, repairs, bounds, period):
        return self._value_series(
            repairs,
            bounds,
            period,
            lambda repair: self._safe_float(repair.get("total")) if self._is_paid(repair) else 0.0,
        )

    def _profit_series(self, repairs, bounds, period, components, labor_rates):
        return self._value_series(
            repairs,
            bounds,
            period,
            lambda repair: self._repair_profit(repair, components, labor_rates) if self._is_paid(repair) else 0.0,
        )

    def _value_series(self, repairs, bounds, period, value_getter):
        if period == "today":
            bucket_labels = [(index, f"{hour:02d}h") for index, hour in enumerate(range(0, 24, 4))]

            def bucket_key(repair_date):
                return min(repair_date.hour // 4, 5)

        elif period == "week":
            start = bounds["start"]
            bucket_labels = [(offset, self.WEEKDAYS[(start + timedelta(days=offset)).weekday()]) for offset in range(7)]

            def bucket_key(repair_date):
                return (repair_date.date() - start.date()).days

        elif period == "month":
            start = bounds["start"]
            days = calendar.monthrange(start.year, start.month)[1]
            bucket_labels = [(offset, str(offset + 1)) for offset in range(days)]

            def bucket_key(repair_date):
                return repair_date.day - 1

        elif period == "year":
            bucket_labels = [(month, self.MONTHS[month - 1]) for month in range(1, 13)]

            def bucket_key(repair_date):
                return repair_date.month

        else:
            years = sorted({date.year for repair in repairs if (date := self._parse_date(repair.get("date")))})
            bucket_labels = [(year, str(year)) for year in years]

            def bucket_key(repair_date):
                return repair_date.year

        buckets = defaultdict(float)
        valid_keys = {key for key, _label in bucket_labels}
        for repair in repairs:
            repair_date = self._parse_date(repair.get("date"))
            if not repair_date:
                continue
            key = bucket_key(repair_date)
            if key in valid_keys:
                buckets[key] += value_getter(repair)

        total = 0.0
        series = []
        for key, label in bucket_labels:
            total += buckets[key]
            series.append((label, total))
        return series

    def _collect_parts(self, repairs):
        parts = []
        for repair in repairs or []:
            used_parts = repair.get("used_parts") or ""
            try:
                parsed = self.app.db_manager._parse_used_parts(used_parts)
            except Exception:
                parsed = []
            for ref, qty in parsed:
                try:
                    qty = int(qty)
                except (TypeError, ValueError):
                    qty = 0
                if qty > 0:
                    parts.append((ref, qty))
        return parts

    def _unpaid_repairs_count(self, repairs):
        return sum(1 for repair in repairs if not self._is_paid(repair))

    def _paid_revenue(self, repairs):
        return sum(self._safe_float(repair.get("total")) for repair in repairs if self._is_paid(repair))

    def _load_labor_rates(self):
        return {
            "labor1": self._safe_float(self.app.db_manager.get_setting("labor_rate_1", "30.0")),
            "labor2": self._safe_float(self.app.db_manager.get_setting("labor_rate_2", "45.0")),
            "placas": self._safe_float(self.app.db_manager.get_setting("placas_price", "50.0")),
        }

    def _repair_profit(self, repair, components, labor_rates):
        component_profit = 0.0
        for ref, qty in self._collect_parts([repair]):
            if not isinstance(ref, int):
                continue
            component = components.get(ref, {})
            sale_price = self._safe_float(component.get("price"))
            purchase_price = self._safe_float(component.get("preco_compra"))
            component_profit += (sale_price - purchase_price) * qty

        labor_type = str(repair.get("labor_type") or "labor1")
        labor_rate = labor_rates.get(labor_type, labor_rates["labor1"])
        labor_qty = self._safe_float(repair.get("hours_worked"))
        labor_profit = labor_qty * labor_rate

        test_hours = self._safe_float(repair.get("horas_teste"))
        test_rate = self._safe_float(repair.get("preco_hora_teste"))
        test_profit = test_hours * test_rate

        return component_profit + labor_profit + test_profit

    def _is_paid(self, repair):
        return str(repair.get("payment_status") or "").strip().lower() == "pago"

    def _parse_date(self, value):
        if not value:
            return None
        text = str(value).strip()
        formats = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%Y %H:%M:%S")
        for date_format in formats:
            try:
                return datetime.strptime(text, date_format)
            except ValueError:
                continue
        return None

    def _delta_text(self, current, previous, has_previous):
        if not has_previous:
            return None
        if previous == 0:
            if current == 0:
                return ("0%", "flat")
            return ("+ Novo", "up")
        delta = ((current - previous) / abs(previous)) * 100
        role = "up" if delta > 0 else "down" if delta < 0 else "flat"
        if role == "up":
            return (f"+ {abs(delta):.0f}%", role)
        if role == "down":
            return (f"- {abs(delta):.0f}%", role)
        return ("0%", role)

    def _hex_to_rgb(self, color):
        color = color.lstrip("#")
        return tuple(int(color[index:index + 2], 16) for index in (0, 2, 4))

    def _rgb_to_hex(self, rgb):
        return "#" + "".join(f"{max(0, min(255, int(channel))):02x}" for channel in rgb)

    def _mix_hex(self, start_color, end_color, ratio):
        ratio = max(0.0, min(1.0, ratio))
        start = self._hex_to_rgb(start_color)
        end = self._hex_to_rgb(end_color)
        mixed = tuple(start[index] + (end[index] - start[index]) * ratio for index in range(3))
        return self._rgb_to_hex(mixed)

    def _safe_float(self, value):
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def _format_currency(self, value):
        return f"{value:.2f} EUR"

    def _short_money(self, value):
        if value >= 1000:
            return f"{value / 1000:.1f}k"
        return f"{value:.0f}"

    def _truncate(self, text, limit):
        text = str(text)
        return text if len(text) <= limit else f"{text[: limit - 3]}..."

    def _add_month(self, value, offset=1):
        month = value.month - 1 + offset
        year = value.year + month // 12
        month = month % 12 + 1
        day = min(value.day, calendar.monthrange(year, month)[1])
        return value.replace(year=year, month=month, day=day)

    def _format_today_label(self):
        now = datetime.now()
        weekday = self.WEEKDAYS[now.weekday()]
        return f"{weekday}, {now.strftime('%d/%m/%Y')}"

    def restore_backup(self):
        """Restaura a base de dados a partir de um ficheiro de backup."""
        try:
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            backups_dir = os.path.join(current_dir, "backups")

            if not os.path.exists(backups_dir):
                backups_dir = os.getcwd()

            backup_file = filedialog.askopenfilename(
                initialdir=backups_dir,
                title="Selecionar Ficheiro de Backup",
                filetypes=[("Database files", "*.db"), ("All files", "*.*")],
            )

            if not backup_file:
                return

            if not backup_file.endswith(".db"):
                messagebox.showerror("Erro", "Por favor, selecione um ficheiro .db valido.")
                return

            confirm_message = (
                "Atencao! Isto vai substituir todos os dados atuais pelos do backup selecionado.\n\n"
                f"Ficheiro: {os.path.basename(backup_file)}\n\n"
                "Esta acao e irreversivel. Deseja continuar?"
            )

            if not messagebox.askyesno("Confirmar Restauro", confirm_message):
                return

            def db_operation():
                return self.app.db_manager.restore_backup(backup_file)

            def callback(success, error):
                if error:
                    messagebox.showerror("Erro", f"Erro ao restaurar backup:\n\n{str(error)}")
                    return

                if success:
                    messagebox.showinfo(
                        "Sucesso",
                        "Restauro concluido com sucesso.\n\n"
                        "A aplicacao vai reiniciar para carregar os dados restaurados.",
                    )

                    self.app.root.destroy()

                    import subprocess

                    python = sys.executable
                    script = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                        "main.py",
                    )
                    subprocess.Popen([python, script])
                    sys.exit(0)
                else:
                    messagebox.showerror("Erro", "Falha ao restaurar backup. Verifique o ficheiro selecionado.")

            run_db_operation(self.app.root, db_operation, callback)

        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado ao restaurar backup:\n\n{str(e)}")

    def export_master_excel(self):
        """Exporta a base de dados completa para um ficheiro Excel Master."""
        try:
            filename = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
                initialfile="Backup_Indutechpro.xlsx",
                title="Exportar Backup Completo (.xlsx)",
            )

            if not filename:
                return

            if os.path.exists(filename):
                try:
                    test_file = open(filename, "a")
                    test_file.close()
                except (IOError, PermissionError, OSError):
                    messagebox.showerror(
                        "Erro",
                        "O ficheiro esta aberto ou sem permissoes de escrita.\n\n"
                        "Feche o ficheiro Excel se estiver aberto e tente novamente.",
                    )
                    return

            def db_operation():
                return self.app.db_manager.export_master_database(filename)

            def callback(success, error):
                if error:
                    messagebox.showerror("Erro", f"Erro ao exportar backup:\n\n{str(error)}")
                    return

                if success:
                    messagebox.showinfo(
                        "Operacao Concluida",
                        f"Backup completo exportado com sucesso.\n\n"
                        f"Ficheiro: {os.path.basename(filename)}\n"
                        f"Localizacao: {os.path.dirname(filename)}\n\n"
                        "O ficheiro contem 3 folhas:\n"
                        "- Clientes\n"
                        "- Stock\n"
                        "- Reparacoes",
                    )

                    try:
                        if os.name == "nt":
                            os.startfile(filename)
                        elif os.name == "posix":
                            import subprocess

                            subprocess.call(["open", filename])
                    except Exception:
                        pass
                else:
                    messagebox.showerror("Erro", "Falha ao exportar backup completo.")

            run_db_operation(self.app.root, db_operation, callback)

        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao exportar backup: {str(e)}")
