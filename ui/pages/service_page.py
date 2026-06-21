"""
Página de Nova Reparação
Permite registar reparações e utilizar componentes do stock
"""

import customtkinter as ctk
from tkinter import messagebox
from typing import List, Dict
from ui.utils import Debouncer, run_db_operation, run_db_operation_with_loading
from ui.theme import (
    apply_modern_style,
    create_button,
    create_action_button,
    create_action_footer,
    create_page_header,
    create_popup_card,
    create_table_action_button,
    create_toolbar_button,
)


def _safe_int(value, default=0):
    """Converte valores vindos da BD/importacao para int sem rebentar a UI."""
    try:
        if value is None or value == "":
            return default
        return int(float(str(value).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return default


def _safe_float(value, default=0.0):
    """Converte valores vindos da BD/importacao para float sem rebentar a UI."""
    try:
        if value is None or value == "":
            return default
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return default


def _normalize_component(component: dict) -> dict:
    """Normaliza um componente para uso seguro na UI."""
    if not component:
        return {}

    normalized = dict(component)
    normalized["id"] = _safe_int(normalized.get("id"), default=None)
    normalized["code"] = str(normalized.get("code") or "N/A")
    normalized["name"] = str(normalized.get("name") or normalized["code"])
    normalized["price"] = _safe_float(normalized.get("price"), default=0.0)
    normalized["qty"] = _safe_int(normalized.get("qty"), default=0)
    return normalized


def _normalize_components_by_id(components: dict) -> dict:
    """Normaliza um dicionario {id: component} e remove entradas sem ID."""
    normalized = {}
    for component in (components or {}).values():
        clean_component = _normalize_component(component)
        comp_id = clean_component.get("id")
        if comp_id is not None:
            normalized[comp_id] = clean_component
    return normalized


class LaborTypeSelector(ctk.CTkFrame):
    """Button selector with the same get/set surface as CTkSegmentedButton."""

    def __init__(self, parent, values, command):
        super().__init__(parent, fg_color="transparent")
        self.values = values
        self.command = command
        self.current_value = values[0] if values else ""
        self.buttons = {}

        for index, value in enumerate(values):
            self.grid_columnconfigure(index, weight=1, uniform="labor_types")
            button = ctk.CTkButton(
                self,
                text=value,
                command=lambda selected=value: self.set(selected, trigger=True),
                font=ctk.CTkFont(size=12, weight="bold"),
                height=34,
                corner_radius=8,
                border_width=1,
                border_color="#35363a",
            )
            button._indutech_keep_style = True
            button.grid(row=0, column=index, sticky="ew", padx=2)
            self.buttons[value] = button

        self._refresh()

    def get(self):
        return self.current_value

    def set(self, value, trigger=False):
        if value not in self.buttons:
            return

        self.current_value = value
        self._refresh()
        if trigger and self.command:
            self.command(value)

    def _refresh(self):
        for value, button in self.buttons.items():
            is_active = value == self.current_value
            button.configure(
                fg_color="#FF5722" if is_active else "#1a2027",
                hover_color="#E64A19" if is_active else "#232a33",
                text_color="#ffffff" if is_active else "#c9ced6",
                border_color="#FF5722" if is_active else "#35363a",
            )


class ServicePage(ctk.CTkFrame):
    """Página de registo de reparações"""

    def __init__(self, parent, app):
        """
        Inicializa a página de reparações

        Args:
            parent: Widget pai
            app: Instância da aplicação principal
        """
        super().__init__(parent, fg_color="#151617")
        self.app = app
        self.selected_components = []  # Lista de componentes selecionados: [(id, qty), ...]
        self.components_cache = {}  # Cache de componentes para evitar consultas repetidas
        self.is_loading = False
        self._components_hash = None  # Hash para evitar refreshes desnecessários
        self.MAX_RESULTS = 20  # Limitar resultados para melhor performance
        self.current_client_id = None  # ID do cliente selecionado

        # Initialize UI first - this creates all widgets including search_entry
        self.setup_ui()

        # Only call refresh_components_list after UI is fully set up
        # Use after() to ensure all widgets are properly initialized
        self.after(100, self.refresh_components_list)

    def setup_ui(self):
        """Configura a interface da página de reparações"""
        # Título
        _, buttons_frame = create_page_header(
            self,
            "Nova Reparacao",
            "Criar folha de obra, associar cliente e consumir componentes.",
        )

        # Botões (voltar e configurar taxa horária)

        # Botão configurar preços
        create_toolbar_button(buttons_frame, "Configurar Precos", self.open_cost_settings, role="primary", width=150)

        # Botão voltar
        # Container principal
        main_container = ctk.CTkFrame(self, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=20, pady=(8, 12))

        # Lado esquerdo: Formulário de reparação com scroll e footer fixo
        form_container = ctk.CTkFrame(
            main_container,
            width=410,
            fg_color="#202124",
            corner_radius=8,
            border_width=1,
            border_color="#35363a",
        )
        form_container.pack(side="left", fill="both", expand=False, padx=(0, 12))
        form_container.pack_propagate(False)

        # Título fixo
        form_title = ctk.CTkLabel(
            form_container,
            text="Dados da Reparação",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#f5f5f5",
        )
        form_title.pack(pady=(16, 8))

        # Frame scrollável para o formulário
        scrollable_form = ctk.CTkScrollableFrame(
            form_container,
            fg_color="transparent"
        )
        scrollable_form.pack(fill="both", expand=True, padx=0, pady=0)

        # Usar scrollable_form como parent para todos os campos
        form_frame = scrollable_form

        # SECÇÃO: Pesquisa de Cliente
        client_search_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        client_search_frame.pack(fill="x", padx=18, pady=(0, 8))

        search_label = ctk.CTkLabel(
            client_search_frame,
            text="Pesquisar Cliente (Nome ou Telemóvel):",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#b8b8b8",
            anchor="w"
        )
        search_label.pack(fill="x", pady=(0, 5))

        # Frame para barra de pesquisa e botão
        search_input_frame = ctk.CTkFrame(client_search_frame, fg_color="transparent")
        search_input_frame.pack(fill="x")

        self.client_search_entry = ctk.CTkEntry(
            search_input_frame,
            font=ctk.CTkFont(size=14),
            placeholder_text="Digite nome ou telefone...",
            height=32,
        )
        self.client_search_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.client_search_entry.bind("<KeyRelease>", self.on_client_search)

        # Inicializar Debouncer após criar o widget (precisa de winfo_toplevel)
        def do_client_search():
            query = self.client_search_entry.get().strip()
            if len(query) >= 2:  # Pesquisar apenas se tiver 2+ caracteres
                self.search_clients()
            else:
                # Ocultar resultados se pesquisa muito curta
                self.client_results_frame.pack_forget()

        self.client_search_debouncer = Debouncer(
            do_client_search,
            self.winfo_toplevel(),
            delay=300  # 0.3 segundos = 300ms
        )

        search_button = create_button(
            search_input_frame,
            text="Pesquisar",
            command=self.search_clients,
            role="primary",
            width=100,
            compact=True,
            height=32,
        )
        search_button.pack(side="left")

        # Frame para resultados da pesquisa (dropdown) - COLOCADO IMEDIATAMENTE ABAIXO DA PESQUISA
        self.client_results_frame = ctk.CTkFrame(client_search_frame, fg_color=["#ffffff", "#2b2b2b"])
        self.client_results_frame.pack(fill="x", padx=0, pady=(5, 0))
        self.client_results_frame.pack_forget()  # Ocultar inicialmente

        # Campos de informações do cliente (preenchidos automaticamente)
        self.client_name_entry = self.create_form_field(form_frame, "Nome:", 1)
        self.client_phone_entry = self.create_form_field(form_frame, "Telemóvel:", 2)
        self.client_nif_entry = self.create_form_field(form_frame, "NIF:", 3)
        self.client_address_entry = self.create_form_field(form_frame, "Morada:", 4)

        # Tipo de Equipamento
        problem_label = ctk.CTkLabel(
            form_frame,
            text="Tipo de Equipamento:",
            font=ctk.CTkFont(size=14),
            anchor="w"
        )
        problem_label.pack(padx=20, pady=(10, 5), anchor="w")

        self.problem_summary_entry = ctk.CTkEntry(
            form_frame,
            font=ctk.CTkFont(size=14),
            height=32,
        )
        self.problem_summary_entry.pack(fill="x", padx=18, pady=(0, 8))

        # IMEI / Nº Série
        imei_label = ctk.CTkLabel(
            form_frame,
            text="IMEI / Nº Série:",
            font=ctk.CTkFont(size=14),
            anchor="w"
        )
        imei_label.pack(padx=20, pady=(10, 5), anchor="w")

        self.device_imei_entry = ctk.CTkEntry(
            form_frame,
            font=ctk.CTkFont(size=14),
            placeholder_text="Ex: 123456789012345 ou SN-ABC123",
            height=32,
        )
        self.device_imei_entry.pack(fill="x", padx=18, pady=(0, 8))

        # Nº Garantia / Seguradora
        warranty_label = ctk.CTkLabel(
            form_frame,
            text="Nº Garantia / Seguradora:",
            font=ctk.CTkFont(size=14),
            anchor="w"
        )
        warranty_label.pack(padx=20, pady=(10, 5), anchor="w")

        self.warranty_number_entry = ctk.CTkEntry(
            form_frame,
            font=ctk.CTkFont(size=14),
            placeholder_text="Ex: GAR-2024-001 ou Seguradora XYZ",
            height=32,
        )
        self.warranty_number_entry.pack(fill="x", padx=18, pady=(0, 8))

        # Descrição/Observações (altura reduzida)
        self.description_text = ctk.CTkTextbox(
            form_frame,
            height=82,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#b8b8b8",
            wrap="word"
        )
        desc_label = ctk.CTkLabel(
            form_frame,
            text="Descrição/Observações:",
            font=ctk.CTkFont(size=14),
            anchor="w"
        )
        desc_label.pack(padx=18, pady=(6, 4), anchor="w")
        self.description_text.pack(fill="x", padx=18, pady=(0, 8))

        # Tipo de Mão de Obra (Segmented Button)
        labor_type_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        labor_type_frame.pack(fill="x", padx=20, pady=(10, 5))

        labor_type_label = ctk.CTkLabel(
            labor_type_frame,
            text="Tipo de Mão de Obra:",
            font=ctk.CTkFont(size=14),
            anchor="w"
        )
        labor_type_label.pack(fill="x", pady=(0, 5))

        self.labor_type_segmented = LaborTypeSelector(
            labor_type_frame,
            values=["Mão de Obra 1", "Mão de Obra 2", "Placas"],
            command=self.on_labor_type_changed,
        )
        self.labor_type_segmented.set("Mão de Obra 1")  # Default
        self.labor_type_segmented.pack(fill="x", pady=(0, 10))

        # Horas/Unidades de Trabalho (Label dinâmico)
        self.labor_qty_label = ctk.CTkLabel(
            form_frame,
            text="Horas:",  # Será atualizado dinamicamente
            font=ctk.CTkFont(size=14),
            anchor="w"
        )
        self.labor_qty_label.pack(padx=20, pady=(0, 5), anchor="w")

        self.hours_entry = ctk.CTkEntry(
            form_frame,
            font=ctk.CTkFont(size=14),
            height=32
        )
        self.hours_entry.pack(fill="x", padx=18, pady=(0, 8))
        self.hours_entry.insert(0, "1.0")
        self.hours_entry.bind("<KeyRelease>", lambda _: self.update_total())

        # Horas de Eletricidade
        self.electricity_hours_entry = self.create_form_field(form_frame, "Horas Eletricidade:", 2)
        self.electricity_hours_entry.insert(0, "0.0")
        self.electricity_hours_entry.bind("<KeyRelease>", lambda _: self.update_total())

        # Peso da Encomenda
        self.package_weight_entry = self.create_form_field(form_frame, "Peso da Encomenda (kg):", 2)
        self.package_weight_entry.insert(0, "0.0")
        self.package_weight_entry.bind("<KeyRelease>", lambda _: self.update_total())

        # Toggle Switch: Realizar Testes/Diagnóstico
        test_toggle_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        test_toggle_frame.pack(fill="x", padx=20, pady=(10, 5))

        self.test_toggle = ctk.CTkSwitch(
            test_toggle_frame,
            text="Realizar Testes/Diagnóstico?",
            command=self.toggle_test_fields,
            font=ctk.CTkFont(size=14)
        )
        self.test_toggle.pack(side="left")

        # Frame para campos de teste (inicialmente oculto)
        self.frame_testes = ctk.CTkFrame(form_frame, fg_color="transparent")
        # Não fazer pack inicialmente (oculto por padrão)

        # Horas Gastas em Testes
        horas_teste_label = ctk.CTkLabel(
            self.frame_testes,
            text="Horas Gastas:",
            font=ctk.CTkFont(size=14),
            anchor="w"
        )
        horas_teste_label.pack(padx=20, pady=(10, 5), anchor="w")

        self.horas_teste_entry = ctk.CTkEntry(
            self.frame_testes,
            font=ctk.CTkFont(size=14),
            height=35
        )
        self.horas_teste_entry.insert(0, "1.0")
        self.horas_teste_entry.bind("<KeyRelease>", lambda _: self.update_total())
        self.horas_teste_entry.pack(fill="x", padx=20, pady=(0, 10))

        # Label informativa com taxa atual
        self.test_rate_info_label = ctk.CTkLabel(
            self.frame_testes,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=["#666666", "#999999"],
            anchor="w"
        )
        self.test_rate_info_label.pack(padx=20, pady=(0, 10), anchor="w")
        # Atualizar texto da label com taxa atual
        self.update_test_rate_label()

        # Taxas informativas (label)
        rate_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        rate_frame.pack(fill="x", padx=20, pady=(5, 10))

        self.rate_label = ctk.CTkLabel(
            rate_frame,
            text="Mão de Obra 1: 30.00 €/h | Mão de Obra 2: 45.00 €/h | Placas: 50.00 €/un | Eletricidade: 0.50 €/h",
            font=ctk.CTkFont(size=11),
            text_color=["#666666", "#999999"],
            anchor="w"
        )
        self.rate_label.pack(side="left")

        # Carregar taxas
        self.load_rates()

        # Footer fixo (fora do scrollable)
        footer_frame = ctk.CTkFrame(
            form_container,
            fg_color="#181c20",
            corner_radius=0,
            border_width=1,
            border_color="#35363a",
        )
        footer_frame.pack(side="bottom", fill="x", padx=0, pady=0)

        # Total no footer
        total_frame = ctk.CTkFrame(footer_frame, fg_color="transparent")
        total_frame.pack(fill="x", padx=18, pady=(10, 6))

        total_label = ctk.CTkLabel(
            total_frame,
            text="Total:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#b8b8b8",
        )
        total_label.pack(side="left")

        self.total_value_label = ctk.CTkLabel(
            total_frame,
            text="0.00 €",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=["#FF5722", "#FF5722"]
        )
        self.total_value_label.pack(side="right")

        # Wrapper seguro para comandos de botões
        def safe_command(func):
            """Wrapper que garante que comandos não bloqueiam o event loop"""
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    from tkinter import messagebox
                    messagebox.showerror("Erro", f"Erro inesperado: {str(e)}")
            return wrapper

        # Botão de submissão no footer
        submit_button = create_button(
            footer_frame,
            text="Salvar e Finalizar Reparação",
            command=safe_command(self.submit_repair),
            role="primary",
            height=42,
        )
        submit_button.pack(fill="x", padx=18, pady=(0, 14))

        # Lado direito: Seleção de componentes (modelo "carrinho de compras")
        components_frame = ctk.CTkFrame(
            main_container,
            fg_color="#202124",
            corner_radius=8,
            border_width=1,
            border_color="#35363a",
        )
        components_frame.pack(side="right", fill="both", expand=True)
        components_frame.grid_columnconfigure(0, weight=1)
        components_frame.grid_rowconfigure(3, weight=2, minsize=120)
        components_frame.grid_rowconfigure(6, weight=1, minsize=105)

        # Título
        components_title = ctk.CTkLabel(
            components_frame,
            text="Componentes Utilizados",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#f5f5f5",
        )
        components_title.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 8))

        # Barra de pesquisa (topo)
        search_frame = ctk.CTkFrame(components_frame, fg_color="transparent")
        search_frame.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 8))

        search_label = ctk.CTkLabel(
            search_frame,
            text="Pesquisar:",
            font=ctk.CTkFont(size=14)
        )
        search_label.pack(side="left", padx=(0, 10))

        self.search_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text="Código ou nome...",
            font=ctk.CTkFont(size=14),
            width=300
        )
        self.search_entry.pack(side="left", fill="x", expand=True)

        # Debounce manual para pesquisa de componentes
        self.COMPONENT_SEARCH_DELAY = 300
        self._component_search_after_id = None
        self._component_auto_select_next = False

        def on_component_search_key_release(event=None):
            """Dispara pesquisa com debounce para evitar queries excessivas."""
            try:
                self._component_auto_select_next = False
                if self._component_search_after_id is not None:
                    self.after_cancel(self._component_search_after_id)
                self._component_search_after_id = self.after(
                    self.COMPONENT_SEARCH_DELAY,
                    lambda: self.refresh_components_list(force=True)
                )
            except Exception:
                pass

        def on_component_search_return(event=None):
            """Enter / leitor de código de barras: tentar auto-selecionar por código."""
            self._component_auto_select_next = True
            self.refresh_components_list(force=True)

        self.search_entry.bind("<KeyRelease>", on_component_search_key_release)
        self.search_entry.bind("<Return>", on_component_search_return)

        # Frame de resultados (meio) - começa vazio
        list_title = ctk.CTkLabel(
            components_frame,
            text="Resultados da Pesquisa",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        list_title.grid(row=2, column=0, sticky="w", padx=20, pady=(6, 5))

        scrollable_frame = ctk.CTkScrollableFrame(
            components_frame,
            height=160,
            fg_color="#151617",
            corner_radius=8,
            border_width=1,
            border_color="#35363a",
        )
        scrollable_frame.grid(row=3, column=0, sticky="nsew", padx=18, pady=(0, 8))

        self.components_list_container = scrollable_frame

        # Indicador de carregamento (criado uma vez)
        self._loading_label = ctk.CTkLabel(
            self.components_list_container,
            text="A carregar...",
            font=ctk.CTkFont(size=14),
            text_color=["#666666", "#999999"]
        )

        # Área de ação (componente selecionado + quantidade + adicionar)
        action_frame = ctk.CTkFrame(components_frame, fg_color="transparent")
        action_frame.grid(row=4, column=0, sticky="ew", padx=18, pady=(0, 8))
        action_frame.pack_propagate(False)

        self.component_action_frame = action_frame
        self.current_selected_component = None

        self.selected_component_label = ctk.CTkLabel(
            action_frame,
            text="Nenhum componente selecionado",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w"
        )
        self.selected_component_label.pack(fill="x", pady=(0, 5))

        qty_row = ctk.CTkFrame(action_frame, fg_color="transparent")
        qty_row.pack(fill="x", pady=(0, 5))

        qty_label = ctk.CTkLabel(
            qty_row,
            text="Quantidade:",
            font=ctk.CTkFont(size=12)
        )
        qty_label.pack(side="left", padx=(0, 5))

        self.component_qty_entry = ctk.CTkEntry(
            qty_row,
            width=80,
            font=ctk.CTkFont(size=13)
        )
        self.component_qty_entry.pack(side="left")
        self.component_qty_entry.insert(0, "1")

        def on_add_selected_component():
            """Adiciona o componente selecionado ao 'carrinho'."""
            if not self.current_selected_component:
                messagebox.showwarning("Atenção", "Nenhum componente selecionado.")
                return
            # Reutilizar lógica existente (add_component_to_repair)
            previous_selection = list(self.selected_components)
            self.add_component_to_repair(self.current_selected_component, self.component_qty_entry)
            if self.selected_components == previous_selection:
                return
            # Resetar seleção para próxima pesquisa
            self._clear_component_selection()
            # Limpar resultados para preparar próxima pesquisa
            for widget in self.components_list_container.winfo_children():
                widget.destroy()
            self.search_entry.delete(0, "end")
            self.search_entry.focus_set()

        self.add_selected_button = create_button(
            action_frame,
            text="Adicionar à Reparação",
            command=on_add_selected_component,
            role="success",
            width=170,
            height=35,
        )
        self.add_selected_button.pack(pady=(0, 5), anchor="w")
        self.component_action_frame.grid_remove()

        # Lista de componentes selecionados (carrinho)
        selected_title = ctk.CTkLabel(
            components_frame,
            text="Componentes Selecionados",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        selected_title.grid(row=5, column=0, sticky="w", padx=18, pady=(4, 5))

        selected_scrollable = ctk.CTkScrollableFrame(
            components_frame,
            height=120,
            fg_color="#151617",
            corner_radius=8,
            border_width=1,
            border_color="#35363a",
        )
        selected_scrollable.grid(row=6, column=0, sticky="nsew", padx=18, pady=(0, 16))

        self.selected_list_container = selected_scrollable

    def on_labor_type_changed(self, value):
        """Callback quando o tipo de mão de obra muda"""
        # Safety check: ensure label exists before accessing it
        if not hasattr(self, 'labor_qty_label') or self.labor_qty_label is None:
            return

        # Atualizar label dinamicamente
        if value == "Placas":
            self.labor_qty_label.configure(text="Unidades:")
        else:
            self.labor_qty_label.configure(text="Horas:")

        # Recalcular total
        self.update_total()

    def create_form_field(self, parent, label_text, row):
        """Cria um campo do formulário"""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=18, pady=(5, 7))

        label = ctk.CTkLabel(
            frame,
            text=label_text,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#b8b8b8",
            anchor="w"
        )
        label.pack(fill="x", pady=(0, 4))

        entry = ctk.CTkEntry(
            frame,
            font=ctk.CTkFont(size=14),
            height=32
        )
        entry.pack(fill="x")

        return entry

    def refresh_data(self, force: bool = True):
        """
        Método público para atualizar dados da página
        Chamado quando navega para esta página para garantir dados frescos

        Args:
            force: Se True, força refresh mesmo se dados não mudaram
        """
        # Limpar cache para garantir dados frescos da base de dados
        if force:
            self.components_cache = {}
            self._components_hash = None

        # Usar overlay de carregamento profissional
        self.refresh_components_list(force=force, show_overlay=True)

    def refresh_components_list(self, force: bool = False, show_overlay: bool = False):
        """
        Atualiza a lista de componentes disponíveis (modo pesquisa-first).

        - Não carrega toda a tabela.
        - Usa pesquisa otimizada (search_stock_smart) com limite pequeno.

        Args:
            force: Se True, força refresh mesmo se dados não mudaram
            show_overlay: (mantido por compatibilidade, ignorado neste fluxo)
        """
        # Safety check: ensure search_entry exists before accessing it
        if not hasattr(self, 'search_entry') or self.search_entry is None:
            return

        if self.is_loading:
            return

        self.is_loading = True

        # Obter termo de pesquisa
        try:
            search_term = self.search_entry.get().strip()
        except AttributeError:
            # search_entry not yet initialized, skip this call
            self.is_loading = False
            return

        auto_select = getattr(self, "_component_auto_select_next", False)
        # Reset auto-select flag after reading
        self._component_auto_select_next = False

        def db_operation():
            # Se não houver termo de pesquisa, não carregar nada
            if not search_term:
                return []
            # Buscar componentes (em background thread) usando pesquisa otimizada
            limit = 10 if auto_select else 5
            components = self.app.db_manager.search_stock_smart(search_term, limit=limit)
            # Mostrar tambem componentes sem stock para permitir repor sem sair da folha de obra.
            components = [
                component
                for component in (_normalize_component(c) for c in components)
                if component.get("id") is not None
            ]
            return components

        def callback(components, error):
            self.is_loading = False

            if error:
                messagebox.showerror("Erro", f"Erro ao carregar componentes: {str(error)}")
                return

            # Safety check: ensure components_list_container exists
            if not hasattr(self, 'components_list_container') or not self.components_list_container.winfo_exists():
                return

            # Limpar lista (com segurança)
            try:
                for widget in self.components_list_container.winfo_children():
                    if widget.winfo_exists():
                        widget.destroy()
            except Exception:
                pass  # Ignorar erros se widgets foram destruídos

            # Atualizar cache básica
            for comp in components:
                self.components_cache[comp["id"]] = comp

            # Nenhuma pesquisa digitada: mostrar mensagem de ajuda
            if not search_term:
                hint_label = ctk.CTkLabel(
                    self.components_list_container,
                    text="Digite um código ou nome para pesquisar componentes...",
                    font=ctk.CTkFont(size=13),
                    text_color=["#666666", "#999999"],
                    anchor="w"
                )
                hint_label.pack(pady=20, padx=10, anchor="w")
                # Reset seleção
                self._clear_component_selection()
                return

            # Nenhum componente encontrado
            if not components:
                no_data_label = ctk.CTkLabel(
                    self.components_list_container,
                    text="Nenhum componente disponível com esse critério.",
                    font=ctk.CTkFont(size=14),
                    text_color=["#666666", "#999999"]
                )
                no_data_label.pack(pady=20)
                return

            # Otimização para scanner: auto-selecionar se houver match exato de código
            if auto_select:
                term_lower = search_term.lower().strip()
                exact_matches = [
                    c for c in components
                    if str(c.get("code", "")).lower().strip() == term_lower
                ]
                if len(exact_matches) == 1:
                    comp = exact_matches[0]
                    if comp.get("qty", 0) > 0:
                        # Simular seleção direta
                        self._select_component_for_repair(comp)
                        return

            # Renderizar resultados (máx 5 ou 10, já limitado no db_operation)
            for component in components:
                try:
                    self.create_component_item(component)
                except Exception:
                    if not self.components_list_container.winfo_exists():
                        break
                    continue

        # Executar em background thread (overlay não é necessário aqui)
        # Mostrar indicador de carregamento simples (para pesquisa)
        if hasattr(self, '_loading_label') and self._loading_label.winfo_exists():
            try:
                self._loading_label.pack(pady=20)
            except Exception:
                pass  # Widget foi destruído, ignorar
        run_db_operation(self.app.root, db_operation, callback)

    def create_component_item(self, component: dict):
        """Cria um item na lista de resultados de pesquisa de componentes."""
        # Safety check: ensure container exists
        if not hasattr(self, 'components_list_container') or not self.components_list_container.winfo_exists():
            return

        component = _normalize_component(component)
        if component.get("id") is None:
            return
        has_stock = component.get("qty", 0) > 0

        item_frame = ctk.CTkFrame(
            self.components_list_container,
            fg_color="#202124",
            corner_radius=6,
            border_width=1,
            border_color="#303236",
        )
        item_frame.pack(fill="x", pady=3, padx=5)

        info_frame = ctk.CTkFrame(item_frame, fg_color="transparent")
        info_frame.pack(side="left", fill="x", expand=True, padx=10, pady=8)

        name_label = ctk.CTkLabel(
            info_frame,
            text=f"{component['code']} - {component['name']}",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w"
        )
        name_label.pack(fill="x")

        details_label = ctk.CTkLabel(
            info_frame,
            text=f"Preco: {component['price']:.2f} EUR | Stock: {component['qty']}" if has_stock else "Sem stock registado",
            font=ctk.CTkFont(size=12),
            text_color="#c9ced6" if has_stock else "#f59e0b",
            anchor="w"
        )
        details_label.pack(fill="x")

        def on_select(local_comp=component):
            """Seleciona componente e mostra área de quantidade."""
            if local_comp.get("qty", 0) <= 0:
                self.open_quick_stock_entry(local_comp)
                return
            self._select_component_for_repair(local_comp)

        # Clique no item seleciona o componente
        name_label.bind("<Button-1>", lambda e, lc=component: on_select(lc))
        details_label.bind("<Button-1>", lambda e, lc=component: on_select(lc))

        # Botão explícito de seleção/reposição de stock
        select_button = create_table_action_button(
            item_frame,
            text="Selecionar" if has_stock else "Adicionar stock",
            command=lambda lc=component: on_select(lc) if has_stock else self.open_quick_stock_entry(lc),
            role="success" if has_stock else "warning",
            width=90 if has_stock else 118,
        )
        select_button.pack_configure(side="right", padx=10, pady=5)

    def _select_component_for_repair(self, component: dict):
        """Mostra o painel de quantidade para o componente selecionado."""
        component = _normalize_component(component)
        if component.get("id") is None or component.get("qty", 0) <= 0:
            return

        self.current_selected_component = component
        self.selected_component_label.configure(
            text=f"[{component['code']}] {component['name']} (Stock Atual: {component['qty']})"
        )
        self.component_qty_entry.delete(0, "end")
        self.component_qty_entry.insert(0, "1")
        self.component_action_frame.grid()
        self.component_qty_entry.focus_set()

    def _clear_component_selection(self):
        """Esconde o painel de quantidade quando nao ha componente selecionado."""
        self.current_selected_component = None
        self.selected_component_label.configure(text="Nenhum componente selecionado")
        self.component_qty_entry.delete(0, "end")
        self.component_qty_entry.insert(0, "1")
        self.component_action_frame.grid_remove()

    def open_quick_stock_entry(self, component: dict):
        """Permite adicionar stock a um componente sem sair da folha de obra."""
        component = _normalize_component(component)
        if component.get("id") is None:
            messagebox.showerror("Erro", "Componente invalido. Verifique os dados do stock.")
            return

        dialog = ctk.CTkToplevel(self.app.root)
        dialog.title("Adicionar Stock")
        dialog.geometry("500x360")
        dialog.minsize(460, 340)
        dialog.configure(fg_color="#151617")
        dialog.transient(self.app.root)
        dialog.grab_set()

        main_frame = create_popup_card(dialog)

        title_label = ctk.CTkLabel(
            main_frame,
            text="Adicionar stock",
            font=ctk.CTkFont(size=19, weight="bold"),
            text_color="#f5f5f5",
            anchor="w",
        )
        title_label.pack(fill="x", padx=18, pady=(16, 4))

        subtitle_label = ctk.CTkLabel(
            main_frame,
            text="Atualizar quantidade antes de usar na folha de obra.",
            font=ctk.CTkFont(size=12),
            text_color="#b8b8b8",
            anchor="w",
        )
        subtitle_label.pack(fill="x", padx=18, pady=(0, 10))

        component_frame = ctk.CTkFrame(
            main_frame,
            fg_color="#151617",
            corner_radius=8,
            border_width=1,
            border_color="#35363a",
        )
        component_frame.pack(fill="x", padx=18, pady=(0, 10))
        component_frame.grid_columnconfigure(0, weight=1)

        component_name = ctk.CTkLabel(
            component_frame,
            text=f"{component['code']} - {component['name']}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#f5f5f5",
            anchor="w",
        )
        component_name.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 2))

        current_stock_label = ctk.CTkLabel(
            component_frame,
            text=f"Stock atual: {component['qty']}",
            font=ctk.CTkFont(size=12),
            text_color="#b8b8b8",
            anchor="w",
        )
        current_stock_label.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))

        quantity_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        quantity_frame.pack(fill="x", padx=18, pady=(0, 8))
        quantity_frame.grid_columnconfigure(1, weight=1)

        qty_label = ctk.CTkLabel(
            quantity_frame,
            text="Adicionar",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#b8b8b8",
            anchor="w",
        )
        qty_label.grid(row=0, column=0, sticky="w", padx=(0, 10), pady=0)

        qty_entry = ctk.CTkEntry(quantity_frame, font=ctk.CTkFont(size=14), height=34, width=120)
        qty_entry.grid(row=0, column=1, sticky="w", pady=0)
        qty_entry.insert(0, "1")

        units_label = ctk.CTkLabel(
            quantity_frame,
            text="unidades",
            font=ctk.CTkFont(size=12),
            text_color="#b8b8b8",
            anchor="w",
        )
        units_label.grid(row=0, column=2, sticky="w", padx=(10, 0), pady=0)

        preview_label = ctk.CTkLabel(
            main_frame,
            text="Novo stock: -",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#16A34A",
            anchor="w",
        )
        preview_label.pack(fill="x", padx=18, pady=(0, 0))

        def update_preview(_event=None):
            try:
                qty_to_add = int(qty_entry.get().strip())
                if qty_to_add <= 0:
                    raise ValueError
                preview_label.configure(text=f"Novo stock: {component['qty'] + qty_to_add}")
            except ValueError:
                preview_label.configure(text="Novo stock: -")

        qty_entry.bind("<KeyRelease>", update_preview)
        update_preview()

        buttons_frame = create_action_footer(main_frame)

        def save_stock():
            try:
                qty_to_add = int(qty_entry.get().strip())
                if qty_to_add <= 0:
                    messagebox.showwarning("Atenção", "A quantidade deve ser maior que zero.")
                    return
            except ValueError:
                messagebox.showerror("Erro", "Por favor, insira uma quantidade valida.")
                return

            def db_operation():
                return self.app.db_manager.add_stock_quantity(component["id"], qty_to_add)

            def callback(new_qty, error):
                if error:
                    messagebox.showerror("Erro", f"Erro ao adicionar stock: {str(error)}")
                    return

                if new_qty is None:
                    messagebox.showerror("Erro", "Nao foi possivel adicionar stock ao componente.")
                    return

                updated_component = dict(component)
                updated_component["qty"] = int(new_qty)
                self.components_cache[updated_component["id"]] = updated_component
                self._select_component_for_repair(updated_component)
                dialog.destroy()
                self.refresh_components_list(force=True)

            run_db_operation(self.app.root, db_operation, callback)

        create_action_button(buttons_frame, "Guardar", save_stock, role="success", width=120)
        create_action_button(buttons_frame, "Cancelar", dialog.destroy, role="secondary", width=110)
        apply_modern_style(dialog)
        dialog.bind("<Return>", lambda _event: save_stock())

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        qty_entry.focus_set()

    def add_component_to_repair(self, component: dict, qty_entry):
        """Adiciona um componente à lista de componentes utilizados"""
        try:
            component = _normalize_component(component)
            if component.get("id") is None:
                messagebox.showerror("Erro", "Componente invalido. Verifique os dados do stock.")
                return False

            qty = int(qty_entry.get())
            if qty <= 0:
                messagebox.showwarning("Atenção", "Quantidade deve ser maior que zero.")
                return

            if qty > component["qty"]:
                if messagebox.askyesno(
                    "Stock insuficiente",
                    f"Disponivel: {component['qty']}.\n\nQuer adicionar stock a este componente agora?",
                ):
                    self.open_quick_stock_entry(component)
                return

            # Verificar se já existe
            for i, (comp_id, existing_qty) in enumerate(self.selected_components):
                if comp_id == component["id"]:
                    new_qty = existing_qty + qty
                    if new_qty > component["qty"]:
                        if messagebox.askyesno(
                            "Stock insuficiente",
                            f"Disponivel: {component['qty']}.\n\nQuer adicionar stock a este componente agora?",
                        ):
                            self.open_quick_stock_entry(component)
                        return
                    self.selected_components[i] = (comp_id, new_qty)
                    self.refresh_selected_list()
                    self.update_total()
                    return

            # Adicionar novo
            self.selected_components.append((component["id"], qty))
            self.refresh_selected_list()
            self.update_total()
            qty_entry.delete(0, "end")
            qty_entry.insert(0, "1")
        except ValueError:
            messagebox.showerror("Erro", "Por favor, insira uma quantidade válida!")

    def refresh_selected_list(self):
        """Atualiza a lista de componentes selecionados"""
        # Limpar lista
        for widget in self.selected_list_container.winfo_children():
            widget.destroy()

        if not self.selected_components:
            no_data_label = ctk.CTkLabel(
                self.selected_list_container,
                text="Nenhum componente selecionado",
                font=ctk.CTkFont(size=12),
                text_color=["#666666", "#999999"]
            )
            no_data_label.pack(pady=20)
            return

        # Obter IDs que não estão em cache
        missing_ids = [comp_id for comp_id, _ in self.selected_components
                      if comp_id not in self.components_cache]

        # Buscar componentes em falta em batch
        if missing_ids:
            batch_components = self.app.db_manager.get_components_by_ids(missing_ids)
            self.components_cache.update(_normalize_components_by_id(batch_components))

        # Adicionar componentes selecionados
        for comp_id, qty in self.selected_components:
            component = _normalize_component(self.components_cache.get(comp_id))
            if component:
                self.create_selected_item(component, qty)

    def create_selected_item(self, component: dict, qty: int):
        """Cria um item na lista de componentes selecionados"""
        component = _normalize_component(component)
        if component.get("id") is None:
            return

        item_frame = ctk.CTkFrame(self.selected_list_container)
        item_frame.pack(fill="x", pady=3)

        # Informações
        info_frame = ctk.CTkFrame(item_frame, fg_color="transparent")
        info_frame.pack(side="left", fill="x", expand=True, padx=10, pady=8)

        name_label = ctk.CTkLabel(
            info_frame,
            text=f"{component['code']} - {component['name']}",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w"
        )
        name_label.pack(fill="x")

        subtotal = component["price"] * qty
        details_label = ctk.CTkLabel(
            info_frame,
            text=f"Qtd: {qty} x {component['price']:.2f} € = {subtotal:.2f} €",
            font=ctk.CTkFont(size=11),
            text_color=["#666666", "#999999"],
            anchor="w"
        )
        details_label.pack(fill="x")

        # Frame para botões (decrease e remove)
        buttons_frame = ctk.CTkFrame(item_frame, fg_color="transparent")
        buttons_frame.pack(side="right", padx=10, pady=8)

        # Botão remover (com wrapper seguro) - Pack primeiro para ficar à direita
        def safe_remove_command(comp_id):
            """Wrapper seguro para remover componente"""
            try:
                self.remove_component_from_repair(comp_id)
            except Exception:
                pass  # Ignorar erros para não quebrar o event loop

        remove_button = create_table_action_button(
            buttons_frame,
            text="X",
            command=lambda: safe_remove_command(component["id"]),
            role="danger",
            width=36,
        )

        # Botão diminuir quantidade (com wrapper seguro) - Pack depois para ficar à esquerda do delete
        def safe_decrease_command(comp_id):
            """Wrapper seguro para diminuir quantidade"""
            try:
                self.decrease_component_qty(comp_id)
            except Exception:
                pass  # Ignorar erros para não quebrar o event loop

        # Mostrar botão "-" apenas se quantidade > 1
        if qty > 1:
            decrease_button = create_table_action_button(
                buttons_frame,
                text="-",
                command=lambda: safe_decrease_command(component["id"]),
                role="warning",
                width=36,
            )

    def decrease_component_qty(self, component_id: int):
        """
        Diminui a quantidade de um componente selecionado em 1
        Só funciona se a quantidade for maior que 1

        Args:
            component_id: ID do componente a diminuir
        """
        # Encontrar o componente na lista
        for i, (comp_id, qty) in enumerate(self.selected_components):
            if comp_id == component_id:
                # Verificar se quantidade > 1
                if qty > 1:
                    # Diminuir quantidade em 1
                    new_qty = qty - 1
                    self.selected_components[i] = (comp_id, new_qty)
                    # Atualizar lista e total
                    self.refresh_selected_list()
                    self.update_total()
                # Se quantidade é 1, não fazer nada (usuário deve usar botão remover)
                break

    def remove_component_from_repair(self, component_id: int):
        """Remove um componente da lista de selecionados"""
        self.selected_components = [(cid, qty) for cid, qty in self.selected_components if cid != component_id]
        self.refresh_selected_list()
        self.update_total()

    def calculate_transport_cost(self, weight: float) -> float:
        """
        Calcula o custo de transporte baseado no peso e nas regras configuradas

        Args:
            weight: Peso da encomenda em kg

        Returns:
            Custo de transporte em euros
        """
        if weight <= 0:
            return 0.0

        # Obter regras de transporte
        rules = self.app.db_manager.get_transport_rules()
        if not rules:
            return 0.0

        # Suportar múltiplos formatos (compatibilidade)
        # Formato novo (simples): {"max": X, "price": Y}
        # Formato antigo: {"max_weight": X, "price": Y} ou {"min": A, "max": B, "price": Y}

        # Normalizar para formato simples
        normalized_rules = []
        for rule in rules:
            if "max" in rule and "max_weight" not in rule:
                # Formato novo simples: {"max": X, "price": Y}
                normalized_rules.append({"max": rule.get("max", 0), "price": rule.get("price", 0)})
            elif "max_weight" in rule:
                # Formato antigo: {"max_weight": X, "price": Y}
                normalized_rules.append({"max": rule.get("max_weight", 0), "price": rule.get("price", 0)})
            elif "max" in rule and "min" in rule:
                # Formato com min: {"min": A, "max": B, "price": Y} -> usar apenas max
                normalized_rules.append({"max": rule.get("max", 0), "price": rule.get("price", 0)})

        if not normalized_rules:
            return 0.0

        # Ordenar por max (crescente)
        sorted_rules = sorted(normalized_rules, key=lambda x: x.get("max", 0))

        # Encontrar a regra apropriada usando lógica de cadeia
        # Cada regra cobre: previous_max < weight <= current_max
        previous_max = 0.0
        for rule in sorted_rules:
            max_weight = rule.get("max", 0.0)
            if previous_max < weight <= max_weight:
                return rule.get("price", 0.0)
            previous_max = max_weight

        # Se peso excede todas as regras, usar o preço da regra mais alta
        return sorted_rules[-1].get("price", 0.0)

    def update_total(self):
        """Calcula e atualiza o total (Peças + Mão de Obra + Eletricidade + Transporte)"""
        # Safety check: ensure UI widgets exist before accessing them
        if not hasattr(self, 'hours_entry') or not hasattr(self, 'labor_type_segmented'):
            return

        # Calcular total de peças
        parts_total = 0.0
        if self.selected_components:
            # Obter IDs que não estão em cache
            missing_ids = [comp_id for comp_id, _ in self.selected_components
                          if comp_id not in self.components_cache]

            # Buscar componentes em falta em batch
            if missing_ids:
                batch_components = self.app.db_manager.get_components_by_ids(missing_ids)
                self.components_cache.update(_normalize_components_by_id(batch_components))

            # Calcular total de peças
            for comp_id, qty in self.selected_components:
                component = _normalize_component(self.components_cache.get(comp_id))
                if component:
                    parts_total += component["price"] * qty

        # Calcular mão de obra (baseado no tipo selecionado)
        try:
            qty = float(self.hours_entry.get().strip().replace(",", "."))
            if qty < 0:
                qty = 0.0
        except (ValueError, AttributeError):
            qty = 0.0

        # Obter tipo selecionado e taxa correspondente
        try:
            labor_type_selected = self.labor_type_segmented.get()
        except AttributeError:
            labor_type_selected = "Mão de Obra 1"  # Fallback

        try:
            if labor_type_selected == "Mão de Obra 1":
                rate = float(self.app.db_manager.get_setting("labor_rate_1", "30.0"))
            elif labor_type_selected == "Mão de Obra 2":
                rate = float(self.app.db_manager.get_setting("labor_rate_2", "45.0"))
            elif labor_type_selected == "Placas":
                rate = float(self.app.db_manager.get_setting("placas_price", "50.0"))
            else:
                rate = 30.0  # Fallback
        except:
            rate = 30.0

        labor_total = qty * rate

        # Calcular custo de eletricidade
        try:
            if hasattr(self, 'electricity_hours_entry'):
                elec_hours = float(self.electricity_hours_entry.get().strip().replace(",", "."))
                if elec_hours < 0:
                    elec_hours = 0.0
            else:
                elec_hours = 0.0
        except (ValueError, AttributeError):
            elec_hours = 0.0

        try:
            elec_rate = float(self.app.db_manager.get_setting("electricity_rate", "0.50"))
        except:
            elec_rate = 0.50

        elec_total = elec_hours * elec_rate

        # Calcular custo de transporte
        try:
            if hasattr(self, 'package_weight_entry'):
                weight = float(self.package_weight_entry.get().strip().replace(",", "."))
                if weight < 0:
                    weight = 0.0
            else:
                weight = 0.0
        except (ValueError, AttributeError):
            weight = 0.0

        transport_total = self.calculate_transport_cost(weight)

        # Calcular custo de testes/diagnóstico (se toggle estiver ativo)
        test_total = 0.0
        if hasattr(self, 'test_toggle') and self.test_toggle.get():
            try:
                if hasattr(self, 'horas_teste_entry'):
                    horas_teste = float(self.horas_teste_entry.get().strip().replace(",", "."))
                    if horas_teste > 0:
                        # Usar taxa global configurada
                        preco_hora_teste = self.load_hourly_rate()
                        test_total = horas_teste * preco_hora_teste
            except (ValueError, AttributeError):
                test_total = 0.0

        # Calcular total: Peças + Mão de Obra + Eletricidade + Transporte + Testes
        total = parts_total + labor_total + elec_total + transport_total + test_total

        # SAFETY CHECK: Only update UI if the label exists
        if hasattr(self, 'total_value_label') and self.total_value_label is not None:
            self.total_value_label.configure(text=f"{total:.2f} €")

    def update_test_rate_label(self):
        """Atualiza a label informativa com a taxa atual de testes"""
        if hasattr(self, 'test_rate_info_label'):
            current_rate = self.load_hourly_rate()
            self.test_rate_info_label.configure(text=f"Taxa em vigor: {current_rate:.2f} €/h")

    def toggle_test_fields(self):
        """Mostra ou oculta os campos de testes/diagnóstico baseado no estado do toggle"""
        if not hasattr(self, 'test_toggle') or not hasattr(self, 'frame_testes'):
            return

        try:
            # CTkSwitch.get() retorna True/False (ou 1/0)
            is_on = self.test_toggle.get()

            if is_on:
                # Toggle ON: Mostrar campos
                self.frame_testes.pack(fill="x", padx=20, pady=(0, 10))
                # Atualizar label com taxa atual
                self.update_test_rate_label()
            else:
                # Toggle OFF: Ocultar campos
                self.frame_testes.pack_forget()

            # Recalcular total após mostrar/ocultar
            self.update_total()
        except Exception as e:
            print(f"Erro ao alternar campos de teste: {e}")

    def on_client_search(self, _=None):
        """Callback para pesquisa de clientes (com debounce)"""
        # Chamar o debouncer (que já tem a função configurada)
        if hasattr(self, 'client_search_debouncer'):
            self.client_search_debouncer()

    def search_clients(self):
        """Pesquisa clientes e exibe resultados"""
        query = self.client_search_entry.get().strip()
        if not query or len(query) < 2:
            self.client_results_frame.pack_forget()
            return

        def db_operation():
            return self.app.db_manager.search_client(query)

        def callback(clients, error):
            if error:
                return

            # Limpar resultados anteriores
            for widget in self.client_results_frame.winfo_children():
                widget.destroy()

            if not clients:
                no_results = ctk.CTkLabel(
                    self.client_results_frame,
                    text="Nenhum cliente encontrado",
                    font=ctk.CTkFont(size=12),
                    text_color=["#999999", "#666666"]
                )
                no_results.pack(pady=10)
                self.client_results_frame.pack(fill="x", padx=0, pady=(5, 0))
                return

            # Mostrar resultados (máximo 5)
            max_results = min(5, len(clients))
            for i, client in enumerate(clients[:max_results]):
                client_frame = ctk.CTkFrame(self.client_results_frame, fg_color="transparent")
                client_frame.pack(fill="x", padx=5, pady=2)

                client_info = f"{client.get('name', 'N/A')} - {client.get('phone', 'N/A')}"
                client_button = ctk.CTkButton(
                    client_frame,
                    text=client_info,
                    command=lambda c=client: self.select_client(c),
                    font=ctk.CTkFont(size=12),
                    fg_color=["#e0e0e0", "#3a3a3a"],
                    hover_color=["#d0d0d0", "#4a4a4a"],
                    anchor="w",
                    height=30
                )
                client_button.pack(fill="x")

            self.client_results_frame.pack(fill="x", padx=0, pady=(5, 0))

        run_db_operation(self.app.root, db_operation, callback)

    def select_client(self, client: dict):
        """Seleciona um cliente e preenche os campos"""
        self.current_client_id = client.get("id")

        # Preencher campos
        self.client_name_entry.delete(0, "end")
        self.client_name_entry.insert(0, client.get("name", ""))

        self.client_phone_entry.delete(0, "end")
        self.client_phone_entry.insert(0, client.get("phone", ""))

        self.client_nif_entry.delete(0, "end")
        self.client_nif_entry.insert(0, client.get("nif", ""))

        self.client_address_entry.delete(0, "end")
        self.client_address_entry.insert(0, client.get("address", ""))

        # Limpar pesquisa e ocultar resultados
        self.client_search_entry.delete(0, "end")
        self.client_results_frame.pack_forget()

    def load_rates(self):
        """Carrega e exibe as taxas atuais"""
        try:
            labor_rate_1 = float(self.app.db_manager.get_setting("labor_rate_1", "30.0"))
            labor_rate_2 = float(self.app.db_manager.get_setting("labor_rate_2", "45.0"))
            placas_price = float(self.app.db_manager.get_setting("placas_price", "50.0"))
            elec_rate = float(self.app.db_manager.get_setting("electricity_rate", "0.50"))
            self.rate_label.configure(
                text=f"Mão de Obra 1: {labor_rate_1:.2f} €/h | Mão de Obra 2: {labor_rate_2:.2f} €/h | Placas: {placas_price:.2f} €/un | Eletricidade: {elec_rate:.2f} €/h"
            )
        except:
            self.rate_label.configure(
                text="Mão de Obra 1: 30.00 €/h | Mão de Obra 2: 45.00 €/h | Placas: 50.00 €/un | Eletricidade: 0.50 €/h"
            )

    def load_hourly_rate(self) -> float:
        """
        Carrega o preço por hora padrão para testes/diagnóstico da base de dados.

        Returns:
            Preço por hora (float, default 20.0)
        """
        try:
            rate_str = self.app.db_manager.get_setting("test_hourly_rate", "20.00")
            return float(rate_str)
        except (ValueError, TypeError):
            return 20.0

    def open_cost_settings(self):
        """Abre diálogo completo para configurar preços (taxas horárias e regras de transporte)"""
        try:
            import json

            # Obter valores atuais
            current_labor_rate_1 = float(self.app.db_manager.get_setting("labor_rate_1", "30.0"))
            current_labor_rate_2 = float(self.app.db_manager.get_setting("labor_rate_2", "45.0"))
            current_placas_price = float(self.app.db_manager.get_setting("placas_price", "50.0"))
            current_elec_rate = float(self.app.db_manager.get_setting("electricity_rate", "0.50"))
            current_test_rate = float(self.app.db_manager.get_setting("test_hourly_rate", "20.00"))
            current_rules = self.app.db_manager.get_transport_rules()

            # Criar janela de diálogo
            dialog = ctk.CTkToplevel(self.app.root)
            dialog.title("Configurar Preços")
            dialog.geometry("760x680")
            dialog.minsize(720, 620)
            dialog.configure(fg_color="#151617")
            dialog.transient(self.app.root)
            dialog.resizable(True, True)

            header = ctk.CTkFrame(
                dialog,
                fg_color="#202124",
                corner_radius=8,
                border_width=1,
                border_color="#35363a",
            )
            header.pack(fill="x", padx=20, pady=(20, 12))

            ctk.CTkLabel(
                header,
                text="Configurar Precos",
                font=ctk.CTkFont(size=21, weight="bold"),
                text_color="#f5f5f5",
                anchor="w",
            ).pack(fill="x", padx=16, pady=(12, 2))

            ctk.CTkLabel(
                header,
                text="Taxas de mao de obra, eletricidade, testes e transporte.",
                font=ctk.CTkFont(size=12),
                text_color="#b8b8b8",
                anchor="w",
            ).pack(fill="x", padx=16, pady=(0, 12))

            # Container principal com scroll
            main_scroll = ctk.CTkScrollableFrame(
                dialog,
                fg_color="#202124",
                corner_radius=8,
                border_width=1,
                border_color="#35363a",
            )
            main_scroll.pack(fill="both", expand=True, padx=20, pady=(0, 12))

            # === SEÇÃO A: Taxas Horárias ===
            section_a_label = ctk.CTkLabel(
                main_scroll,
                text="Taxas Horárias",
                font=ctk.CTkFont(size=18, weight="bold")
            )
            section_a_label.pack(pady=(0, 10), anchor="w")

            def align_rate_row(row_frame):
                children = row_frame.winfo_children()
                if not children:
                    return
                children[0].configure(width=190, anchor="w", text_color="#dbe4ee")
                if len(children) > 1:
                    children[1].configure(width=150, height=32)

            # Mão de Obra 1
            labor1_frame = ctk.CTkFrame(main_scroll, fg_color="transparent")
            labor1_frame.pack(fill="x", pady=5)

            ctk.CTkLabel(labor1_frame, text="Mão de Obra 1 (€/h):", font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 10))
            labor1_entry = ctk.CTkEntry(labor1_frame, width=150, height=30)
            labor1_entry.pack(side="left")
            labor1_entry.insert(0, str(current_labor_rate_1))
            align_rate_row(labor1_frame)

            # Mão de Obra 2
            labor2_frame = ctk.CTkFrame(main_scroll, fg_color="transparent")
            labor2_frame.pack(fill="x", pady=5)

            ctk.CTkLabel(labor2_frame, text="Mão de Obra 2 (€/h):", font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 10))
            labor2_entry = ctk.CTkEntry(labor2_frame, width=150, height=30)
            labor2_entry.pack(side="left")
            labor2_entry.insert(0, str(current_labor_rate_2))
            align_rate_row(labor2_frame)

            # Placas
            placas_frame = ctk.CTkFrame(main_scroll, fg_color="transparent")
            placas_frame.pack(fill="x", pady=5)

            ctk.CTkLabel(placas_frame, text="Placas (Preço/Un):", font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 10))
            placas_entry = ctk.CTkEntry(placas_frame, width=150, height=30)
            placas_entry.pack(side="left")
            placas_entry.insert(0, str(current_placas_price))
            align_rate_row(placas_frame)

            # Eletricidade
            elec_frame = ctk.CTkFrame(main_scroll, fg_color="transparent")
            elec_frame.pack(fill="x", pady=5)

            ctk.CTkLabel(elec_frame, text="Eletricidade (€/h):", font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 10))
            elec_entry = ctk.CTkEntry(elec_frame, width=150, height=30)
            elec_entry.pack(side="left")
            elec_entry.insert(0, str(current_elec_rate))
            align_rate_row(elec_frame)

            # Taxa Teste/Diagnóstico
            test_frame = ctk.CTkFrame(main_scroll, fg_color="transparent")
            test_frame.pack(fill="x", pady=5)

            ctk.CTkLabel(test_frame, text="Taxa Teste/Diagnóstico (€/h):", font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 10))
            test_entry = ctk.CTkEntry(test_frame, width=150, height=30)
            test_entry.pack(side="left")
            test_entry.insert(0, str(current_test_rate))
            align_rate_row(test_frame)

            # Separador
            separator = ctk.CTkFrame(main_scroll, height=1, fg_color="#35363a")
            separator.pack(fill="x", pady=20)

            # === SEÇÃO B: Regras de Transporte ===
            section_b_label = ctk.CTkLabel(
                main_scroll,
                text="Regras de Transporte (Intervalos de Peso)",
                font=ctk.CTkFont(size=18, weight="bold")
            )
            section_b_label.pack(pady=(0, 10), anchor="w")

            # Container para regras (scrollável)
            rules_container = ctk.CTkScrollableFrame(
                main_scroll,
                height=250,
                fg_color="#151617",
                corner_radius=8,
                border_width=1,
                border_color="#35363a",
            )
            rules_container.pack(fill="both", expand=True, pady=10)

            # Converter regras antigas para novo formato (compatibilidade)
            # Formato antigo: [{"max_weight": 2, "price": 5}] ou [{"min": 0, "max": 2, "price": 5}]
            # Formato novo (simples): [{"max": 2, "price": 5}]
            def normalize_rules(rules):
                """Normaliza regras para formato simples: [{"max": X, "price": Y}]"""
                if not rules:
                    return []

                normalized = []

                # Se já está no formato simples, retornar como está
                if rules and "max" in rules[0] and "min" not in rules[0]:
                    # Ordenar por max
                    return sorted(rules, key=lambda x: x.get("max", 0))

                # Converter formato antigo para novo
                # Pode ser {"max_weight": X} ou {"min": A, "max": B}
                sorted_rules = sorted(rules, key=lambda x: x.get("max_weight", x.get("max", 0)))

                for rule in sorted_rules:
                    if "max_weight" in rule:
                        # Formato antigo: {"max_weight": X, "price": Y}
                        normalized.append({"max": rule.get("max_weight", 0), "price": rule.get("price", 0)})
                    elif "max" in rule:
                        # Formato com min: {"min": A, "max": B, "price": Y} -> {"max": B, "price": Y}
                        normalized.append({"max": rule.get("max", 0), "price": rule.get("price", 0)})

                return normalized

            # Normalizar regras para formato simples
            current_rules = normalize_rules(current_rules)

            # Lista de linhas de transporte (com StringVars para reatividade)
            transport_rows = []

            def recalculate_chain(*args):
                """Recalcula a cadeia em tempo real quando max_var muda"""
                current_floor = 0.0

                for row in transport_rows:
                    # 1. Atualizar label "De" da linha atual
                    row["min_label"].configure(text=f"{current_floor:.2f} kg")

                    # 2. Ler valor do max_var
                    max_str = row["max_var"].get().strip().replace(",", ".")

                    # 3. Se válido, atualizar current_floor
                    if max_str:
                        try:
                            max_value = float(max_str)
                            if max_value > current_floor:
                                current_floor = max_value
                        except ValueError:
                            # Valor inválido, manter current_floor como está
                            pass

            def refresh_rules_display():
                """Atualiza a exibição das regras usando StringVars com trace"""
                # Limpar widgets existentes e traces
                for widget in rules_container.winfo_children():
                    widget.destroy()

                # Limpar traces antigos
                for row in transport_rows:
                    if "max_var" in row and hasattr(row["max_var"], "trace_remove"):
                        try:
                            # Remover trace se existir
                            if "trace_id" in row:
                                row["max_var"].trace_remove("write", row["trace_id"])
                        except:
                            pass

                transport_rows.clear()

                # Ordenar regras por max (crescente)
                current_rules.sort(key=lambda x: x.get("max", 0))

                # Criar cabeçalhos
                header_frame = ctk.CTkFrame(rules_container, fg_color=["#e0e0e0", "#3a3a3a"])
                header_frame.pack(fill="x", pady=(0, 5))

                ctk.CTkLabel(header_frame, text="De (> kg)", font=ctk.CTkFont(size=12, weight="bold"), width=120).pack(side="left", padx=5)
                ctk.CTkLabel(header_frame, text="Até (<= kg)", font=ctk.CTkFont(size=12, weight="bold"), width=120).pack(side="left", padx=5)
                ctk.CTkLabel(header_frame, text="Preço (€)", font=ctk.CTkFont(size=12, weight="bold"), width=120).pack(side="left", padx=5)
                ctk.CTkLabel(header_frame, text="Ações", font=ctk.CTkFont(size=12, weight="bold"), width=100).pack(side="left", padx=5)

                # Criar linhas com StringVars
                for index, rule in enumerate(current_rules):
                    # Criar linha
                    row_frame = ctk.CTkFrame(rules_container, fg_color="transparent")
                    row_frame.pack(fill="x", pady=2)

                    # Col 1: Label "De" (read-only, será atualizado por recalculate_chain)
                    min_label = ctk.CTkLabel(
                        row_frame,
                        text="0.00 kg",  # Será atualizado por recalculate_chain
                        font=ctk.CTkFont(size=12),
                        width=120,
                        anchor="center"
                    )
                    min_label.pack(side="left", padx=5)

                    # Col 2: Entry "Até" (max) com StringVar
                    max_var = ctk.StringVar(value=str(rule.get("max", "")))
                    max_entry = ctk.CTkEntry(
                        row_frame,
                        width=120,
                        height=30,
                        justify="center",
                        textvariable=max_var
                    )
                    max_entry.pack(side="left", padx=5)

                    # Adicionar trace listener para reatividade
                    trace_id = max_var.trace_add("write", recalculate_chain)

                    # Col 3: Entry "Preço" com StringVar
                    price_var = ctk.StringVar(value=str(rule.get("price", "")))
                    price_entry = ctk.CTkEntry(
                        row_frame,
                        width=120,
                        height=30,
                        justify="center",
                        textvariable=price_var
                    )
                    price_entry.pack(side="left", padx=5)

                    # Col 4: Botão Remover
                    remove_btn = ctk.CTkButton(
                        row_frame,
                        text="Remover",
                        command=lambda idx=index: remove_rule(idx),
                        width=100,
                        height=30,
                        fg_color=["#F44336", "#F44336"],
                        hover_color=["#d32f2f", "#d32f2f"]
                    )
                    remove_btn.pack(side="left", padx=5)

                    # Guardar referências na lista
                    transport_rows.append({
                        "frame": row_frame,
                        "min_label": min_label,
                        "max_var": max_var,
                        "price_var": price_var,
                        "trace_id": trace_id,
                        "rule_index": index
                    })

                # Trigger inicial para calcular labels "De"
                recalculate_chain()

            def remove_rule(index):
                """Remove uma regra e refresca a tabela"""
                if 0 <= index < len(current_rules):
                    current_rules.pop(index)
                    refresh_rules_display()

            def add_rule():
                """Adiciona uma nova regra no final da cadeia"""
                # Encontrar o último max weight das regras existentes
                last_max = 0.0
                if current_rules:
                    last_max = max(rule.get("max", 0.0) for rule in current_rules)
                elif transport_rows:
                    # Se não há regras mas há widgets, calcular do último max_var
                    try:
                        last_max_str = transport_rows[-1]["max_var"].get().strip().replace(",", ".")
                        if last_max_str:
                            last_max = float(last_max_str)
                    except:
                        pass

                # Adicionar nova regra (formato simples: apenas max e price)
                new_rule = {"max": last_max + 5.0, "price": 0.0}
                current_rules.append(new_rule)

                # Refresh toda a tabela (cria novos widgets e recalcula cadeia)
                refresh_rules_display()

            # Botão adicionar regra
            add_btn = ctk.CTkButton(
                main_scroll,
                text="Adicionar Intervalo",
                command=add_rule,
                width=200,
                height=35,
                fg_color=["#2196F3", "#2196F3"],
                hover_color=["#1976D2", "#1976D2"]
            )
            add_btn.pack(pady=10)

            # Carregar regras existentes
            refresh_rules_display()

            # Botões de ação
            buttons_frame = create_action_footer(dialog, padx=20, pady=(0, 18))

            def on_save():
                """Salva todas as configurações"""
                try:
                    # Validar taxas horárias
                    try:
                        new_labor_rate_1 = float(labor1_entry.get().strip().replace(",", "."))
                        if new_labor_rate_1 < 0:
                            raise ValueError("Taxa de mão de obra 1 deve ser positiva")
                    except ValueError:
                        messagebox.showerror("Erro", "Taxa de mão de obra 1 inválida!")
                        return

                    try:
                        new_labor_rate_2 = float(labor2_entry.get().strip().replace(",", "."))
                        if new_labor_rate_2 < 0:
                            raise ValueError("Taxa de mão de obra 2 deve ser positiva")
                    except ValueError:
                        messagebox.showerror("Erro", "Taxa de mão de obra 2 inválida!")
                        return

                    try:
                        new_placas_price = float(placas_entry.get().strip().replace(",", "."))
                        if new_placas_price < 0:
                            raise ValueError("Preço de placas deve ser positivo")
                    except ValueError:
                        messagebox.showerror("Erro", "Preço de placas inválido!")
                        return

                    try:
                        new_elec_rate = float(elec_entry.get().strip().replace(",", "."))
                        if new_elec_rate < 0:
                            raise ValueError("Taxa de eletricidade deve ser positiva")
                    except ValueError:
                        messagebox.showerror("Erro", "Taxa de eletricidade inválida!")
                        return

                    try:
                        new_test_rate = float(test_entry.get().strip().replace(",", "."))
                        if new_test_rate < 0:
                            raise ValueError("Taxa de teste/diagnóstico deve ser positiva")
                    except ValueError:
                        messagebox.showerror("Erro", "Taxa de teste/diagnóstico inválida!")
                        return

                    # Validar e coletar regras (formato simples: apenas max e price)
                    validated_rules = []
                    previous_max = 0.0

                    for row in transport_rows:
                        try:
                            max_weight = float(row["max_var"].get().strip().replace(",", "."))
                            price = float(row["price_var"].get().strip().replace(",", "."))

                            # Validações
                            if max_weight <= previous_max:
                                messagebox.showerror(
                                    "Erro",
                                    f"O peso máximo ({max_weight:.2f} kg) deve ser maior que o peso máximo anterior ({previous_max:.2f} kg)!\n\n"
                                    "Os intervalos devem estar em ordem crescente."
                                )
                                return

                            if price < 0:
                                messagebox.showerror("Erro", "O preço não pode ser negativo!")
                                return

                            validated_rules.append({"max": max_weight, "price": price})
                            previous_max = max_weight

                        except ValueError:
                            messagebox.showerror("Erro", "Por favor, insira valores numéricos válidos em todos os campos!")
                            return

                    # Ordenar por max (garantir ordem)
                    validated_rules.sort(key=lambda x: x["max"])

                    # Salvar tudo
                    success1 = self.app.db_manager.set_setting("labor_rate_1", str(new_labor_rate_1))
                    success2 = self.app.db_manager.set_setting("labor_rate_2", str(new_labor_rate_2))
                    success3 = self.app.db_manager.set_setting("placas_price", str(new_placas_price))
                    success4 = self.app.db_manager.set_setting("electricity_rate", str(new_elec_rate))
                    success5 = self.app.db_manager.set_setting("test_hourly_rate", str(new_test_rate))
                    success6 = self.app.db_manager.set_transport_rules(validated_rules)

                    if success1 and success2 and success3 and success4 and success5 and success6:
                        messagebox.showinfo("Operação Concluída", "Preços configurados com sucesso.")
                        self.load_rates()
                        # Atualizar label de taxa de teste se estiver visível
                        if hasattr(self, 'test_rate_info_label'):
                            self.update_test_rate_label()
                        self.update_total()
                        dialog.destroy()
                    else:
                        messagebox.showerror("Erro", "Erro ao guardar configurações!")
                except Exception as e:
                    messagebox.showerror("Erro", f"Erro ao guardar:\n\n{str(e)}")

            def on_cancel():
                dialog.destroy()

            save_btn = create_action_button(
                buttons_frame,
                text="Guardar",
                command=on_save,
                role="success",
                width=150,
            )

            cancel_btn = create_action_button(
                buttons_frame,
                text="Cancelar",
                command=on_cancel,
                role="secondary",
                width=150,
            )
            apply_modern_style(dialog)

            # Centralizar diálogo
            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
            y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
            dialog.geometry(f"+{x}+{y}")

        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao abrir configurações:\n\n{str(e)}")

    def submit_repair(self):
        """Regista a reparação"""
        # Obter dados do cliente
        client_name = self.client_name_entry.get().strip()
        client_phone = self.client_phone_entry.get().strip()
        client_nif = self.client_nif_entry.get().strip()
        client_address = self.client_address_entry.get().strip()

        # Obter dados da reparação
        problem_summary = self.problem_summary_entry.get().strip()
        device_imei = self.device_imei_entry.get().strip()
        warranty_number = self.warranty_number_entry.get().strip()
        description = self.description_text.get("1.0", "end-1c").strip()

        # Validações
        if not client_name:
            messagebox.showwarning("Atenção", "Por favor, insira o nome do cliente.")
            return

        if not client_phone:
            messagebox.showwarning("Atenção", "Por favor, insira o telemóvel do cliente.")
            return

        if not problem_summary:
            messagebox.showwarning("Atenção", "Por favor, insira o tipo de equipamento.")
            return

        if not description:
            messagebox.showwarning("Atenção", "Por favor, insira uma descrição.")
            return

        if not self.selected_components:
            if not messagebox.askyesno("Confirmar", "Nenhum componente selecionado. Deseja continuar?"):
                return

        # Obter quantidade (horas ou unidades) e tipo de mão de obra
        try:
            labor_qty = float(self.hours_entry.get().strip().replace(",", "."))
            if labor_qty < 0:
                labor_qty = 0.0
        except (ValueError, AttributeError):
            labor_qty = 1.0

        # Obter tipo de mão de obra selecionado
        labor_type_selected = self.labor_type_segmented.get()

        # Converter para valor do banco de dados
        if labor_type_selected == "Mão de Obra 1":
            labor_type = "labor1"
        elif labor_type_selected == "Mão de Obra 2":
            labor_type = "labor2"
        elif labor_type_selected == "Placas":
            labor_type = "placas"
        else:
            labor_type = "labor1"  # Fallback

        # Obter taxa correspondente para cálculo do total
        try:
            if labor_type == "labor1":
                rate = float(self.app.db_manager.get_setting("labor_rate_1", "30.0"))
            elif labor_type == "labor2":
                rate = float(self.app.db_manager.get_setting("labor_rate_2", "45.0"))
            elif labor_type == "placas":
                rate = float(self.app.db_manager.get_setting("placas_price", "50.0"))
            else:
                rate = 30.0
        except:
            rate = 30.0

        # Calcular total e verificar stock (usar cache quando possível)
        parts_total = 0.0
        used_parts_list = []
        components_to_consume = []
        selected_comp_ids = [comp_id for comp_id, _ in self.selected_components]

        # Buscar componentes em falta em batch
        missing_ids = [comp_id for comp_id in selected_comp_ids if comp_id not in self.components_cache]
        if missing_ids:
            batch_components = self.app.db_manager.get_components_by_ids(missing_ids)
            self.components_cache.update(_normalize_components_by_id(batch_components))

        for comp_id, component_qty in self.selected_components:
            component = _normalize_component(self.components_cache.get(comp_id))
            if not component or component.get("id") is None:
                messagebox.showerror("Erro", f"Componente ID {comp_id} nao encontrado ou invalido.")
                self.refresh_components_list()
                self.refresh_selected_list()
                return

            # Verificar stock
            if component["qty"] < component_qty:
                messagebox.showerror("Erro", f"Stock insuficiente para {component['code']}!")
                self.refresh_components_list()
                self.refresh_selected_list()
                return

            subtotal = component["price"] * component_qty
            parts_total += subtotal
            # Use ID:QTY format instead of CODE (QTY) to avoid parsing issues with special characters
            used_parts_list.append(f"{comp_id}:{component_qty}")
            components_to_consume.append((comp_id, component_qty))

        used_parts_str = ",".join(used_parts_list) if used_parts_list else "Nenhum"

        # Obter horas de eletricidade
        try:
            electricity_hours = float(self.electricity_hours_entry.get().strip().replace(",", "."))
            if electricity_hours < 0:
                electricity_hours = 0.0
        except (ValueError, AttributeError):
            electricity_hours = 0.0

        # Obter taxa de eletricidade
        try:
            elec_rate = float(self.app.db_manager.get_setting("electricity_rate", "0.50"))
        except:
            elec_rate = 0.50

        # Obter peso da encomenda
        try:
            package_weight = float(self.package_weight_entry.get().strip().replace(",", "."))
            if package_weight < 0:
                package_weight = 0.0
        except (ValueError, AttributeError):
            package_weight = 0.0

        # Obter horas de testes (se toggle estiver ativo)
        horas_teste = 0.0
        if hasattr(self, 'test_toggle') and self.test_toggle.get():
            try:
                horas_teste = float(self.horas_teste_entry.get().strip().replace(",", "."))
                if horas_teste < 0:
                    horas_teste = 0.0
            except (ValueError, AttributeError):
                horas_teste = 0.0

        # Obter preço por hora de testes da configuração global
        preco_hora_teste = self.load_hourly_rate() if horas_teste > 0 else 0.0

        # Calcular custos
        labor_total = labor_qty * rate
        elec_total = electricity_hours * elec_rate
        transport_cost = self.calculate_transport_cost(package_weight)
        test_total = horas_teste * preco_hora_teste

        # Calcular total: Peças + Mão de Obra + Eletricidade + Transporte + Testes
        total = parts_total + labor_total + elec_total + transport_cost + test_total

        # Executar operações de BD em background
        def db_operation():
            return self.app.db_manager.add_repair_with_stock_update(
                client=client_name,
                phone=client_phone,
                nif=client_nif,
                address=client_address,
                description=description,
                used_parts=used_parts_str,
                total=total,
                components_to_consume=components_to_consume,
                payment_status="Pendente",
                hours_worked=labor_qty,
                problem_summary=problem_summary,
                device_imei=device_imei,
                repair_status="Em Análise",  # Estado inicial do workflow
                electricity_hours=electricity_hours,
                package_weight=package_weight,
                transport_cost=transport_cost,
                labor_type=labor_type,  # Novo campo
                warranty_number=warranty_number,  # Número de garantia
                horas_teste=horas_teste,  # Horas de testes/diagnóstico
                preco_hora_teste=preco_hora_teste  # Preço por hora de teste
            )

        def callback(repair_id, error):
            if error:
                messagebox.showerror("Erro", f"Erro ao registar reparação: {str(error)}")
                return

            messagebox.showinfo("Operação Concluída", f"Reparação registada com sucesso. ID: {repair_id}")

            # Limpar formulário
            self.client_name_entry.delete(0, "end")
            self.client_phone_entry.delete(0, "end")
            self.client_nif_entry.delete(0, "end")
            self.client_address_entry.delete(0, "end")
            self.problem_summary_entry.delete(0, "end")
            self.device_imei_entry.delete(0, "end")
            self.warranty_number_entry.delete(0, "end")
            self.description_text.delete("1.0", "end")
            self.hours_entry.delete(0, "end")
            self.hours_entry.insert(0, "1.0")

            # Limpar campos de testes e desativar toggle
            if hasattr(self, 'test_toggle'):
                self.test_toggle.deselect()  # Desativar toggle
            if hasattr(self, 'horas_teste_entry'):
                self.horas_teste_entry.delete(0, "end")
                self.horas_teste_entry.insert(0, "1.0")
            if hasattr(self, 'frame_testes'):
                self.frame_testes.pack_forget()  # Ocultar campos
            # Atualizar label informativa
            if hasattr(self, 'test_rate_info_label'):
                self.update_test_rate_label()
            self.labor_type_segmented.set("Mão de Obra 1")  # Reset para default
            self.on_labor_type_changed("Mão de Obra 1")  # Atualizar label
            self.selected_components = []
            self.current_client_id = None

            # Limpar cache e hash para garantir dados frescos na próxima vez
            self.components_cache = {}
            self._components_hash = None

            self.refresh_selected_list()

            # IMPORTANTE: Atualizar lista de componentes para refletir stock atualizado
            # Usar after() com pequeno delay para garantir que a UI está pronta e a mensagem foi processada
            self.after(100, lambda: self.refresh_components_list(force=True))

            self.update_total()

        run_db_operation(self.app.root, db_operation, callback)
