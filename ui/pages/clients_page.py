"""
Página de Histórico de Clientes
Lista todas as reparações e permite exportar para Excel
"""

import customtkinter as ctk
from tkinter import messagebox, filedialog
import pandas as pd
from datetime import datetime
import os
import re
from tkcalendar import DateEntry
from ui.utils import Debouncer, run_db_operation, run_db_operation_with_loading
from ui.pdf_exporter import generate_repair_pdf


class ClientsPage(ctk.CTkFrame):
    """Página de histórico de clientes"""
    
    def __init__(self, parent, app):
        """
        Inicializa a página de histórico
        
        Args:
            parent: Widget pai
            app: Instância da aplicação principal
        """
        super().__init__(parent, fg_color=["#f0f0f0", "#1a1a1a"])
        self.app = app
        self.is_loading = False
        self.current_data_hash = None
        self.current_payment_filter = "All"  # "All", "Pago", "Pendente"
        self.current_status_filter = "All"  # "All", "Em Análise", "Aguardar Peças", "Pronto a Entregar"
        self.setup_ui()
        self.refresh_data()
    
    def setup_ui(self):
        """Configura a interface da página de histórico"""
        # Título e botões
        title_frame = ctk.CTkFrame(self, fg_color="transparent")
        title_frame.pack(fill="x", padx=20, pady=(20, 10))
        
        title_label = ctk.CTkLabel(
            title_frame,
            text="Histórico de Reparações",
            font=ctk.CTkFont(size=32, weight="bold"),
            text_color=["#FF5722", "#FF5722"]
        )
        title_label.pack(side="left")
        
        # Botões
        buttons_frame = ctk.CTkFrame(title_frame, fg_color="transparent")
        buttons_frame.pack(side="right")
        
        # Botão Filtro de Pagamento
        self.payment_filter_button = ctk.CTkButton(
            buttons_frame,
            text="Filtro: Todos",
            command=self.toggle_payment_filter,
            font=ctk.CTkFont(size=14),
            fg_color=["#666666", "#666666"],
            hover_color=["#555555", "#555555"],
            width=130,
            height=30
        )
        self.payment_filter_button.pack(side="left", padx=(0, 10))
        
        # Botão Filtro de Progresso
        self.status_filter_button = ctk.CTkButton(
            buttons_frame,
            text="Progresso: Todos",
            command=self.toggle_status_filter,
            font=ctk.CTkFont(size=14),
            fg_color=["#666666", "#666666"],
            hover_color=["#555555", "#555555"],
            width=130,
            height=30
        )
        self.status_filter_button.pack(side="left", padx=(0, 10))
        
        back_button = ctk.CTkButton(
            buttons_frame,
            text="Voltar",
            command=lambda: self.app.show_page("home"),
            font=ctk.CTkFont(size=14),
            fg_color="transparent",
            hover_color=["#555555", "#333333"],
            width=100,
            height=30
        )
        back_button.pack(side="left")
        
        # Barra de pesquisa
        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.pack(fill="x", padx=20, pady=(0, 10))
        
        search_label = ctk.CTkLabel(
            search_frame,
            text="Pesquisar:",
            font=ctk.CTkFont(size=14)
        )
        search_label.pack(side="left", padx=(0, 10))
        
        self.search_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text="Cliente, NIF, descrição ou IMEI...",
            font=ctk.CTkFont(size=14),
            width=400
        )
        self.search_entry.pack(side="left", fill="x", expand=True)
        
        # Estado atual do filtro de datas (armazenado como YYYY-MM-DD ou None)
        self.date_filter_start = None
        self.date_filter_end = None
        
        # Botão para abrir seletor de datas + label de estado
        date_filters_frame = ctk.CTkFrame(search_frame, fg_color="transparent")
        date_filters_frame.pack(side="left", padx=(10, 0))
        
        self.date_filter_btn = ctk.CTkButton(
            date_filters_frame,
            text="📅 Filtrar por Data",
            command=self.open_date_picker,
            font=ctk.CTkFont(size=12),
            width=140,
            height=30,
        )
        self.date_filter_btn.pack(side="left", padx=(0, 8))
        
        self.date_filter_label = ctk.CTkLabel(
            date_filters_frame,
            text="Filtro: Tudo",
            font=ctk.CTkFont(size=12),
            text_color=["#cccccc", "#aaaaaa"],
            anchor="w"
        )
        self.date_filter_label.pack(side="left")

        # Usar debounce para evitar pesquisas a cada tecla (300ms após parar de digitar)
        self.search_debouncer = Debouncer(self.refresh_data, self.winfo_toplevel(), delay=300)
        
        def safe_key_release(e):
            """Handler seguro para KeyRelease que não bloqueia o event loop"""
            try:
                self.search_debouncer()
            except Exception:
                pass  # Ignorar erros para não quebrar o event loop
        
        self.search_entry.bind("<KeyRelease>", safe_key_release)
        
        # Lista de reparações
        list_frame = ctk.CTkFrame(self)
        list_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        # Scrollable frame
        scrollable_frame = ctk.CTkScrollableFrame(list_frame)
        scrollable_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        self.list_container = scrollable_frame
    
    def toggle_payment_filter(self):
        """Alterna entre os estados do filtro de pagamento: All -> Pago -> Pendente -> All"""
        if self.current_payment_filter == "All":
            self.current_payment_filter = "Pago"
            self.payment_filter_button.configure(
                text="Filtro: Pagos",
                fg_color=["#4CAF50", "#4CAF50"],
                hover_color=["#45a049", "#45a049"]
            )
        elif self.current_payment_filter == "Pago":
            self.current_payment_filter = "Pendente"
            self.payment_filter_button.configure(
                text="Filtro: Não Pagos",
                fg_color=["#F44336", "#F44336"],
                hover_color=["#d32f2f", "#d32f2f"]
            )
        else:  # Pendente
            self.current_payment_filter = "All"
            self.payment_filter_button.configure(
                text="Filtro: Todos",
                fg_color=["#666666", "#666666"],
                hover_color=["#555555", "#555555"]
            )
        
        # Recarregar dados com o novo filtro
        self.refresh_data(force=True)
    
    def toggle_status_filter(self):
        """Alterna entre os estados do filtro de progresso: All -> Em Análise -> Aguardar Peças -> Pronto -> All"""
        if self.current_status_filter == "All":
            self.current_status_filter = "Em Análise"
            self.status_filter_button.configure(
                text="Progresso: Em Análise",
                fg_color=["#3B8ED0", "#3B8ED0"],
                hover_color=["#2E6DA4", "#2E6DA4"]
            )
        elif self.current_status_filter == "Em Análise":
            self.current_status_filter = "Aguardar Peças"
            self.status_filter_button.configure(
                text="Progresso: Aguardar Peças",
                fg_color=["#E67E22", "#E67E22"],
                hover_color=["#D35400", "#D35400"]
            )
        elif self.current_status_filter == "Aguardar Peças":
            self.current_status_filter = "Pronto a Entregar"
            self.status_filter_button.configure(
                text="Progresso: Pronto",
                fg_color=["#2CC985", "#2CC985"],
                hover_color=["#27AE60", "#27AE60"]
            )
        else:  # Pronto a Entregar
            self.current_status_filter = "All"
            self.status_filter_button.configure(
                text="Progresso: Todos",
                fg_color=["#666666", "#666666"],
                hover_color=["#555555", "#555555"]
            )
        
        # Recarregar dados com o novo filtro
        self.refresh_data(force=True)
    
    def open_date_picker(self):
        """Abre um popup com calendário e presets para filtrar por intervalo de datas."""
        popup = ctk.CTkToplevel(self.app.root)
        popup.title("Filtrar por Data")
        popup.geometry("420x320")
        popup.resizable(False, False)
        popup.transient(self.app.root)
        
        # Centralizar popup
        popup.update_idletasks()
        x = (popup.winfo_screenwidth() // 2) - (420 // 2)
        y = (popup.winfo_screenheight() // 2) - (320 // 2)
        popup.geometry(f"420x320+{x}+{y}")
        
        main_frame = ctk.CTkFrame(popup)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Helper para aplicar intervalo e fechar
        def apply_range(start_date, end_date, label_text: str):
            from datetime import date
            
            # Normalizar ordem (start <= end)
            if start_date and end_date and start_date > end_date:
                start_date, end_date = end_date, start_date
            
            # Guardar em formato YYYY-MM-DD para o SQL
            self.date_filter_start = start_date.strftime("%Y-%m-%d") if start_date else None
            self.date_filter_end = end_date.strftime("%Y-%m-%d") if end_date else None
            
            # Atualizar label de estado
            if hasattr(self, "date_filter_label"):
                self.date_filter_label.configure(text=label_text)
            
            popup.destroy()
            self.refresh_data(force=True)
        
        from datetime import datetime, timedelta
        today = datetime.now().date()
        
        # Presets rápidos
        presets_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        presets_frame.pack(fill="x", pady=(0, 15))
        
        def make_preset_btn(text, cmd):
            btn = ctk.CTkButton(
                presets_frame,
                text=text,
                command=cmd,
                font=ctk.CTkFont(size=12),
                width=120,
                height=28
            )
            btn.pack(side="left", padx=4, pady=4)
        
        # Hoje
        def preset_today():
            label = f"Hoje ({today.strftime('%d/%m/%Y')})"
            apply_range(today, today, label)
        
        # Esta semana (segunda a domingo)
        def preset_this_week():
            monday = today - timedelta(days=today.weekday())
            sunday = monday + timedelta(days=6)
            label = f"Esta Semana ({monday.strftime('%d/%m')} - {sunday.strftime('%d/%m')})"
            apply_range(monday, sunday, label)
        
        # Este mês
        def preset_this_month():
            first = today.replace(day=1)
            if first.month == 12:
                next_month_first = first.replace(year=first.year + 1, month=1, day=1)
            else:
                next_month_first = first.replace(month=first.month + 1, day=1)
            last = next_month_first - timedelta(days=1)
            label = f"Este Mês ({first.strftime('%d/%m')} - {last.strftime('%d/%m')})"
            apply_range(first, last, label)
        
        # Últimos 30 dias
        def preset_last_30():
            start = today - timedelta(days=30)
            label = f"Últimos 30 dias ({start.strftime('%d/%m')} - {today.strftime('%d/%m')})"
            apply_range(start, today, label)
        
        # Limpar filtro
        def preset_clear():
            apply_range(None, None, "Filtro: Tudo")
        
        make_preset_btn("Hoje", preset_today)
        make_preset_btn("Esta Semana", preset_this_week)
        make_preset_btn("Este Mês", preset_this_month)
        make_preset_btn("Últimos 30 Dias", preset_last_30)
        make_preset_btn("Limpar Filtro", preset_clear)
        
        # Separador
        separator = ctk.CTkLabel(
            main_frame,
            text="OU selecionar intervalo personalizado:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=["#cccccc", "#aaaaaa"]
        )
        separator.pack(pady=(10, 10))
        
        # Intervalo personalizado com DateEntry
        custom_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        custom_frame.pack(fill="x", pady=(0, 10))
        
        # Labels
        start_label = ctk.CTkLabel(
            custom_frame,
            text="Início:",
            font=ctk.CTkFont(size=12)
        )
        start_label.grid(row=0, column=0, padx=(0, 5), pady=5, sticky="e")
        
        end_label = ctk.CTkLabel(
            custom_frame,
            text="Fim:",
            font=ctk.CTkFont(size=12)
        )
        end_label.grid(row=1, column=0, padx=(0, 5), pady=5, sticky="e")
        
        # Valores iniciais (usar filtro atual, se existir)
        def parse_iso_date(s: str):
            try:
                return datetime.strptime(s, "%Y-%m-%d").date()
            except Exception:
                return None
        
        current_start = parse_iso_date(self.date_filter_start) if getattr(self, "date_filter_start", None) else today - timedelta(days=30)
        current_end = parse_iso_date(self.date_filter_end) if getattr(self, "date_filter_end", None) else today
        
        # DateEntry widgets (tkcalendar)
        start_cal = DateEntry(
            custom_frame,
            date_pattern="yyyy-mm-dd",
        )
        start_cal.grid(row=0, column=1, padx=(0, 10), pady=5, sticky="w")
        start_cal.set_date(current_start)
        
        end_cal = DateEntry(
            custom_frame,
            date_pattern="yyyy-mm-dd",
        )
        end_cal.grid(row=1, column=1, padx=(0, 10), pady=5, sticky="w")
        end_cal.set_date(current_end)
        
        # Botões Confirmar / Cancelar
        buttons_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        buttons_frame.pack(fill="x", pady=(10, 0))
        
        def on_confirm():
            s_date = start_cal.get_date()
            e_date = end_cal.get_date()
            label = f"De {s_date.strftime('%d/%m/%Y')} a {e_date.strftime('%d/%m/%Y')}"
            apply_range(s_date, e_date, label)
        
        confirm_btn = ctk.CTkButton(
            buttons_frame,
            text="Confirmar",
            command=on_confirm,
            font=ctk.CTkFont(size=12, weight="bold"),
            width=120,
            height=30
        )
        confirm_btn.pack(side="left", padx=(0, 10))
        
        cancel_btn = ctk.CTkButton(
            buttons_frame,
            text="Cancelar",
            command=popup.destroy,
            font=ctk.CTkFont(size=12),
            width=100,
            height=30,
            fg_color=["#666666", "#666666"],
            hover_color=["#555555", "#555555"],
        )
        cancel_btn.pack(side="left")
    
    def refresh_data(self, force: bool = False):
        """
        Atualiza a lista de reparações (com threading)
        
        Args:
            force: Se True, força refresh mesmo se dados não mudaram
        """
        if self.is_loading:
            return
        
        self.is_loading = True
        
        # Obter termo de pesquisa
        search_term = self.search_entry.get().strip()
        
        # Obter datas do filtro atual (já normalizadas em YYYY-MM-DD)
        date_start = getattr(self, "date_filter_start", None)
        date_end = getattr(self, "date_filter_end", None)
        
        # Determinar filtros (None se "All" para compatibilidade com BD)
        payment_filter = None if self.current_payment_filter == "All" else self.current_payment_filter
        status_filter = None if self.current_status_filter == "All" else self.current_status_filter
        
        def db_operation():
            if search_term:
                return self.app.db_manager.search_repairs(
                    search_term,
                    payment_filter=payment_filter,
                    status_filter=status_filter,
                    date_start=date_start,
                    date_end=date_end,
                    limit=50
                )
            else:
                return self.app.db_manager.get_all_repairs(
                    payment_filter=payment_filter,
                    status_filter=status_filter,
                    date_start=date_start,
                    date_end=date_end,
                    limit=50
                )
        
        def callback(repairs, error):
            self.is_loading = False
            
            if error:
                messagebox.showerror("Erro", f"Erro ao carregar reparações: {str(error)}")
                return
            
            # Calcular hash dos dados para evitar refresh desnecessário
            import hashlib
            data_str = str(sorted([(r["id"], r["client"], r["date"]) for r in repairs]))
            data_hash = hashlib.md5(data_str.encode()).hexdigest()
            
            # Se dados não mudaram e não é refresh forçado, não atualizar UI
            if not force and data_hash == self.current_data_hash:
                return  # Dados não mudaram
            
            self.current_data_hash = data_hash
            
            # Limpar lista atual
            for widget in self.list_container.winfo_children():
                widget.destroy()
            
            if not repairs:
                no_data_label = ctk.CTkLabel(
                    self.list_container,
                    text="Nenhuma reparação encontrada",
                    font=ctk.CTkFont(size=16),
                    text_color=["#666666", "#999999"]
                )
                no_data_label.pack(pady=50)
                return
            
            # Criar cabeçalho
            header_frame = ctk.CTkFrame(self.list_container, fg_color=["#e0e0e0", "#2b2b2b"])
            header_frame.pack(fill="x", pady=(0, 10))
            
            # Configurar pesos das colunas (Data:1, Cliente:2, Tipo de Equipamento:2, IMEI:1, Total:1, Progresso:1, Estado:1, Ações:2)
            column_weights = [1, 2, 2, 1, 1, 1, 1, 2]
            for i, weight in enumerate(column_weights):
                header_frame.grid_columnconfigure(i, weight=weight, uniform="repair_cols")
            
            headers = ["Data", "Cliente", "Tipo de Equipamento", "IMEI", "Total s/ IVA", "Progresso", "Estado", "Ações"]
            
            for i, header in enumerate(headers):
                label = ctk.CTkLabel(
                    header_frame,
                    text=header,
                    font=ctk.CTkFont(size=14, weight="bold"),
                    anchor="w"
                )
                label.grid(row=0, column=i, padx=5, pady=10, sticky="ew")
            
            # Adicionar reparações
            for repair in repairs:
                self.create_repair_row(repair)
        
        run_db_operation(self.app.root, db_operation, callback)
    
    def _show_repair_details_impl(self, repair: dict):
        """Implementação real do popup de detalhes (chamado após delay) - Padrão Withdraw-Update-Show para macOS"""
        # STEP 1: Criar janela e IMEDIATAMENTE esconder (withdraw)
        popup = ctk.CTkToplevel(self.app.root)
        popup.title(f"Detalhes da Reparação - {repair.get('client', 'Cliente')}")
        popup.withdraw()  # Esconder instantaneamente para evitar crash no macOS
        
        # STEP 2: Construir toda a UI enquanto a janela está escondida
        # Frame principal
        main_frame = ctk.CTkFrame(popup)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Título
        title_label = ctk.CTkLabel(
            main_frame,
            text=f"Reparação #{repair.get('id', 'N/A')} - {repair.get('client', 'Cliente')}",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=["#FF5722", "#FF5722"]
        )
        title_label.pack(pady=(0, 20))
        
        # Frame scrollável para conteúdo
        scrollable = ctk.CTkScrollableFrame(main_frame)
        scrollable.pack(fill="both", expand=True)
        
        # Seção 1: Descrição Completa
        desc_frame = ctk.CTkFrame(scrollable, fg_color=["#f9f9f9", "#2b2b2b"])
        desc_frame.pack(fill="x", padx=10, pady=10)
        
        desc_title = ctk.CTkLabel(
            desc_frame,
            text="Descrição Completa:",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w"
        )
        desc_title.pack(fill="x", padx=15, pady=(15, 10))
        
        description = repair.get("description", "Nenhuma descrição disponível")
        desc_text = ctk.CTkTextbox(
            desc_frame,
            height=150,
            font=ctk.CTkFont(size=13),
            wrap="word"
        )
        desc_text.pack(fill="x", padx=15, pady=(0, 15))
        desc_text.insert("1.0", description)
        desc_text.configure(state="disabled")  # Read-only
        
        # Seção 2: Componentes Utilizados (Tabela com 3 colunas)
        parts_frame = ctk.CTkFrame(scrollable, fg_color=["#f9f9f9", "#2b2b2b"])
        parts_frame.pack(fill="x", padx=10, pady=10)
        
        parts_title = ctk.CTkLabel(
            parts_frame,
            text="Componentes Utilizados:",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w"
        )
        parts_title.pack(fill="x", padx=15, pady=(15, 10))
        
        used_parts = repair.get("used_parts", "Nenhum")
        if used_parts and used_parts != "Nenhum":
            # Criar tabela com cabeçalho
            table_container = ctk.CTkFrame(parts_frame, fg_color="transparent")
            table_container.pack(fill="x", padx=15, pady=(0, 15))
            
            # Configurar grid para 3 colunas
            table_container.grid_columnconfigure(0, weight=1, uniform="parts_cols")
            table_container.grid_columnconfigure(1, weight=3, uniform="parts_cols")
            table_container.grid_columnconfigure(2, weight=1, uniform="parts_cols")
            
            # Cabeçalho da tabela
            header_frame = ctk.CTkFrame(table_container, fg_color=["#e0e0e0", "#2b2b2b"])
            header_frame.pack(fill="x", pady=(0, 5))
            header_frame.grid_columnconfigure(0, weight=1, uniform="parts_cols")
            header_frame.grid_columnconfigure(1, weight=3, uniform="parts_cols")
            header_frame.grid_columnconfigure(2, weight=1, uniform="parts_cols")
            
            headers = ["Código", "Nome", "Quantidade"]
            for i, header in enumerate(headers):
                header_label = ctk.CTkLabel(
                    header_frame,
                    text=header,
                    font=ctk.CTkFont(size=13, weight="bold"),
                    anchor="w"
                )
                header_label.grid(row=0, column=i, padx=5, pady=8, sticky="ew")
            
            # Parse components usando o método do db_manager (suporta ID:QTY e Code (Qty))
            # Carregar códigos válidos para greedy matching (formato antigo)
            all_components_for_parse = self.app.db_manager.get_all_components()
            valid_codes = [c["code"] for c in all_components_for_parse] if all_components_for_parse else None
            parsed_components = self.app.db_manager._parse_used_parts(used_parts, valid_codes=valid_codes)
            
            for id_or_code, qty in parsed_components:
                # Determinar se é ID ou código e buscar componente
                if isinstance(id_or_code, int):
                    # É um ID (formato novo)
                    component = self.app.db_manager.get_component_by_id(id_or_code)
                    if component:
                        code = component.get("code", f"ID {id_or_code}")
                        name = component.get("name", code)
                    else:
                        code = f"ID {id_or_code}"
                        name = code
                else:
                    # É um código (formato antigo)
                    code = id_or_code
                    name = self.app.db_manager.get_component_name_by_code(code)
                
                # Converter qty para string se necessário
                qty_display = str(qty) if isinstance(qty, int) else str(qty)
                
                # Criar linha da tabela
                row_frame = ctk.CTkFrame(table_container, fg_color="transparent")
                row_frame.pack(fill="x", pady=2)
                row_frame.grid_columnconfigure(0, weight=1, uniform="parts_cols")
                row_frame.grid_columnconfigure(1, weight=3, uniform="parts_cols")
                row_frame.grid_columnconfigure(2, weight=1, uniform="parts_cols")
                
                # Código (Coluna 1)
                code_label = ctk.CTkLabel(
                    row_frame,
                    text=code,
                    font=ctk.CTkFont(size=12),
                    anchor="w"
                )
                code_label.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
                
                # Nome (Coluna 2) - obtido da base de dados
                name_label = ctk.CTkLabel(
                    row_frame,
                    text=name,
                    font=ctk.CTkFont(size=12),
                    anchor="w"
                )
                name_label.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
                
                # Quantidade (Coluna 3)
                qty_label = ctk.CTkLabel(
                    row_frame,
                    text=qty_display,
                    font=ctk.CTkFont(size=12),
                    anchor="w"
                )
                qty_label.grid(row=0, column=2, padx=5, pady=5, sticky="ew")
        else:
            no_parts = ctk.CTkLabel(
                parts_frame,
                text="Nenhum componente utilizado",
                font=ctk.CTkFont(size=13),
                text_color=["#666666", "#999999"],
                anchor="w"
            )
            no_parts.pack(fill="x", padx=15, pady=(0, 15))
        
        # Seção 3: Informações Adicionais
        info_frame = ctk.CTkFrame(scrollable, fg_color=["#f9f9f9", "#2b2b2b"])
        info_frame.pack(fill="x", padx=10, pady=10)
        
        info_title = ctk.CTkLabel(
            info_frame,
            text="Informações Adicionais:",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w"
        )
        info_title.pack(fill="x", padx=15, pady=(15, 10))
        
        # Data
        date_str = repair.get("date", "")
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            formatted_date = dt.strftime("%d/%m/%Y %H:%M")
        except:
            formatted_date = date_str
        
        date_info = ctk.CTkLabel(
            info_frame,
            text=f"Data: {formatted_date}",
            font=ctk.CTkFont(size=13),
            anchor="w"
        )
        date_info.pack(fill="x", padx=15, pady=2)
        
        # IMEI / Nº Série
        device_imei = repair.get("device_imei", "") or ""
        if device_imei:
            imei_info = ctk.CTkLabel(
                info_frame,
                text=f"IMEI / Nº Série: {device_imei}",
                font=ctk.CTkFont(size=13),
                anchor="w"
            )
            imei_info.pack(fill="x", padx=15, pady=2)
        
        # Nº Garantia
        warranty_number = repair.get("warranty_number", "") or ""
        if warranty_number:
            warranty_info = ctk.CTkLabel(
                info_frame,
                text=f"Nº Garantia: {warranty_number}",
                font=ctk.CTkFont(size=13),
                anchor="w"
            )
            warranty_info.pack(fill="x", padx=15, pady=2)
        
        # Total
        total_info = ctk.CTkLabel(
            info_frame,
            text=f"Total: {repair.get('total', 0.0):.2f} €",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=["#FF5722", "#FF5722"],
            anchor="w"
        )
        total_info.pack(fill="x", padx=15, pady=2)
        
        # Estado
        payment_status = repair.get("payment_status", "Pendente")
        status_info = ctk.CTkLabel(
            info_frame,
            text=f"Estado: {payment_status}",
            font=ctk.CTkFont(size=13),
            text_color=["#4CAF50", "#4CAF50"] if payment_status == "Pago" else ["#F44336", "#F44336"],
            anchor="w"
        )
        status_info.pack(fill="x", padx=15, pady=(0, 15))
        
        # Botões (Editar e Fechar)
        buttons_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        buttons_frame.pack(pady=(20, 0))
        
        # Botão Editar Dados
        edit_button = ctk.CTkButton(
            buttons_frame,
            text="Editar Dados",
            command=lambda: self.open_edit_repair_window(repair.get('id'), popup),
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=["#2196F3", "#2196F3"],
            hover_color=["#1976D2", "#1976D2"],
            width=150,
            height=40
        )
        edit_button.pack(side="left", padx=(0, 10))
        
        # Botão Fechar
        close_button = ctk.CTkButton(
            buttons_frame,
            text="Fechar",
            command=popup.destroy,
            font=ctk.CTkFont(size=14),
            fg_color=["#666666", "#666666"],
            hover_color=["#555555", "#555555"],
            width=150,
            height=40
        )
        close_button.pack(side="left")
        
        # STEP 3: Configurar geometria e forçar cálculo de layout
        popup.geometry("600x450")
        popup.resizable(False, False)
        popup.transient(self.app.root)
        popup.update_idletasks()  # Forçar Tkinter a calcular layout
        
        # STEP 4: Centralizar antes de mostrar
        x = (popup.winfo_screenwidth() // 2) - (popup.winfo_width() // 2)
        y = (popup.winfo_screenheight() // 2) - (popup.winfo_height() // 2)
        popup.geometry(f"600x450+{x}+{y}")
        
        # STEP 5: Mostrar a janela (deiconify) e usar topmost (mais seguro que grab no macOS)
        popup.deiconify()  # Mostrar a janela
        popup.attributes("-topmost", True)  # Manter no topo (mais seguro que grab_set no macOS)
    
    def show_repair_details(self, repair: dict):
        """Abre popup com detalhes completos da reparação (com delay para evitar crash no macOS)"""
        # Usar after() com delay maior (100ms) para evitar segmentation fault no macOS
        # Isso dá tempo para a animação do botão terminar completamente
        self.after(100, lambda: self._show_repair_details_impl(repair))
    
    def open_edit_repair_window(self, repair_id: int, details_popup=None):
        """
        Abre janela de edição de dados da reparação
        
        Args:
            repair_id: ID da reparação a editar
            details_popup: Janela de detalhes (opcional, para fechar após abrir edição)
        """
        # Fechar janela de detalhes se estiver aberta
        if details_popup:
            details_popup.destroy()
        
        # Carregar dados da reparação
        def load_repair_data():
            def db_operation():
                # Não usar get_all_repairs() (agora é limitado); buscar diretamente por ID
                return self.app.db_manager.get_repair_by_id(repair_id)
            
            def callback(repair, error):
                if error:
                    messagebox.showerror("Erro", f"Erro ao carregar reparação: {str(error)}")
                    return
                
                if not repair:
                    messagebox.showerror("Erro", "Reparação não encontrada!")
                    return
                
                # Criar janela de edição
                edit_dialog = ctk.CTkToplevel(self.app.root)
                edit_dialog.title(f"Editar Reparação #{repair_id}")
                edit_dialog.geometry("800x800")
                edit_dialog.minsize(700, 700)
                edit_dialog.resizable(True, True)
                edit_dialog.transient(self.app.root)
                
                # Centralizar
                edit_dialog.update_idletasks()
                x = (edit_dialog.winfo_screenwidth() // 2) - (800 // 2)
                y = (edit_dialog.winfo_screenheight() // 2) - (800 // 2)
                edit_dialog.geometry(f"800x800+{x}+{y}")
                
                # Container principal
                main_frame = ctk.CTkFrame(edit_dialog)
                main_frame.pack(fill="both", expand=True, padx=20, pady=20)
                
                # Título
                title_label = ctk.CTkLabel(
                    main_frame,
                    text=f"Editar Reparação #{repair_id}",
                    font=ctk.CTkFont(size=20, weight="bold"),
                    text_color=["#FF5722", "#FF5722"]
                )
                title_label.pack(pady=(0, 15))
                
                # Frame scrollável para campos
                scrollable = ctk.CTkScrollableFrame(main_frame)
                scrollable.pack(fill="both", expand=True, pady=(0, 20))
                
                # Helper function para criar campos
                def create_field(parent, label_text, default_value="", is_textbox=False):
                    frame = ctk.CTkFrame(parent, fg_color="transparent")
                    frame.pack(fill="x", padx=10, pady=8)
                    
                    label = ctk.CTkLabel(
                        frame,
                        text=label_text,
                        font=ctk.CTkFont(size=12, weight="bold"),
                        anchor="w"
                    )
                    label.pack(fill="x", pady=(0, 5))
                    
                    if is_textbox:
                        entry = ctk.CTkTextbox(
                            frame,
                            height=100,
                            font=ctk.CTkFont(size=13),
                            wrap="word"
                        )
                        entry.pack(fill="x")
                        if default_value:
                            entry.insert("1.0", str(default_value))
                    else:
                        entry = ctk.CTkEntry(
                            frame,
                            font=ctk.CTkFont(size=13),
                            height=35
                        )
                        entry.pack(fill="x")
                        if default_value:
                            entry.insert(0, str(default_value))
                    
                    return entry
                
                # Campos editáveis - Informações Básicas
                device_entry = create_field(
                    scrollable, 
                    "Dispositivo (IMEI / Nº Série):", 
                    repair.get("device_imei", "")
                )
                
                problem_entry = create_field(
                    scrollable,
                    "Tipo de Equipamento:",
                    repair.get("problem_summary", "")
                )
                
                warranty_entry = create_field(
                    scrollable,
                    "Número de Garantia:",
                    repair.get("warranty_number", "")
                )
                
                description_entry = create_field(
                    scrollable,
                    "Descrição Completa:",
                    repair.get("description", ""),
                    is_textbox=True
                )
                
                # ========== SEÇÃO: COMPONENTES USADOS ==========
                components_section = ctk.CTkFrame(scrollable, fg_color=["#f9f9f9", "#2b2b2b"])
                components_section.pack(fill="x", padx=10, pady=15)
                
                # Título da seção
                components_title = ctk.CTkLabel(
                    components_section,
                    text="Componentes Usados",
                    font=ctk.CTkFont(size=16, weight="bold"),
                    anchor="w"
                )
                components_title.pack(fill="x", padx=15, pady=(15, 10))
                
                # Estrutura de dados para componentes selecionados
                # Lista de dicts: [{"id": int, "code": str, "name": str, "price": float, "qty": int}, ...]
                selected_components_list = []
                
                # Container para a lista de componentes (scrollable)
                components_list_container = ctk.CTkScrollableFrame(components_section, height=200)
                components_list_container.pack(fill="both", expand=True, padx=15, pady=(0, 10))
                
                # Label para total de peças (será atualizado dinamicamente)
                total_parts_label = ctk.CTkLabel(
                    components_section,
                    text="Total Peças: 0.00 €",
                    font=ctk.CTkFont(size=14, weight="bold"),
                    text_color=["#FF5722", "#FF5722"],
                    anchor="w"
                )
                total_parts_label.pack(fill="x", padx=15, pady=(0, 10))
                
                # Função para atualizar o total de peças
                def update_parts_total():
                    total = sum(comp["price"] * comp["qty"] for comp in selected_components_list)
                    total_parts_label.configure(text=f"Total Peças: {total:.2f} €")
                
                # Função para criar uma linha de componente na lista
                def create_component_row(component_data):
                    """Cria uma linha visual para um componente na lista"""
                    item_frame = ctk.CTkFrame(components_list_container)
                    item_frame.pack(fill="x", pady=3)
                    
                    # Informações do componente
                    info_frame = ctk.CTkFrame(item_frame, fg_color="transparent")
                    info_frame.pack(side="left", fill="x", expand=True, padx=10, pady=8)
                    
                    # Nome e código
                    name_label = ctk.CTkLabel(
                        info_frame,
                        text=f"{component_data['code']} - {component_data['name']}",
                        font=ctk.CTkFont(size=12, weight="bold"),
                        anchor="w"
                    )
                    name_label.pack(fill="x")
                    
                    # Preço unitário e subtotal
                    subtotal = component_data["price"] * component_data["qty"]
                    details_label = ctk.CTkLabel(
                        info_frame,
                        text=f"Preço Unit.: {component_data['price']:.2f} € | Qtd: {component_data['qty']} | Total: {subtotal:.2f} €",
                        font=ctk.CTkFont(size=11),
                        text_color=["#666666", "#999999"],
                        anchor="w"
                    )
                    details_label.pack(fill="x")
                    
                    # Frame para botões
                    buttons_frame = ctk.CTkFrame(item_frame, fg_color="transparent")
                    buttons_frame.pack(side="right", padx=10, pady=8)
                    
                    # Botão remover (X) - Pack primeiro para ficar à direita
                    def safe_remove_command(comp_id):
                        try:
                            # Remover da lista
                            selected_components_list[:] = [c for c in selected_components_list if c["id"] != comp_id]
                            # Atualizar UI
                            refresh_components_list()
                            update_parts_total()
                        except Exception:
                            pass
                    
                    remove_button = ctk.CTkButton(
                        buttons_frame,
                        text="X",
                        command=lambda: safe_remove_command(component_data["id"]),
                        font=ctk.CTkFont(size=14, weight="bold"),
                        fg_color=["#f44336", "#f44336"],
                        hover_color=["#d32f2f", "#d32f2f"],
                        width=35,
                        height=30
                    )
                    remove_button.pack(side="right")
                    
                    # Botão aumentar quantidade (+)
                    def safe_increase_command(comp_id):
                        try:
                            for comp in selected_components_list:
                                if comp["id"] == comp_id:
                                    comp["qty"] += 1
                                    break
                            refresh_components_list()
                            update_parts_total()
                        except Exception:
                            pass
                    
                    increase_button = ctk.CTkButton(
                        buttons_frame,
                        text="+",
                        command=lambda: safe_increase_command(component_data["id"]),
                        font=ctk.CTkFont(size=16, weight="bold"),
                        fg_color=["#4CAF50", "#4CAF50"],
                        hover_color=["#45a049", "#45a049"],
                        width=35,
                        height=30
                    )
                    increase_button.pack(side="right", padx=(0, 5))
                    
                    # Label de quantidade
                    qty_label = ctk.CTkLabel(
                        buttons_frame,
                        text=str(component_data["qty"]),
                        font=ctk.CTkFont(size=14, weight="bold"),
                        width=40
                    )
                    qty_label.pack(side="right", padx=5)
                    
                    # Botão diminuir quantidade (-) - apenas se qty > 1
                    if component_data["qty"] > 1:
                        def safe_decrease_command(comp_id):
                            try:
                                for comp in selected_components_list:
                                    if comp["id"] == comp_id and comp["qty"] > 1:
                                        comp["qty"] -= 1
                                        break
                                refresh_components_list()
                                update_parts_total()
                            except Exception:
                                pass
                        
                        decrease_button = ctk.CTkButton(
                            buttons_frame,
                            text="-",
                            command=lambda: safe_decrease_command(component_data["id"]),
                            font=ctk.CTkFont(size=16, weight="bold"),
                            fg_color=["#F39C12", "#F39C12"],
                            hover_color=["#D35400", "#D35400"],
                            width=35,
                            height=30
                        )
                        decrease_button.pack(side="right", padx=(0, 5))
                
                # Função para atualizar a lista visual de componentes
                def refresh_components_list():
                    # Limpar container
                    for widget in components_list_container.winfo_children():
                        widget.destroy()
                    
                    # Recriar linhas
                    for comp in selected_components_list:
                        create_component_row(comp)
                    
                    # Se lista vazia, mostrar mensagem
                    if not selected_components_list:
                        empty_label = ctk.CTkLabel(
                            components_list_container,
                            text="Nenhum componente adicionado",
                            font=ctk.CTkFont(size=12),
                            text_color=["#666666", "#999999"]
                        )
                        empty_label.pack(pady=20)
                
                # Barra de pesquisa e adicionar
                # Frame para pesquisa de componentes
                search_frame = ctk.CTkFrame(components_section, fg_color="transparent")
                search_frame.pack(fill="x", padx=15, pady=(0, 15))
                
                # Label
                search_label = ctk.CTkLabel(
                    search_frame,
                    text="Pesquisar Componente (Nome ou Código):",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    anchor="w"
                )
                search_label.pack(fill="x", pady=(0, 5))
                
                # Entry para pesquisa
                component_search_entry = ctk.CTkEntry(
                    search_frame,
                    font=ctk.CTkFont(size=12),
                    placeholder_text="Digite nome ou código..."
                )
                component_search_entry.pack(fill="x", pady=(0, 5))
                
                # Frame para resultados da pesquisa (suggestions list)
                component_results_frame = ctk.CTkScrollableFrame(
                    search_frame,
                    fg_color=["#ffffff", "#2b2b2b"],
                    height=150  # Altura máxima limitada
                )
                component_results_frame.pack(fill="x", padx=0, pady=(0, 0))
                component_results_frame.pack_forget()  # Ocultar inicialmente
                
                # Variáveis para armazenar dados de componentes
                all_components = []  # Lista completa de componentes (dicts)
                search_timer = None  # Timer para debouncing
                
                # Função para pesquisar componentes (executada após delay)
                def perform_component_search():
                    """Executa a pesquisa real de componentes"""
                    query = component_search_entry.get().strip().lower()
                    
                    # Limpar resultados anteriores
                    for widget in component_results_frame.winfo_children():
                        widget.destroy()
                    
                    if not query or len(query) < 1:
                        # Se vazio, ocultar resultados
                        component_results_frame.pack_forget()
                        return
                    
                    # Filtrar componentes que contêm o texto (case-insensitive)
                    # Buscar em código ou nome
                    filtered = [
                        comp for comp in all_components
                        if query in comp.get('code', '').lower() or query in comp.get('name', '').lower()
                    ]
                    
                    if not filtered:
                        # Nenhum resultado
                        no_results = ctk.CTkLabel(
                            component_results_frame,
                            text="Nenhum componente encontrado",
                            font=ctk.CTkFont(size=12),
                            text_color=["#999999", "#666666"]
                        )
                        no_results.pack(pady=10)
                        component_results_frame.pack(fill="x", padx=0, pady=(5, 0))
                        return
                    
                    # Mostrar resultados (máximo 10 para não sobrecarregar)
                    max_results = min(10, len(filtered))
                    for comp in filtered[:max_results]:
                        comp_frame = ctk.CTkFrame(component_results_frame, fg_color="transparent")
                        comp_frame.pack(fill="x", padx=5, pady=2)
                        
                        # Formato: [ID] Name | Stock: X
                        stock_qty = comp.get('qty', 0)
                        comp_info = f"[{comp.get('code', 'N/A')}] {comp.get('name', 'N/A')} | Stock: {stock_qty}"
                        
                        comp_button = ctk.CTkButton(
                            comp_frame,
                            text=comp_info,
                            command=lambda c=comp: select_component(c),
                            font=ctk.CTkFont(size=11),
                            fg_color=["#e0e0e0", "#3a3a3a"],
                            hover_color=["#d0d0d0", "#4a4a4a"],
                            anchor="w",
                            height=30
                        )
                        comp_button.pack(fill="x")
                    
                    # Mostrar frame de resultados
                    component_results_frame.pack(fill="x", padx=0, pady=(5, 0))
                
                # Função para pesquisar componentes (com debouncing)
                def on_component_search(event=None):
                    """Handler para pesquisa de componentes (com debounce)"""
                    nonlocal search_timer
                    
                    # Cancelar timer anterior se existir
                    if search_timer:
                        edit_dialog.after_cancel(search_timer)
                    
                    # Agendar pesquisa após 300ms
                    search_timer = edit_dialog.after(300, perform_component_search)
                
                # Bind KeyRelease no entry
                component_search_entry.bind("<KeyRelease>", on_component_search)
                
                # Função para selecionar um componente
                def select_component(comp):
                    """Adiciona um componente à lista de componentes usados"""
                    # Verificar se já existe na lista
                    existing_idx = None
                    for i, selected_comp in enumerate(selected_components_list):
                        if selected_comp["id"] == comp["id"]:
                            existing_idx = i
                            break
                    
                    if existing_idx is not None:
                        # Incrementar quantidade
                        selected_components_list[existing_idx]["qty"] += 1
                    else:
                        # Adicionar novo componente
                        selected_components_list.append({
                            "id": comp["id"],
                            "code": comp["code"],
                            "name": comp["name"],
                            "price": comp.get("price", 0.0),
                            "qty": 1
                        })
                    
                    # Limpar pesquisa e ocultar resultados
                    component_search_entry.delete(0, "end")
                    component_results_frame.pack_forget()
                    
                    # Atualizar UI
                    refresh_components_list()
                    update_parts_total()
                
                # Carregar todos os componentes
                def load_components_for_search():
                    def db_operation():
                        return self.app.db_manager.get_all_components()
                    
                    def callback(components, error):
                        nonlocal all_components
                        
                        if error:
                            messagebox.showerror("Erro", f"Erro ao carregar componentes: {str(error)}")
                            return
                        
                        # Armazenar lista completa de componentes
                        all_components = components
                    
                    run_db_operation(self.app.root, db_operation, callback)
                
                # Carregar componentes
                load_components_for_search()
                
                # Parse componentes existentes da reparação
                used_parts_str = repair.get("used_parts", "")
                if used_parts_str and used_parts_str.strip() and used_parts_str.strip() != "Nenhum":
                    # Carregar dados completos dos componentes
                    def load_existing_components():
                        def db_operation():
                            # Buscar todos os componentes para lookup (por ID e por código)
                            all_components_db = self.app.db_manager.get_all_components()
                            component_lookup_by_code = {c["code"]: c for c in all_components_db}
                            component_lookup_by_id = {c["id"]: c for c in all_components_db}
                            
                            # Obter lista de códigos válidos para greedy matching (formato antigo)
                            valid_codes = [c["code"] for c in all_components_db] if all_components_db else None
                            
                            # Usar o método do db_manager para parse com greedy matching
                            parsed_components = self.app.db_manager._parse_used_parts(used_parts_str, valid_codes=valid_codes)
                            
                            # Construir lista de componentes selecionados
                            result = []
                            for id_or_code, qty in parsed_components:
                                comp = None
                                
                                # Determinar se é ID ou código
                                if isinstance(id_or_code, int):
                                    # É um ID (formato novo: ID:QTY)
                                    comp = component_lookup_by_id.get(id_or_code)
                                else:
                                    # É um código (formato antigo: Code (Qty))
                                    comp = component_lookup_by_code.get(id_or_code)
                                
                                if comp:
                                    result.append({
                                        "id": comp["id"],
                                        "code": comp["code"],
                                        "name": comp["name"],
                                        "price": comp.get("price", 0.0),
                                        "qty": qty
                                    })
                            return result
                        
                        def callback(components, error):
                            if error:
                                messagebox.showerror("Erro", f"Erro ao carregar componentes: {str(error)}")
                            else:
                                selected_components_list.extend(components)
                                refresh_components_list()
                                update_parts_total()
                        
                        run_db_operation(self.app.root, db_operation, callback)
                    
                    load_existing_components()
                else:
                    # Lista vazia, mostrar mensagem
                    refresh_components_list()
                
                # Separador visual
                separator = ctk.CTkFrame(scrollable, fg_color=["#e0e0e0", "#444444"], height=2)
                separator.pack(fill="x", padx=10, pady=15)
                
                # Campos de Custos - Mão de Obra
                hours_label = ctk.CTkLabel(
                    scrollable,
                    text="Horas de Mão de Obra:",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    anchor="w"
                )
                hours_label.pack(fill="x", padx=10, pady=(5, 5))
                
                hours_entry = ctk.CTkEntry(
                    scrollable,
                    font=ctk.CTkFont(size=13),
                    height=35
                )
                hours_entry.pack(fill="x", padx=10, pady=(0, 10))
                hours_entry.insert(0, str(repair.get("hours_worked", 1.0)))
                
                # Tipo de Mão de Obra
                labor_type_label = ctk.CTkLabel(
                    scrollable,
                    text="Tipo de Mão de Obra:",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    anchor="w"
                )
                labor_type_label.pack(fill="x", padx=10, pady=(5, 5))
                
                # Determinar tipo de mão de obra atual
                current_labor_type = repair.get("labor_type", "labor1")
                labor_type_map = {
                    "labor1": "Mão de Obra 1",
                    "labor2": "Mão de Obra 2",
                    "placas": "Placas"
                }
                # Mapear de volta para valores do DB
                reverse_map = {v: k for k, v in labor_type_map.items()}
                current_display = labor_type_map.get(current_labor_type, "Mão de Obra 1")
                
                labor_type_segmented = ctk.CTkSegmentedButton(
                    scrollable,
                    values=["Mão de Obra 1", "Mão de Obra 2", "Placas"],
                    font=ctk.CTkFont(size=12),
                    height=35
                )
                labor_type_segmented.pack(fill="x", padx=10, pady=(0, 10))
                labor_type_segmented.set(current_display)
                
                # Eletricidade
                electricity_entry = create_field(
                    scrollable,
                    "Horas de Eletricidade:",
                    str(repair.get("electricity_hours", 0.0))
                )
                
                # Transporte
                weight_entry = create_field(
                    scrollable,
                    "Peso da Encomenda (Kg):",
                    str(repair.get("package_weight", 0.0))
                )
                
                # Testes/Diagnóstico
                test_frame = ctk.CTkFrame(scrollable, fg_color="transparent")
                test_frame.pack(fill="x", padx=10, pady=8)
                
                test_label = ctk.CTkLabel(
                    test_frame,
                    text="Realizou Testes/Diagnóstico?",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    anchor="w"
                )
                test_label.pack(fill="x", pady=(0, 5))
                
                # Switch para testes
                test_switch = ctk.CTkSwitch(
                    test_frame,
                    text="Sim",
                    font=ctk.CTkFont(size=12)
                )
                test_switch.pack(side="left", pady=(0, 10))
                
                # Verificar se há horas de teste para ativar switch
                horas_teste = repair.get("horas_teste", 0.0)
                if horas_teste and horas_teste > 0:
                    test_switch.select()
                
                # Campo de horas de teste
                test_hours_frame = ctk.CTkFrame(test_frame, fg_color="transparent")
                test_hours_frame.pack(fill="x", pady=(5, 0))
                
                test_hours_label = ctk.CTkLabel(
                    test_hours_frame,
                    text="Horas de Teste:",
                    font=ctk.CTkFont(size=11),
                    anchor="w"
                )
                test_hours_label.pack(side="left", padx=(20, 10))
                
                test_hours_entry = ctk.CTkEntry(
                    test_hours_frame,
                    font=ctk.CTkFont(size=13),
                    height=30,
                    width=150
                )
                test_hours_entry.pack(side="left")
                if horas_teste and horas_teste > 0:
                    test_hours_entry.insert(0, str(horas_teste))
                else:
                    test_hours_entry.insert(0, "1.0")
                    test_hours_entry.configure(state="disabled")
                
                # Função para habilitar/desabilitar campo de horas de teste
                def on_test_switch_change():
                    if test_switch.get():
                        test_hours_entry.configure(state="normal")
                    else:
                        test_hours_entry.configure(state="disabled")
                        test_hours_entry.delete(0, "end")
                        test_hours_entry.insert(0, "0.0")
                
                test_switch.configure(command=on_test_switch_change)
                
                # Botões de ação
                buttons_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
                buttons_frame.pack(fill="x")
                
                def save_changes():
                    try:
                        # Validar campos obrigatórios
                        description = description_entry.get("1.0", "end-1c").strip()
                        if not description:
                            messagebox.showwarning("Atenção", "A descrição é obrigatória!")
                            return
                        
                        # Coletar valores dos campos
                        hours_worked = float(hours_entry.get().strip().replace(",", ".") or "1.0")
                        electricity_hours = float(electricity_entry.get().strip().replace(",", ".") or "0.0")
                        package_weight = float(weight_entry.get().strip().replace(",", ".") or "0.0")
                        
                        # Tipo de mão de obra
                        labor_type_display = labor_type_segmented.get()
                        labor_type_map = {
                            "Mão de Obra 1": "labor1",
                            "Mão de Obra 2": "labor2",
                            "Placas": "placas"
                        }
                        labor_type = labor_type_map.get(labor_type_display, "labor1")
                        
                        # Horas de teste
                        test_switch_on = test_switch.get()
                        if test_switch_on:
                            horas_teste = float(test_hours_entry.get().strip().replace(",", ".") or "0.0")
                        else:
                            horas_teste = 0.0
                        
                        # Carregar taxas atuais da base de dados
                        labor_rate_1 = float(self.app.db_manager.get_setting("labor_rate_1", "30.0"))
                        labor_rate_2 = float(self.app.db_manager.get_setting("labor_rate_2", "45.0"))
                        placas_price = float(self.app.db_manager.get_setting("placas_price", "50.0"))
                        electricity_rate = float(self.app.db_manager.get_setting("electricity_rate", "0.50"))
                        test_rate = float(self.app.db_manager.get_setting("test_hourly_rate", "20.0"))
                        
                        # Calcular custos
                        # Custo de mão de obra
                        if labor_type == "labor1":
                            labor_cost = hours_worked * labor_rate_1
                        elif labor_type == "labor2":
                            labor_cost = hours_worked * labor_rate_2
                        else:  # placas
                            labor_cost = hours_worked * placas_price
                        
                        # Custo de eletricidade
                        elec_cost = electricity_hours * electricity_rate
                        
                        # Custo de transporte (usar método do service_page se disponível, senão calcular manualmente)
                        transport_cost = 0.0
                        if package_weight > 0:
                            transport_rules = self.app.db_manager.get_transport_rules()
                            if transport_rules:
                                # Normalizar regras
                                normalized_rules = []
                                for rule in transport_rules:
                                    if "max" in rule and "max_weight" not in rule:
                                        normalized_rules.append({"max": rule.get("max", 0), "price": rule.get("price", 0)})
                                    elif "max_weight" in rule:
                                        normalized_rules.append({"max": rule.get("max_weight", 0), "price": rule.get("price", 0)})
                                
                                if normalized_rules:
                                    sorted_rules = sorted(normalized_rules, key=lambda x: x.get("max", 0))
                                    previous_max = 0.0
                                    for rule in sorted_rules:
                                        max_weight = rule.get("max", 0.0)
                                        if previous_max < package_weight <= max_weight:
                                            transport_cost = rule.get("price", 0.0)
                                            break
                                        previous_max = max_weight
                        
                        # Custo de testes
                        test_cost = horas_teste * test_rate if test_switch_on and horas_teste > 0 else 0.0
                        
                        # Calcular custo de peças a partir da lista de componentes selecionados
                        parts_cost = 0.0
                        used_parts_list = []
                        
                        for comp in selected_components_list:
                            # Calcular custo
                            parts_cost += comp["price"] * comp["qty"]
                            
                            # Usar formato ID:QTY para evitar problemas com caracteres especiais no código
                            used_parts_list.append(f"{comp['id']}:{comp['qty']}")
                        
                        # Construir string final de used_parts (formato: "ID:QTY,ID:QTY")
                        used_parts_str = ",".join(used_parts_list) if used_parts_list else "Nenhum"
                        
                        # Total = Peças + Mão de Obra + Eletricidade + Transporte + Testes
                        total = parts_cost + labor_cost + elec_cost + transport_cost + test_cost
                        
                        # Preço por hora de teste (para armazenar)
                        preco_hora_teste = test_rate if test_switch_on and horas_teste > 0 else 0.0
                        
                        # Coletar todos os dados
                        new_data = {
                            'device_imei': device_entry.get().strip(),
                            'problem_summary': problem_entry.get().strip(),
                            'warranty_number': warranty_entry.get().strip(),
                            'description': description,
                            'hours_worked': hours_worked,
                            'used_parts': used_parts_str,
                            'labor_type': labor_type,
                            'electricity_hours': electricity_hours,
                            'package_weight': package_weight,
                            'transport_cost': transport_cost,
                            'horas_teste': horas_teste,
                            'preco_hora_teste': preco_hora_teste,
                            'total': total  # Será recalculado no backend com custo de peças
                        }
                        
                        # Atualizar base de dados com validação de stock
                        def db_operation():
                            try:
                                return self.app.db_manager.update_repair_with_stock_validation(repair_id, new_data)
                            except ValueError as ve:
                                # Re-raise ValueError para ser tratado no callback
                                raise ve
                            except Exception as e:
                                # Outros erros também são re-levantados
                                raise ValueError(f"Erro ao atualizar reparação: {str(e)}")
                        
                        def callback(result, error):
                            if error:
                                # Verificar se é erro de stock insuficiente
                                error_msg = str(error)
                                if "Stock insuficiente" in error_msg or "insuficiente" in error_msg.lower():
                                    messagebox.showerror(
                                        "Stock Insuficiente",
                                        f"{error_msg}\n\n"
                                        "Por favor, ajuste as quantidades ou verifique o stock disponível."
                                    )
                                else:
                                    messagebox.showerror("Erro", f"Erro ao guardar alterações: {error_msg}")
                            elif result:
                                messagebox.showinfo(
                                    "Operação Concluída",
                                    f"Dados da reparação atualizados com sucesso!\n\n"
                                    f"Total recalculado: {total:.2f} €"
                                )
                                edit_dialog.destroy()
                                # Atualizar tabela principal
                                self.refresh_data(force=True)
                            else:
                                messagebox.showerror("Erro", "Erro ao guardar alterações!")
                        
                        run_db_operation(self.app.root, db_operation, callback)
                        
                    except ValueError as e:
                        # Erro de validação (stock ou valores numéricos)
                        error_msg = str(e)
                        if "Stock insuficiente" in error_msg or "insuficiente" in error_msg.lower():
                            messagebox.showerror(
                                "Stock Insuficiente",
                                f"{error_msg}\n\n"
                                "Por favor, ajuste as quantidades ou verifique o stock disponível."
                            )
                        else:
                            messagebox.showerror("Erro", f"Por favor, insira valores numéricos válidos!\n\n{error_msg}")
                    except Exception as e:
                        messagebox.showerror("Erro", f"Erro inesperado: {str(e)}")
                
                save_button = ctk.CTkButton(
                    buttons_frame,
                    text="Guardar Alterações",
                    command=save_changes,
                    font=ctk.CTkFont(size=14, weight="bold"),
                    fg_color=["#4CAF50", "#4CAF50"],
                    hover_color=["#45a049", "#45a049"],
                    height=40
                )
                save_button.pack(side="left", padx=(0, 10), expand=True)
                
                cancel_button = ctk.CTkButton(
                    buttons_frame,
                    text="Cancelar",
                    command=edit_dialog.destroy,
                    font=ctk.CTkFont(size=14),
                    fg_color="transparent",
                    hover_color=["#555555", "#333333"],
                    height=40
                )
                cancel_button.pack(side="left", expand=True)
            
            run_db_operation(self.app.root, db_operation, callback)
        
        # Carregar dados após um pequeno delay
        self.after(100, load_repair_data)
    
    def create_repair_row(self, repair: dict):
        """Cria uma linha na lista para uma reparação"""
        row_frame = ctk.CTkFrame(self.list_container)
        row_frame.pack(fill="x", pady=2)
        
        # Configurar pesos das colunas (idêntico ao header)
        column_weights = [1, 2, 2, 1, 1, 1, 1, 2]
        for i, weight in enumerate(column_weights):
            row_frame.grid_columnconfigure(i, weight=weight, uniform="repair_cols")
        
        # Data
        date_str = repair["date"]
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            formatted_date = dt.strftime("%d/%m/%Y")
        except:
            formatted_date = date_str
        
        date_label = ctk.CTkLabel(
            row_frame,
            text=formatted_date,
            font=ctk.CTkFont(size=12),
            text_color=["#666666", "#999999"],
            anchor="w"
        )
        date_label.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        
        # Cliente
        client_label = ctk.CTkLabel(
            row_frame,
            text=repair["client"],
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w"
        )
        client_label.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        # Tipo de Equipamento
        problem_summary = repair.get("problem_summary", "")
        if not problem_summary:
            problem_summary = "N/A"
        if len(problem_summary) > 40:
            problem_summary = problem_summary[:37] + "..."
        
        problem_label = ctk.CTkLabel(
            row_frame,
            text=problem_summary,
            font=ctk.CTkFont(size=13),
            anchor="w"
        )
        problem_label.grid(row=0, column=2, padx=5, pady=5, sticky="ew")
        
        # IMEI
        imei = repair.get("device_imei", "") or "N/A"
        if len(imei) > 15:
            imei = imei[:12] + "..."
        
        imei_label = ctk.CTkLabel(
            row_frame,
            text=imei,
            font=ctk.CTkFont(size=12),
            text_color=["#666666", "#999999"],
            anchor="w"
        )
        imei_label.grid(row=0, column=3, padx=5, pady=5, sticky="ew")
        
        # Total
        total_label = ctk.CTkLabel(
            row_frame,
            text=f"{repair['total']:.2f} €",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=["#FF5722", "#FF5722"],
            anchor="w"
        )
        total_label.grid(row=0, column=4, padx=5, pady=5, sticky="ew")
        
        # Progresso (Workflow Status) - Botão de ciclo
        repair_status = repair.get("repair_status", "Em Análise")
        if not repair_status:
            repair_status = "Em Análise"  # Fallback para registos antigos
        
        def cycle_repair_status():
            # Ciclar entre os 3 estados
            current_status = repair.get("repair_status", "Em Análise")
            if not current_status:
                current_status = "Em Análise"
            
            if current_status == "Em Análise":
                new_status = "Aguardar Peças"
            elif current_status == "Aguardar Peças":
                new_status = "Pronto a Entregar"
            else:  # "Pronto a Entregar"
                new_status = "Em Análise"
            
            # Atualizar base de dados
            def db_operation():
                return self.app.db_manager.update_repair_status(repair["id"], new_status)
            
            def callback(result, error):
                if error:
                    messagebox.showerror("Erro", f"Erro ao atualizar progresso: {str(error)}")
                elif result:
                    # Atualizar UI
                    self.refresh_data(force=True)
            
            run_db_operation(self.app.root, db_operation, callback)
        
        # Determinar cor e texto do botão
        status_colors = {
            "Em Análise": ["#3B8ED0", "#3B8ED0"],
            "Aguardar Peças": ["#E67E22", "#E67E22"],
            "Pronto a Entregar": ["#2CC985", "#2CC985"]
        }
        status_hover_colors = {
            "Em Análise": ["#2E6DA4", "#2E6DA4"],
            "Aguardar Peças": ["#D35400", "#D35400"],
            "Pronto a Entregar": ["#27AE60", "#27AE60"]
        }
        
        # Texto do botão (normalizar para versão curta se necessário)
        status_text = repair_status
        if repair_status == "A Aguardar Peças" or repair_status == "Aguardar Peças":
            status_text = "Aguardar Peças"  # Versão curta para o botão
        
        progress_button = ctk.CTkButton(
            row_frame,
            text=status_text,
            command=cycle_repair_status,
            font=ctk.CTkFont(family="Arial", size=10),
            fg_color=status_colors.get(repair_status, ["#3B8ED0", "#3B8ED0"]),
            hover_color=status_hover_colors.get(repair_status, ["#2E6DA4", "#2E6DA4"]),
            width=110,
            height=24
        )
        progress_button.grid(row=0, column=5, padx=5, pady=2, sticky="ew")
        
        # Estado de Pagamento (Toggle Button com confirmação)
        payment_status = repair.get("payment_status", "Pendente")
        is_paid = payment_status == "Pago"
        
        def toggle_payment_status():
            # Obter estado atual e calcular próximo estado
            current_status = repair.get("payment_status", "Pendente")
            new_status = "Pago" if current_status != "Pago" else "Pendente"
            
            # Mostrar diálogo de confirmação apropriado
            if new_status == "Pago":
                # Mudando para Pago
                confirm_message = "Confirmar pagamento desta reparação?\n\n(Mudar para 'Pago')"
                confirm_title = "Confirmar Pagamento"
            else:
                # Mudando para Pendente
                confirm_message = "Marcar esta reparação como não paga?\n\n(Mudar para 'Pendente')"
                confirm_title = "Confirmar Mudança de Estado"
            
            # Mostrar confirmação - só proceder se utilizador clicar "Sim"
            if not messagebox.askyesno(confirm_title, confirm_message):
                return  # Utilizador cancelou - não fazer nada
            
            # Proceder com atualização apenas se confirmado
            def db_operation():
                return self.app.db_manager.update_repair_payment_status(repair["id"], new_status)
            
            def callback(result, error):
                if error:
                    messagebox.showerror("Erro", f"Erro ao atualizar estado: {str(error)}")
                elif result:
                    # Atualizar UI
                    self.refresh_data(force=True)
            
            run_db_operation(self.app.root, db_operation, callback)
        
        # Botão de estado (verde se pago, vermelho/laranja se pendente) - COMPACTO E UNIFORME
        status_button = ctk.CTkButton(
            row_frame,
            text="Pago" if is_paid else "Pendente",
            command=toggle_payment_status,
            font=ctk.CTkFont(family="Arial", size=11, weight="bold"),
            fg_color=["#4CAF50", "#4CAF50"] if is_paid else ["#F44336", "#F44336"],
            hover_color=["#45a049", "#45a049"] if is_paid else ["#d32f2f", "#d32f2f"],
            width=85,
            height=24
        )
        status_button.grid(row=0, column=6, padx=5, pady=2, sticky="ew")
        
        # Ações (Detalhes, PDF, Remover) - COMPACTOS E UNIFORMES
        actions_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
        actions_frame.grid(row=0, column=7, padx=5, pady=2, sticky="ew")
        actions_frame.grid_columnconfigure(0, weight=1)
        actions_frame.grid_columnconfigure(1, weight=1)
        actions_frame.grid_columnconfigure(2, weight=1)
        
        # Botão Detalhes - COMPACTO E UNIFORME
        details_button = ctk.CTkButton(
            actions_frame,
            text="Detalhes",
            command=lambda: self.show_repair_details(repair),
            font=ctk.CTkFont(family="Arial", size=11),
            fg_color=["#2196F3", "#2196F3"],
            hover_color=["#1976D2", "#1976D2"],
            width=85,
            height=24
        )
        details_button.grid(row=0, column=0, padx=2, pady=2, sticky="ew")
        
        # Botão PDF (Gerar Fatura)
        def generate_pdf():
            # Formatar nome do ficheiro
            client_name = repair.get("client", "Cliente").replace(" ", "_")
            date_str = repair.get("date", "")
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                date_formatted = dt.strftime("%Y%m%d")
            except:
                date_formatted = datetime.now().strftime("%Y%m%d")
            
            default_filename = f"Fatura_{client_name}_{date_formatted}.pdf"
            
            # Solicitar localização para salvar
            filename = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
                initialfile=default_filename,
                title="Guardar Fatura como PDF"
            )
            
            if not filename:
                return  # Utilizador cancelou
            
            # Verificar se ficheiro está bloqueado
            if os.path.exists(filename):
                try:
                    test_file = open(filename, 'a')
                    test_file.close()
                except (IOError, PermissionError, OSError):
                    messagebox.showerror(
                        "Erro",
                        "O ficheiro está aberto ou não tem permissões de escrita.\n\n"
                        "Por favor, feche o ficheiro PDF se estiver aberto e tente novamente."
                    )
                    return
            
            # Gerar PDF em background (incluir taxas no repair dict)
            def db_operation():
                """
                Função pesada executada em background:
                - Lê taxas/config da BD
                - Enriquece o dict da reparação
                - Gera o PDF com reportlab
                """
                try:
                    # Obter taxas da base de dados
                    electricity_rate = float(self.app.db_manager.get_setting("electricity_rate", "0.50"))
                    repair_with_rate = repair.copy()
                    repair_with_rate["electricity_rate"] = electricity_rate
                    # labor_type, hours_worked (qty), electricity_hours, package_weight, transport_cost já vêm do repair dict
                    
                    # Buscar dados completos do cliente se client_id estiver disponível
                    client_id = repair.get("client_id")
                    if client_id:
                        client_data = self.app.db_manager.get_client_by_id(client_id)
                        if client_data:
                            repair_with_rate["client_nif"] = client_data.get("nif", "")
                            repair_with_rate["client_address"] = client_data.get("address", "")
                            repair_with_rate["client_phone"] = client_data.get("phone", "")
                    
                    # Passar db_manager para buscar preços de componentes
                    success = generate_repair_pdf(repair_with_rate, filename, db_manager=self.app.db_manager)
                    return {"success": success, "error": None}
                except ImportError as e:
                    return {"success": False, "error": ("import_error", str(e))}
                except Exception as e:
                    return {"success": False, "error": ("general", str(e))}
            
            def callback(result, error):
                """Callback no main thread após geração do PDF."""
                if error:
                    messagebox.showerror("Erro", f"Erro ao gerar PDF:\n\n{str(error)}")
                    return
                
                if not isinstance(result, dict):
                    messagebox.showerror("Erro", "Erro inesperado ao gerar PDF.")
                    return
                
                success = result.get("success", False)
                err_info = result.get("error")
                
                if not success:
                    if err_info:
                        kind, msg = err_info
                        if kind == "import_error":
                            messagebox.showerror(
                                "Erro",
                                "Biblioteca 'reportlab' não encontrada!\n\n"
                                "Por favor, instale usando:\npip install reportlab\n\n"
                                f"Detalhes: {msg}"
                            )
                        else:
                            messagebox.showerror("Erro", f"Erro ao gerar PDF:\n\n{msg}")
                    else:
                        messagebox.showerror("Erro", "Erro ao gerar PDF. Verifique os dados da reparação.")
                    return
                
                # Sucesso
                messagebox.showinfo(
                    "Operação Concluída",
                    f"Fatura gerada com sucesso.\n\n"
                    f"Ficheiro: {os.path.basename(filename)}"
                )
                
                # Tentar abrir automaticamente
                try:
                    if os.name == 'nt':  # Windows
                        os.startfile(filename)
                    elif os.name == 'posix':  # macOS e Linux
                        os.system(f'open "{filename}"')
                except Exception:
                    # Ignorar se não conseguir abrir
                    pass
            
            # Executar geração com overlay/progress em background
            run_db_operation_with_loading(
                self.app.root,
                self,           # parent widget para overlay
                db_operation,
                callback,
                loading_message="A gerar PDF...",
                min_delay=0.6
            )
        
        pdf_button = ctk.CTkButton(
            actions_frame,
            text="PDF",
            command=generate_pdf,
            font=ctk.CTkFont(family="Arial", size=11),
            fg_color=["#2196F3", "#2196F3"],
            hover_color=["#1976D2", "#1976D2"],
            width=85,
            height=24
        )
        pdf_button.grid(row=0, column=1, padx=2, pady=2, sticky="ew")
        
        # Botão Remover (com confirmação segura)
        def safe_delete():
            confirm_message = (
                f"Tem a certeza que pretende eliminar este registo?\n\n"
                f"Cliente: {repair['client']}\n"
                f"Total: {repair['total']:.2f} €\n\n"
                f"Os componentes utilizados serão restaurados ao stock.\n"
                f"Esta ação é irreversível."
            )
            
            if messagebox.askyesno("Confirmar Eliminação", confirm_message):
                def db_operation():
                    return self.app.db_manager.delete_repair(repair["id"])
                
                def callback(result, error):
                    if error:
                        messagebox.showerror("Erro", f"Erro ao remover registo: {str(error)}")
                    elif result:
                        messagebox.showinfo("Operação Concluída", "Registo removido com sucesso.")
                        self.refresh_data(force=True)
                    else:
                        messagebox.showerror("Erro", "Erro ao remover registo!")
                
                run_db_operation(self.app.root, db_operation, callback)
        
        delete_button = ctk.CTkButton(
            actions_frame,
            text="Apagar",
            command=safe_delete,
            font=ctk.CTkFont(family="Arial", size=11),
            fg_color=["#F44336", "#F44336"],
            hover_color=["#d32f2f", "#d32f2f"],
            width=85,
            height=24
        )
        delete_button.grid(row=0, column=2, padx=2, pady=2, sticky="ew")
    