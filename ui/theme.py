"""Shared visual styling for the Indutechpro desktop UI."""

import customtkinter as ctk


FONT_FAMILY = "Segoe UI"

PAGE_BG = "#151617"
PANEL_BG = "#202124"
PANEL_ALT_BG = "#242424"
BORDER = "#35363a"
TEXT = "#f5f5f5"
TEXT_MUTED = "#b8b8b8"
TEXT_SUBTLE = "#8f949c"

BRAND = "#FF5722"
BRAND_HOVER = "#E64A19"
PRIMARY = "#2563EB"
PRIMARY_HOVER = "#1D4ED8"
SUCCESS = "#16A34A"
SUCCESS_HOVER = "#15803D"
WARNING = "#F59E0B"
WARNING_HOVER = "#D97706"
DANGER = "#DC2626"
DANGER_HOVER = "#B91C1C"
SECONDARY = "#1a2027"
SECONDARY_HOVER = "#232a33"


def font(size=13, weight="normal"):
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)


def create_page_header(parent, title, subtitle=None):
    """Create the compact page header used across non-dashboard pages."""
    header = ctk.CTkFrame(
        parent,
        fg_color=PANEL_BG,
        corner_radius=8,
        border_width=1,
        border_color=BORDER,
    )
    header.pack(fill="x", padx=20, pady=(18, 10))
    header.grid_columnconfigure(0, weight=1)

    title_stack = ctk.CTkFrame(header, fg_color="transparent")
    title_stack.grid(row=0, column=0, sticky="ew", padx=16, pady=12)

    title_label = ctk.CTkLabel(
        title_stack,
        text=title,
        font=font(21, "bold"),
        text_color=TEXT,
        anchor="w",
    )
    title_label.pack(fill="x")

    if subtitle:
        subtitle_label = ctk.CTkLabel(
            title_stack,
            text=subtitle,
            font=font(12),
            text_color=TEXT_MUTED,
            anchor="w",
        )
        subtitle_label.pack(fill="x", pady=(2, 0))

    buttons_frame = ctk.CTkFrame(header, fg_color="transparent")
    buttons_frame.grid(row=0, column=1, sticky="e", padx=14, pady=12)
    return header, buttons_frame


def button_style(role="primary", compact=False):
    colors = {
        "brand": (BRAND, BRAND_HOVER),
        "primary": (PRIMARY, PRIMARY_HOVER),
        "success": (SUCCESS, SUCCESS_HOVER),
        "warning": (WARNING, WARNING_HOVER),
        "danger": (DANGER, DANGER_HOVER),
        "secondary": (SECONDARY, SECONDARY_HOVER),
    }
    fg_color, hover_color = colors.get(role, colors["primary"])
    return {
        "font": font(12 if compact else 13, "bold"),
        "corner_radius": 8 if not compact else 7,
        "fg_color": fg_color,
        "hover_color": hover_color,
        "text_color": "#ffffff",
        "height": 30 if compact else 34,
        "border_width": 0,
    }


def keep_custom_style(widget):
    """Prevent the global style pass from rewriting a purpose-built control."""
    widget._indutech_keep_style = True
    return widget


def create_button(parent, text, command, role="primary", width=124, compact=False, **kwargs):
    """Create a standard styled button without applying geometry management."""
    style = button_style(role, compact=compact)
    style.update(kwargs)
    button = ctk.CTkButton(
        parent,
        text=text,
        command=command,
        width=width,
        **style,
    )
    return keep_custom_style(button)


def create_popup_card(parent, padx=18, pady=18):
    """Create the standard framed surface for pop-up window content."""
    frame = ctk.CTkFrame(
        parent,
        fg_color=PANEL_BG,
        corner_radius=8,
        border_width=1,
        border_color=BORDER,
    )
    frame.pack(fill="both", expand=True, padx=padx, pady=pady)
    return frame


def create_action_footer(parent, padx=18, pady=(12, 18), align="right"):
    """Create a consistent bottom action area for pop-up windows."""
    footer = ctk.CTkFrame(parent, fg_color="transparent")
    footer.pack(side="bottom", fill="x", padx=padx, pady=pady)

    button_row = ctk.CTkFrame(footer, fg_color="transparent")
    pack_side = "right" if align == "right" else "left"
    button_row.pack(side=pack_side)
    return button_row


def create_action_button(parent, text, command, role="primary", width=132, compact=False):
    """Create a standard action button for pop-up footers."""
    button = create_button(parent, text, command, role=role, width=width, compact=compact)
    button.pack(side="right", padx=(8, 0))
    return button


def create_toolbar_button(parent, text, command, role="primary", width=124):
    """Create a compact button for page headers and toolbars."""
    button = create_button(parent, text, command, role=role, width=width, compact=True)
    button.pack(side="left", padx=(0, 8))
    return button


def create_table_actions_frame(parent, row=0, column=0, padx=8, pady=6):
    """Create a centered action area inside a table/grid cell."""
    frame = ctk.CTkFrame(parent, fg_color="transparent")
    frame.grid(row=row, column=column, padx=padx, pady=pady)
    return frame


def create_table_action_button(parent, text, command, role="primary", width=82):
    """Create a compact table action button."""
    button = create_button(parent, text, command, role=role, width=width, compact=True)
    button.pack(side="left", padx=3)
    return button


def configure_table_columns(frame, column_weights, uniform, min_widths=None):
    """Apply consistent grid weights/min-widths to a table row or header."""
    min_widths = min_widths or {}
    for index, weight in enumerate(column_weights):
        kwargs = {"weight": weight, "uniform": uniform}
        if index in min_widths:
            kwargs["minsize"] = min_widths[index]
        frame.grid_columnconfigure(index, **kwargs)


def create_table_header(parent, headers, column_weights, uniform, min_widths=None, padx=0, pady=(0, 8)):
    """Create a reusable table header row."""
    header = ctk.CTkFrame(
        parent,
        fg_color="#151b21",
        corner_radius=6,
        border_width=1,
        border_color="#2c333b",
    )
    header.pack(fill="x", padx=padx, pady=pady)
    configure_table_columns(header, column_weights, uniform, min_widths=min_widths)

    last_index = len(headers) - 1
    for index, text in enumerate(headers):
        create_table_cell(
            header,
            text=text,
            column=index,
            is_header=True,
            anchor="center" if index == last_index else "w",
            pady=9,
        )
    return header


def create_table_row(parent, column_weights, uniform, min_widths=None, padx=0, pady=4):
    """Create a reusable table data row."""
    row = ctk.CTkFrame(
        parent,
        fg_color=PANEL_BG,
        corner_radius=6,
        border_width=1,
        border_color="#303236",
    )
    row.pack(fill="x", padx=padx, pady=pady)
    configure_table_columns(row, column_weights, uniform, min_widths=min_widths)
    return row


def create_table_cell(
    parent,
    text,
    column,
    row=0,
    anchor="w",
    weight="normal",
    text_color=None,
    is_header=False,
    padx=7,
    pady=8,
):
    """Create a reusable table cell label."""
    label = ctk.CTkLabel(
        parent,
        text=text,
        font=font(12, "bold" if is_header else weight),
        text_color=text_color or (TEXT_MUTED if is_header else "#c9ced6"),
        anchor=anchor,
    )
    label.grid(row=row, column=column, padx=padx, pady=pady, sticky="ew")
    return label


def create_list_item(
    parent,
    title,
    subtitle=None,
    command=None,
    action_text=None,
    action_command=None,
    action_role="primary",
    action_width=100,
    padx=5,
    pady=3,
):
    """Create a reusable result/list row with optional click and action button."""
    item_frame = ctk.CTkFrame(
        parent,
        fg_color=PANEL_BG,
        corner_radius=6,
        border_width=1,
        border_color="#303236",
    )
    item_frame.pack(fill="x", pady=pady, padx=padx)

    info_frame = ctk.CTkFrame(item_frame, fg_color="transparent")
    info_frame.pack(side="left", fill="x", expand=True, padx=10, pady=8)

    title_label = ctk.CTkLabel(
        info_frame,
        text=title,
        font=font(13, "bold"),
        text_color=TEXT,
        anchor="w",
    )
    title_label.pack(fill="x")

    subtitle_label = None
    if subtitle is not None:
        subtitle_label = ctk.CTkLabel(
            info_frame,
            text=subtitle,
            font=font(12),
            text_color=TEXT_MUTED,
            anchor="w",
        )
        subtitle_label.pack(fill="x")

    if command:
        def run_command(_event=None):
            command()

        item_frame.bind("<Button-1>", run_command)
        title_label.bind("<Button-1>", run_command)
        if subtitle_label is not None:
            subtitle_label.bind("<Button-1>", run_command)

    action_button = None
    if action_text and action_command:
        action_button = create_button(
            item_frame,
            text=action_text,
            command=action_command,
            role=action_role,
            width=action_width,
            compact=True,
            height=30,
        )
        action_button.pack(side="right", padx=10, pady=5)

    return {
        "frame": item_frame,
        "info_frame": info_frame,
        "title_label": title_label,
        "subtitle_label": subtitle_label,
        "action_button": action_button,
    }


def status_badge_style(role="info"):
    colors = {
        "info": ("#1D4ED8", "#2563EB", "#eaf1ff"),
        "warning": ("#A16207", "#B7791F", "#fff7d6"),
        "success": ("#15803D", "#16A34A", "#e8fff1"),
        "danger": ("#B91C1C", "#DC2626", "#fff1f1"),
        "secondary": ("#29313c", "#343f4d", "#dbe4ee"),
    }
    fg_color, hover_color, text_color = colors.get(role, colors["info"])
    return {
        "font": font(11, "bold"),
        "fg_color": fg_color,
        "hover_color": hover_color,
        "text_color": text_color,
        "corner_radius": 999,
        "border_width": 0,
        "height": 28,
    }


def repair_status_badge_style(status):
    status_text = str(status or "")
    if "Aguardar" in status_text:
        return status_badge_style("warning")
    if "Pronto" in status_text:
        return status_badge_style("success")
    return status_badge_style("info")


def payment_status_badge_style(is_paid):
    return status_badge_style("success" if is_paid else "danger")


def icon_button_style():
    return {
        "font": font(15, "bold"),
        "fg_color": "#202833",
        "hover_color": "#2a3442",
        "text_color": "#dbe4ee",
        "border_color": "#3a4656",
        "border_width": 1,
        "corner_radius": 999,
        "width": 38,
        "height": 28,
    }


def _color_token(value):
    if isinstance(value, (list, tuple)) and value:
        value = value[-1]
    return str(value).lower()


def _infer_button_role(button):
    text = ""
    try:
        text = str(button.cget("text")).lower()
    except Exception:
        pass

    try:
        color = _color_token(button.cget("fg_color"))
    except Exception:
        color = ""

    if any(word in text for word in ("apagar", "remover", "delete", "cancelar")) or "#f44336" in color or "#dc2626" in color:
        return "danger" if "cancelar" not in text else "secondary"
    if any(word in text for word in ("fechar", "voltar")):
        return "secondary"
    if any(word in text for word in ("guardar", "salvar", "adicionar", "novo", "entrada", "pago")) or "#4caf50" in color:
        return "success"
    if any(word in text for word in ("restaurar", "pendente", "progresso")) or "#ff9800" in color or "#f39c12" in color:
        return "warning"
    if "exportar" in text or "importar" in text or "#2196f3" in color or "#3b8ed0" in color:
        return "primary"
    if "configurar" in text or color in ("transparent", "none") or "#666666" in color or "#444444" in color:
        return "secondary"
    return "primary"


def _configure_font(widget):
    try:
        current = widget.cget("font")
        size = current.cget("size") if hasattr(current, "cget") else 13
        weight = current.cget("weight") if hasattr(current, "cget") else "normal"
        widget.configure(font=font(size=size, weight=weight))
    except Exception:
        pass


def style_button(button):
    if getattr(button, "_indutech_keep_style", False):
        return

    role = _infer_button_role(button)
    compact = False
    try:
        compact = int(button.cget("width") or 0) <= 90
    except Exception:
        compact = False

    style = button_style(role, compact=compact)
    try:
        button.configure(**style)
    except Exception:
        for key, value in style.items():
            try:
                button.configure(**{key: value})
            except Exception:
                pass


def apply_modern_style(root):
    """Apply shared typography and button styling to an existing widget tree."""
    stack = [root]
    while stack:
        widget = stack.pop()
        if isinstance(widget, ctk.CTkButton):
            style_button(widget)
        elif isinstance(widget, (ctk.CTkLabel, ctk.CTkEntry, ctk.CTkTextbox, ctk.CTkOptionMenu)):
            _configure_font(widget)

        try:
            stack.extend(widget.winfo_children())
        except Exception:
            pass
