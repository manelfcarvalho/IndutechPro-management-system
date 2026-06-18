"""
Página de Gestão de Stock
Permite adicionar, visualizar, pesquisar e editar componentes
"""

import customtkinter as ctk
from tkinter import messagebox, filedialog
import pandas as pd
import os
import shutil
import subprocess
import platform
from typing import Optional
from PIL import Image, ImageTk
from ui.utils import run_db_operation, run_db_operation_with_loading, get_base_path


class StockPage(ctk.CTkFrame):
    """Página de gestão de stock"""
    
    def __init__(self, parent, app):
        """
        Inicializa a página de stock
        
        Args:
            parent: Widget pai
            app: Instância da aplicação principal
        """
        super().__init__(parent, fg_color=["#f0f0f0", "#1a1a1a"])
        self.app = app
        self.current_data_hash = None  # Para evitar refreshes desnecessários
        self.is_loading = False

        # Estado de paginação
        self.current_page = 0
        # Menos itens por página para reduzir lag de scroll/renderização
        self.items_per_page = 25
        self.total_pages = 1
        self.total_items = 0
        self.is_search_mode = False
        self.setup_ui()
        self.refresh_data()
    
    def _get_margin_multiplier(self) -> float:
        """
        Retorna o multiplicador de margem baseado na configuração do utilizador.
        Ex: Se margem = 30%, retorna 1.30
        
        Returns:
            Multiplicador (1 + margem/100)
        """
        try:
            margin_str = self.app.db_manager.get_setting("default_margin", "30")
            margin = float(margin_str)
            return 1 + (margin / 100)
        except (ValueError, TypeError):
            # Fallback para 30% se houver erro
            return 1.30
    
    def setup_ui(self):
        """Configura a interface da página de stock"""
        # Título
        title_frame = ctk.CTkFrame(self, fg_color="transparent")
        title_frame.pack(fill="x", padx=20, pady=(20, 10))
        
        title_label = ctk.CTkLabel(
            title_frame,
            text="Gestão de Stock",
            font=ctk.CTkFont(size=32, weight="bold"),
            text_color=["#FF5722", "#FF5722"]
        )
        title_label.pack(side="left")
        
        # Botões (voltar, configurações, import/export)
        buttons_frame = ctk.CTkFrame(title_frame, fg_color="transparent")
        buttons_frame.pack(side="right")
        
        # Botão importar Excel (usa Master Excel, folha \"Stock\")
        import_button = ctk.CTkButton(
            buttons_frame,
            text="Importar Excel",
            command=self.import_from_excel,
            font=ctk.CTkFont(size=12),
            fg_color=["#2196F3", "#2196F3"],
            hover_color=["#1976D2", "#1976D2"],
            width=130,
            height=30
        )
        import_button.pack(side="left", padx=(0, 5))
        
        # Botão configurações de margem
        settings_button = ctk.CTkButton(
            buttons_frame,
            text="Configurar Margem",
            command=self.open_margin_settings,
            font=ctk.CTkFont(size=12),
            fg_color=["#666666", "#444444"],
            hover_color=["#555555", "#333333"],
            width=150,
            height=30
        )
        settings_button.pack(side="left", padx=(0, 10))
        
        # Botão voltar
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
        
        # Container principal (lista e pesquisa)
        main_container = ctk.CTkFrame(self, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=20, pady=10)
        
        # Botão para adicionar novo componente
        add_button_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        add_button_frame.pack(fill="x", pady=(0, 10))
        
        def safe_command(func):
            """Wrapper que garante que comandos não bloqueiam o event loop"""
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    messagebox.showerror("Erro", f"Erro inesperado: {str(e)}")
            return wrapper
        
        add_component_button = ctk.CTkButton(
            add_button_frame,
            text="Novo Componente",
            command=safe_command(lambda: self.open_component_dialog()),
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=["#2196F3", "#2196F3"],
            hover_color=["#1976D2", "#1976D2"],
            height=40,
            width=200
        )
        add_component_button.pack(side="left", padx=(0, 10))
        
        # Botão para entrada rápida de stock
        fast_restock_button = ctk.CTkButton(
            add_button_frame,
            text="Entrada de Stock",
            command=safe_command(lambda: self.open_fast_restock_dialog()),
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=["#4CAF50", "#4CAF50"],
            hover_color=["#45a049", "#45a049"],
            height=40,
            width=200
        )
        fast_restock_button.pack(side="left")
        
        # Lista e pesquisa
        list_frame = ctk.CTkFrame(main_container)
        list_frame.pack(fill="both", expand=True)
        
        # Barra de pesquisa
        search_frame = ctk.CTkFrame(list_frame, fg_color="transparent")
        search_frame.pack(fill="x", padx=20, pady=(20, 10))
        
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

        # Debounce manual para pesquisa (SEARCH_DELAY = 300ms)
        self.SEARCH_DELAY = 300
        self._search_after_id = None

        def on_search_key_release(event=None):
            """Dispara pesquisa com debounce para evitar queries excessivas."""
            try:
                if self._search_after_id is not None:
                    self.after_cancel(self._search_after_id)
                self._search_after_id = self.after(self.SEARCH_DELAY, lambda: self.refresh_data(force=True))
            except Exception:
                # Não deixar erros de debounce quebrar o event loop
                pass

        self.search_entry.bind("<KeyRelease>", on_search_key_release)
        
        # Scrollable frame para a lista
        scrollable_frame = ctk.CTkScrollableFrame(list_frame)
        scrollable_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        
        self.list_container = scrollable_frame
        
        # Controlo de paginação (desativado no novo workflow de pesquisa)
        # Mantido apenas por compatibilidade futura, mas escondido.
        pagination_frame = ctk.CTkFrame(list_frame, fg_color="transparent")
        self.pagination_frame = pagination_frame

        self.prev_page_button = ctk.CTkButton(
            pagination_frame,
            text="<",
            width=40,
            command=self.prev_page,
            font=ctk.CTkFont(size=14)
        )

        self.page_label = ctk.CTkLabel(
            pagination_frame,
            text="Página 1 de 1",
            font=ctk.CTkFont(size=14)
        )

        self.next_page_button = ctk.CTkButton(
            pagination_frame,
            text=">",
            width=40,
            command=self.next_page,
            font=ctk.CTkFont(size=14)
        )

        # Não mostrar paginação no novo fluxo (apenas top-N resultados)
        # pagination_frame.pack(...) é intencionalmente omitido
        
        # Indicador de carregamento
        self.loading_label = ctk.CTkLabel(
            list_frame,
            text="A carregar...",
            font=ctk.CTkFont(size=14),
            text_color=["#666666", "#999999"]
        )

        # Focar automaticamente a barra de pesquisa no arranque
        self.after(100, self.search_entry.focus_set)

    def update_pagination_controls(self):
        """
        Atualiza o estado dos botões de paginação e o label da página.
        """
        # Se estamos em modo pesquisa, desativar paginação (uma única "página")
        if self.is_search_mode:
            self.page_label.configure(text="Resultados da pesquisa")
            self.prev_page_button.configure(state="disabled")
            self.next_page_button.configure(state="disabled")
            return

        total_pages = max(1, self.total_pages)
        current = self.current_page + 1  # 1-based para o utilizador
        if current > total_pages:
            current = total_pages

        self.page_label.configure(text=f"Página {current} de {total_pages}")

        # Ativar/desativar botões
        if self.current_page <= 0:
            self.prev_page_button.configure(state="disabled")
        else:
            self.prev_page_button.configure(state="normal")

        if self.current_page >= total_pages - 1:
            self.next_page_button.configure(state="disabled")
        else:
            self.next_page_button.configure(state="normal")

    def next_page(self):
        """Vai para a próxima página de componentes."""
        if self.is_search_mode:
            return  # Paginação não usada em modo pesquisa
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.refresh_data(force=True)

    def prev_page(self):
        """Vai para a página anterior de componentes."""
        if self.is_search_mode:
            return  # Paginação não usada em modo pesquisa
        if self.current_page > 0:
            self.current_page -= 1
            self.refresh_data(force=True)
    
    def open_component_dialog(self, component_id: Optional[int] = None):
        """
        Abre diálogo para adicionar/editar componente com layout de 2 colunas
        
        Args:
            component_id: ID do componente para edição (None para novo)
        """
        # Criar janela de diálogo
        dialog = ctk.CTkToplevel(self)
        dialog.title("Adicionar Componente" if component_id is None else "Editar Componente")
        dialog.geometry("800x600")
        dialog.minsize(700, 500)
        dialog.resizable(True, True)
        dialog.transient(self)
        
        # Centralizar
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (800 // 2)
        y = (dialog.winfo_screenheight() // 2) - (600 // 2)
        dialog.geometry(f"800x600+{x}+{y}")
        
        # Variáveis para armazenar dados
        current_image_path = None
        current_datasheet_path = None
        preview_image = None
        
        # Helper: Criar pastas necessárias
        def ensure_folders():
            """Garante que as pastas assets/components e assets/datasheets existem"""
            base_path = get_base_path()
            components_dir = os.path.join(base_path, "assets", "components")
            datasheets_dir = os.path.join(base_path, "assets", "datasheets")
            os.makedirs(components_dir, exist_ok=True)
            os.makedirs(datasheets_dir, exist_ok=True)
        
        ensure_folders()
        
        # Helper: Abrir PDF de forma cross-platform
        def open_pdf_file(file_path):
            """Abre um arquivo PDF usando o visualizador padrão do sistema"""
            try:
                if platform.system() == 'Windows':
                    os.startfile(file_path)
                elif platform.system() == 'Darwin':  # macOS
                    subprocess.call(['open', file_path])
                else:  # Linux
                    subprocess.call(['xdg-open', file_path])
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao abrir PDF: {str(e)}")
        
        # ========== SCROLLABLE CONTENT (TOP) ==========
        scrollable_content = ctk.CTkScrollableFrame(dialog)
        scrollable_content.pack(fill="both", expand=True, padx=10, pady=10)
        scrollable_content.grid_columnconfigure(0, weight=1, uniform="scroll_cols")
        scrollable_content.grid_columnconfigure(1, weight=1, uniform="scroll_cols")
        
        # ========== COLUNA ESQUERDA: INPUTS ==========
        left_frame = ctk.CTkFrame(scrollable_content)
        left_frame.grid(row=0, column=0, padx=(0, 10), pady=0, sticky="nsew")
        left_frame.grid_columnconfigure(0, weight=1)
        
        # Título
        title_label = ctk.CTkLabel(
            left_frame,
            text="Informações do Componente",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.pack(pady=(15, 20))
        
        # Função helper para criar campos
        def create_field(parent, label_text, row):
            frame = ctk.CTkFrame(parent, fg_color="transparent")
            frame.pack(fill="x", padx=15, pady=8)
            
            label = ctk.CTkLabel(
                frame,
                text=label_text,
                font=ctk.CTkFont(size=12),
                anchor="w"
            )
            label.pack(fill="x", pady=(0, 5))
            
            entry = ctk.CTkEntry(
                frame,
                font=ctk.CTkFont(size=13),
                height=32
            )
            entry.pack(fill="x")
            return entry
        
        # Campos do formulário
        code_entry = create_field(left_frame, "Código:", 0)
        name_entry = create_field(left_frame, "Nome:", 1)
        family_entry = create_field(left_frame, "Família:", 2)
        supplier_entry = create_field(left_frame, "Fornecedor:", 3)  # New supplier field
        supplier_ref_entry = create_field(left_frame, "Ref. Fornecedor:", 4)  # New supplier ref field
        cost_entry = create_field(left_frame, "Preço de Compra (€):", 5)
        margin_entry = create_field(left_frame, "Margem (%):", 6)
        price_entry = create_field(left_frame, "Preço de Venda (€):", 7)
        price_entry.configure(state="disabled")  # sempre desativado para evitar edição manual
        qty_entry = create_field(left_frame, "Quantidade:", 8)
        
        # Datasheet PDF
        datasheet_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        datasheet_frame.pack(fill="x", padx=15, pady=8)
        
        datasheet_label = ctk.CTkLabel(
            datasheet_frame,
            text="Datasheet PDF:",
            font=ctk.CTkFont(size=12),
            anchor="w"
        )
        datasheet_label.pack(fill="x", pady=(0, 5))
        
        # Label para mostrar o nome do arquivo
        datasheet_filename_label = ctk.CTkLabel(
            datasheet_frame,
            text="Nenhum",
            font=ctk.CTkFont(size=11),
            anchor="w",
            text_color=["#666666", "#999999"]
        )
        datasheet_filename_label.pack(fill="x", pady=(0, 8))
        
        # Frame para botões
        datasheet_buttons_frame = ctk.CTkFrame(datasheet_frame, fg_color="transparent")
        datasheet_buttons_frame.pack(fill="x")
        datasheet_buttons_frame.grid_columnconfigure(0, weight=1)
        datasheet_buttons_frame.grid_columnconfigure(1, weight=1)
        
        def load_datasheet_pdf():
            """Carrega um arquivo PDF para o datasheet"""
            nonlocal current_datasheet_path
            
            file_path = filedialog.askopenfilename(
                title="Selecionar PDF do Datasheet",
                filetypes=[("PDF Files", "*.pdf"), ("Todos", "*.*")]
            )
            
            if not file_path:
                return
            
            try:
                # Criar pasta assets/datasheets/ se não existir
                base_path = get_base_path()
                datasheets_dir = os.path.join(base_path, "assets", "datasheets")
                os.makedirs(datasheets_dir, exist_ok=True)
                
                # Gerar nome único baseado no código (ou timestamp)
                code = code_entry.get().strip()
                if code:
                    filename = f"{code}_{os.path.basename(file_path)}"
                else:
                    filename = f"datasheet_{int(os.path.getmtime(file_path))}_{os.path.basename(file_path)}"
                
                # Caminho de destino
                dest_path = os.path.join(datasheets_dir, filename)
                
                # Copiar arquivo
                shutil.copy2(file_path, dest_path)
                
                # Salvar caminho relativo (para compatibilidade com BD)
                current_datasheet_path = os.path.join("assets", "datasheets", filename)
                
                # Atualizar label
                datasheet_filename_label.configure(
                    text=os.path.basename(filename),
                    text_color=["#333333", "#cccccc"]
                )
                
                # Mostrar botão "Ver PDF"
                view_pdf_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")
                
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao carregar PDF: {str(e)}")
        
        def view_datasheet_pdf():
            """Abre o PDF do datasheet"""
            if current_datasheet_path:
                # Se for caminho absoluto, usar diretamente; caso contrário, usar get_base_path()
                if os.path.isabs(current_datasheet_path):
                    full_path = current_datasheet_path
                else:
                    base_path = get_base_path()
                    full_path = os.path.join(base_path, current_datasheet_path)
                
                if os.path.exists(full_path):
                    open_pdf_file(full_path)
                else:
                    messagebox.showerror("Erro", "Arquivo PDF não encontrado!")
            else:
                messagebox.showwarning("Atenção", "Nenhum PDF carregado.")
        
        load_pdf_button = ctk.CTkButton(
            datasheet_buttons_frame,
            text="Carregar PDF",
            command=load_datasheet_pdf,
            font=ctk.CTkFont(size=12),
            height=32
        )
        load_pdf_button.grid(row=0, column=0, sticky="ew")
        
        view_pdf_button = ctk.CTkButton(
            datasheet_buttons_frame,
            text="Ver Datasheet",
            command=view_datasheet_pdf,
            font=ctk.CTkFont(size=12),
            height=32,
            fg_color=["#2196F3", "#2196F3"],
            hover_color=["#1976D2", "#1976D2"]
        )
        # Inicialmente oculto (será mostrado quando houver PDF)
        view_pdf_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        view_pdf_button.grid_remove()
        
        # Carregar margem padrão
        try:
            default_margin = self.app.db_manager.get_setting("default_margin", "30")
            margin_entry.insert(0, default_margin)
        except:
            margin_entry.insert(0, "30")
        
        # Função para calcular preço de venda usando margem configurada
        def calculate_price(*args):
            try:
                cost_str = cost_entry.get().strip().replace(",", ".")
                if cost_str:
                    cost_val = float(cost_str)
                    multiplier = self._get_margin_multiplier()
                    selling_price = cost_val * multiplier
                    price_entry.configure(state="normal")
                    price_entry.delete(0, "end")
                    price_entry.insert(0, f"{selling_price:.2f}")
                    price_entry.configure(state="disabled")
                else:
                    price_entry.configure(state="normal")
                    price_entry.delete(0, "end")
                    price_entry.configure(state="disabled")
            except:
                price_entry.configure(state="normal")
                price_entry.delete(0, "end")
                price_entry.configure(state="disabled")
        
        cost_entry.bind("<KeyRelease>", calculate_price)
        calculate_price()  # Calcular inicial
        
        # ========== COLUNA DIREITA: MEDIA ==========
        right_frame = ctk.CTkFrame(scrollable_content)
        right_frame.grid(row=0, column=1, padx=(10, 0), pady=0, sticky="nsew")
        right_frame.grid_columnconfigure(0, weight=1)
        
        # Título
        media_title = ctk.CTkLabel(
            right_frame,
            text="Foto do Produto",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        media_title.pack(pady=(15, 20))
        
        # Preview da imagem (max 300x300, mantendo aspect ratio)
        image_preview_label = ctk.CTkLabel(
            right_frame,
            text="Sem imagem",
            font=ctk.CTkFont(size=12),
            width=300,
            height=300,
            fg_color=["#e0e0e0", "#2b2b2b"],
            corner_radius=8
        )
        image_preview_label.pack(pady=(0, 15))
        
        # Botão para carregar foto
        def load_image():
            nonlocal current_image_path, preview_image
            
            file_path = filedialog.askopenfilename(
                title="Selecionar Imagem",
                filetypes=[("Imagens", "*.jpg *.jpeg *.png *.gif *.bmp"), ("Todos", "*.*")]
            )
            
            if not file_path:
                return
            
            try:
                # Criar pasta assets/components/ se não existir
                base_path = get_base_path()
                components_dir = os.path.join(base_path, "assets", "components")
                os.makedirs(components_dir, exist_ok=True)
                
                # Gerar nome único baseado no código (ou timestamp)
                code = code_entry.get().strip()
                if code:
                    filename = f"{code}_{os.path.basename(file_path)}"
                else:
                    filename = f"img_{int(os.path.getmtime(file_path))}_{os.path.basename(file_path)}"
                
                # Caminho de destino
                dest_path = os.path.join(components_dir, filename)
                
                # Copiar arquivo
                shutil.copy2(file_path, dest_path)
                
                # Salvar caminho relativo (para compatibilidade com BD)
                current_image_path = os.path.join("assets", "components", filename)
                
                # Carregar e exibir preview (max 300x300, mantendo aspect ratio)
                img = Image.open(dest_path)
                img.thumbnail((300, 300), Image.Resampling.LANCZOS)
                # Calcular tamanho real mantendo aspect ratio
                img_width, img_height = img.size
                preview_image = ctk.CTkImage(light_image=img, dark_image=img, size=(img_width, img_height))
                image_preview_label.configure(image=preview_image, text="")
                
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao carregar imagem: {str(e)}")
        
        load_image_button = ctk.CTkButton(
            right_frame,
            text="Carregar Foto",
            command=load_image,
            font=ctk.CTkFont(size=13),
            height=35,
            width=180
        )
        load_image_button.pack()
        
        # ========== BOTÕES DE AÇÃO (FIXED BOTTOM) ==========
        action_frame = ctk.CTkFrame(dialog, height=70)
        action_frame.pack(fill="x", side="bottom", padx=10, pady=10)
        action_frame.pack_propagate(False)
        action_frame.grid_columnconfigure(0, weight=1)
        action_frame.grid_columnconfigure(1, weight=1)
        
        def save_component():
            try:
                code = code_entry.get().strip()
                name = name_entry.get().strip()
                family = family_entry.get().strip() or None
                supplier = supplier_entry.get().strip() or None  # Get supplier value
                supplier_ref = supplier_ref_entry.get().strip() or None  # Get supplier ref value
                cost_str = cost_entry.get().strip().replace(",", ".")
                qty_str = qty_entry.get().strip()
                
                if not code or not name:
                    messagebox.showwarning("Atenção", "Código e Nome são obrigatórios.")
                    return

                # Recalcular preço de venda usando margem configurada
                try:
                    preco_compra = float(cost_str) if cost_str else 0.0
                except ValueError:
                    preco_compra = 0.0
                multiplier = self._get_margin_multiplier()
                price = preco_compra * multiplier
                qty = int(qty_str) if qty_str else 0
                
                if price < 0 or qty < 0:
                    messagebox.showwarning("Atenção", "Preço e Quantidade devem ser positivos.")
                    return
                
                def db_operation():
                    if component_id is None:
                        # Adicionar novo
                        return self.app.db_manager.add_component(
                            code,
                            name,
                            price,
                            qty,
                            current_image_path,
                            current_datasheet_path,
                            family,
                            supplier,
                            supplier_ref,
                            preco_compra,
                        )
                    else:
                        # Atualizar existente
                        return self.app.db_manager.update_component(
                            component_id,
                            code,
                            name,
                            price,
                            qty,
                            current_image_path,
                            current_datasheet_path,
                            family,
                            supplier,
                            supplier_ref,
                            preco_compra,
                        )
                
                def callback(result, error):
                    if error:
                        messagebox.showerror("Erro", f"Erro ao guardar componente: {str(error)}")
                    elif result:
                        messagebox.showinfo("Operação Concluída", "Componente guardado com sucesso.")
                        dialog.destroy()
                        # Force immediate refresh of the Treeview after dialog closes
                        self.after(100, lambda: self.refresh_data(force=True))
                    else:
                        messagebox.showerror("Erro", "Código já existe na base de dados!" if component_id is None else "Erro ao atualizar componente!")
                
                run_db_operation(self.app.root, db_operation, callback)
                
            except ValueError:
                messagebox.showerror("Erro", "Por favor, insira valores numéricos válidos!")
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao guardar componente: {str(e)}")
        
        save_button = ctk.CTkButton(
            action_frame,
            text="Guardar",
            command=save_component,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=["#2196F3", "#2196F3"],
            hover_color=["#1976D2", "#1976D2"],
            height=40
        )
        save_button.grid(row=0, column=0, padx=(0, 10), pady=10, sticky="ew")
        
        cancel_button = ctk.CTkButton(
            action_frame,
            text="Cancelar",
            command=dialog.destroy,
            font=ctk.CTkFont(size=14),
            fg_color="transparent",
            hover_color=["#555555", "#333333"],
            height=40
        )
        cancel_button.grid(row=0, column=1, pady=10, sticky="ew")
        
        # Se for edição, carregar dados do componente
        if component_id is not None:
            def load_component_data():
                def db_operation():
                    return self.app.db_manager.get_component_by_id(component_id)
                
                def callback(component, error):
                    if error:
                        messagebox.showerror("Erro", f"Erro ao carregar componente: {str(error)}")
                        dialog.destroy()
                    elif component:
                        # Preencher campos
                        code_entry.insert(0, component.get("code", ""))
                        name_entry.insert(0, component.get("name", ""))
                        family_entry.insert(0, component.get("family", "") or "")
                        supplier_entry.insert(0, component.get("supplier", "") or "")  # Fill supplier field
                        supplier_ref_entry.insert(0, component.get("supplier_ref", "") or "")  # Fill supplier ref field
                        
                        # Preço de venda e preço de compra (preco_compra)
                        selling_price = component.get("price", 0)
                        preco_compra = component.get("preco_compra", None)

                        # Preencher preço de venda
                        price_entry.configure(state="normal")
                        price_entry.insert(0, f"{selling_price:.2f}")
                        price_entry.configure(state="readonly")

                        # Preencher preço de compra, se existir na BD; caso contrário, tentar calcular
                        if preco_compra is not None:
                            try:
                                cost_entry.insert(0, f"{float(preco_compra):.2f}")
                            except Exception:
                                pass
                        else:
                            # Fallback: calcular custo aproximado a partir da margem
                            try:
                                margin = float(margin_entry.get().strip().replace(",", "."))
                                if margin > 0:
                                    cost = selling_price / (1 + margin / 100)
                                    cost_entry.insert(0, f"{cost:.2f}")
                            except Exception:
                                pass
                        
                        qty_entry.insert(0, str(component.get("qty", 0)))
                        
                        # Carregar imagem se existir
                        img_path = component.get("image_path")
                        if img_path:
                            nonlocal current_image_path, preview_image
                            current_image_path = img_path
                            # Se for caminho absoluto, usar diretamente; caso contrário, usar get_base_path()
                            if os.path.isabs(img_path):
                                full_path = img_path
                            else:
                                base_path = get_base_path()
                                full_path = os.path.join(base_path, img_path)
                            
                            if os.path.exists(full_path):
                                try:
                                    img = Image.open(full_path)
                                    img.thumbnail((300, 300), Image.Resampling.LANCZOS)
                                    img_width, img_height = img.size
                                    preview_image = ctk.CTkImage(light_image=img, dark_image=img, size=(img_width, img_height))
                                    image_preview_label.configure(image=preview_image, text="")
                                except Exception as e:
                                    pass  # Silenciosamente falhar se imagem não puder ser carregada
                        
                        # Carregar datasheet PDF
                        datasheet = component.get("datasheet_path")
                        if datasheet:
                            nonlocal current_datasheet_path
                            current_datasheet_path = datasheet
                            # Atualizar label com nome do arquivo
                            filename = os.path.basename(datasheet)
                            datasheet_filename_label.configure(
                                text=filename,
                                text_color=["#333333", "#cccccc"]
                            )
                            # Mostrar botão "Ver PDF"
                            view_pdf_button.grid()
                
                run_db_operation(self.app.root, db_operation, callback)
            
            # Carregar dados após um pequeno delay para garantir que a UI está pronta
            dialog.after(100, load_component_data)
    
    def open_margin_settings(self):
        """Abre diálogo para configurar margem padrão"""
        # Criar janela de diálogo
        dialog = ctk.CTkToplevel(self)
        dialog.title("Configurar Margem Padrão")
        dialog.geometry("400x200")
        dialog.transient(self)  # Tornar modal
        dialog.grab_set()  # Capturar eventos
        
        # Centralizar
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (400 // 2)
        y = (dialog.winfo_screenheight() // 2) - (200 // 2)
        dialog.geometry(f"400x200+{x}+{y}")
        
        # Container principal
        main_frame = ctk.CTkFrame(dialog)
        main_frame.pack(fill="both", expand=True, padx=30, pady=30)
        
        # Título
        title_label = ctk.CTkLabel(
            main_frame,
            text="Margem de Lucro Padrão",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(0, 10))
        
        # Descrição
        desc_label = ctk.CTkLabel(
            main_frame,
            text="Qual a margem de lucro padrão (%)?",
            font=ctk.CTkFont(size=14)
        )
        desc_label.pack(pady=(0, 15))
        
        # Campo de entrada
        entry_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        entry_frame.pack(fill="x", pady=(0, 20))
        
        margin_entry = ctk.CTkEntry(
            entry_frame,
            font=ctk.CTkFont(size=16),
            height=40,
            width=200
        )
        margin_entry.pack()
        
        # Carregar valor atual
        try:
            current_margin = self.app.db_manager.get_setting("default_margin", "30")
            margin_entry.insert(0, current_margin)
        except:
            margin_entry.insert(0, "30")
        
        # Botões
        buttons_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        buttons_frame.pack(fill="x")
        
        def save_margin():
            try:
                margin_value = margin_entry.get().strip().replace(",", ".")
                margin_float = float(margin_value)
                
                if margin_float < 0:
                    messagebox.showwarning("Atenção", "A margem deve ser positiva.")
                    return
                
                # Guardar na base de dados
                success = self.app.db_manager.set_setting("default_margin", margin_value)
                
                if success:
                    # Atualizar todos os preços de venda em massa com a nova margem
                    def db_operation():
                        return self.app.db_manager.update_all_sale_prices(margin_float)
                    
                    def callback(result, error):
                        if error:
                            messagebox.showerror("Erro", f"Erro ao atualizar preços: {str(error)}")
                        elif result:
                            # Atualizar a tabela na UI para mostrar os novos preços
                            self.refresh_data(force=True)
                            messagebox.showinfo(
                                "Operação Concluída",
                                f"Margem padrão definida para {margin_value}%.\n\nPreços de todo o stock atualizados com a nova margem!"
                            )
                            dialog.destroy()
                        else:
                            messagebox.showerror("Erro", "Erro ao atualizar preços de venda!")
                    
                    run_db_operation(self.app.root, db_operation, callback)
                else:
                    messagebox.showerror("Erro", "Erro ao guardar configuração!")
            except ValueError:
                messagebox.showerror("Erro", "Por favor, insira um valor numérico válido!")
            except Exception as e:
                messagebox.showerror("Erro", f"Erro: {str(e)}")
        
        save_button = ctk.CTkButton(
            buttons_frame,
            text="Guardar",
            command=save_margin,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=["#4CAF50", "#4CAF50"],
            hover_color=["#45a049", "#45a049"],
            width=120,
            height=35
        )
        save_button.pack(side="left", padx=(0, 10), expand=True)
        
        cancel_button = ctk.CTkButton(
            buttons_frame,
            text="Cancelar",
            command=dialog.destroy,
            font=ctk.CTkFont(size=14),
            fg_color="transparent",
            hover_color=["#555555", "#333333"],
            width=120,
            height=35
        )
        cancel_button.pack(side="left", expand=True)
        
        # Focar no campo de entrada
        margin_entry.focus_set()
        
        # Permitir Enter para guardar
        margin_entry.bind("<Return>", lambda e: save_margin())
    
    def edit_component(self, component_id: int):
        """Abre janela de detalhes para visualizar/editar um componente"""
        self.open_component_details(component_id)
    
    def open_component_details(self, component_id: int):
        """
        Abre janela de detalhes do componente com modo View/Edit
        Layout vertical: Foto grande no topo, campos abaixo
        
        Args:
            component_id: ID do componente
        """
        # Criar janela de detalhes
        details_window = ctk.CTkToplevel(self)
        details_window.title("Detalhes do Componente")
        details_window.geometry("700x800")
        details_window.minsize(600, 700)
        details_window.resizable(True, True)
        details_window.transient(self)
        
        # Centralizar
        details_window.update_idletasks()
        x = (details_window.winfo_screenwidth() // 2) - (700 // 2)
        y = (details_window.winfo_screenheight() // 2) - (800 // 2)
        details_window.geometry(f"700x800+{x}+{y}")
        
        # Variáveis para armazenar dados
        current_image_path = None
        current_datasheet_path = None
        preview_image = None
        is_edit_mode = False
        
        # Helper: Criar pastas necessárias
        def ensure_folders():
            base_path = get_base_path()
            components_dir = os.path.join(base_path, "assets", "components")
            datasheets_dir = os.path.join(base_path, "assets", "datasheets")
            os.makedirs(components_dir, exist_ok=True)
            os.makedirs(datasheets_dir, exist_ok=True)
        
        ensure_folders()
        
        # Helper: Abrir PDF de forma cross-platform
        def open_pdf_file(file_path):
            try:
                if platform.system() == 'Windows':
                    os.startfile(file_path)
                elif platform.system() == 'Darwin':  # macOS
                    subprocess.call(['open', file_path])
                else:  # Linux
                    subprocess.call(['xdg-open', file_path])
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao abrir PDF: {str(e)}")
        
        # ========== SCROLLABLE CONTENT (VERTICAL LAYOUT) ==========
        scrollable_content = ctk.CTkScrollableFrame(details_window)
        scrollable_content.pack(fill="both", expand=True, padx=10, pady=10)
        scrollable_content.grid_columnconfigure(0, weight=1)
        
        # ========== TOP: LARGE PHOTO (HERO) ==========
        # Preview da imagem (Large: max height 250-300px, keeping aspect ratio)
        image_preview_label = ctk.CTkLabel(
            scrollable_content,
            text="Sem imagem",
            font=ctk.CTkFont(size=12),
            width=400,
            height=300,
            fg_color=["#e0e0e0", "#2b2b2b"],
            corner_radius=8
        )
        image_preview_label.pack(pady=(15, 15))
        
        # Botão para carregar/alterar foto (hidden in view mode)
        def load_image():
            nonlocal current_image_path, preview_image
            
            file_path = filedialog.askopenfilename(
                title="Selecionar Imagem",
                filetypes=[("Imagens", "*.jpg *.jpeg *.png *.gif *.bmp"), ("Todos", "*.*")]
            )
            
            if not file_path:
                return
            
            try:
                base_path = get_base_path()
                components_dir = os.path.join(base_path, "assets", "components")
                os.makedirs(components_dir, exist_ok=True)
                
                code = code_entry.get().strip()
                if code:
                    filename = f"{code}_{os.path.basename(file_path)}"
                else:
                    filename = f"img_{int(os.path.getmtime(file_path))}_{os.path.basename(file_path)}"
                
                dest_path = os.path.join(components_dir, filename)
                shutil.copy2(file_path, dest_path)
                current_image_path = os.path.join("assets", "components", filename)
                
                # Load and display preview (max height 300px, keeping aspect ratio)
                img = Image.open(dest_path)
                img.thumbnail((400, 300), Image.Resampling.LANCZOS)
                preview_image = ImageTk.PhotoImage(img)
                image_preview_label.configure(image=preview_image, text="")
                
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao carregar imagem: {str(e)}")
        
        load_image_button = ctk.CTkButton(
            scrollable_content,
            text="Alterar Foto",
            command=load_image,
            font=ctk.CTkFont(size=13),
            height=35,
            width=200
        )
        load_image_button.pack(pady=(0, 20))
        load_image_button.pack_forget()  # Hidden initially (view mode)
        
        # ========== DATASHEET BUTTON (Below Photo) ==========
        def load_datasheet_pdf():
            nonlocal current_datasheet_path
            
            file_path = filedialog.askopenfilename(
                title="Selecionar PDF do Datasheet",
                filetypes=[("PDF Files", "*.pdf"), ("Todos", "*.*")]
            )
            
            if not file_path:
                return
            
            try:
                base_path = get_base_path()
                datasheets_dir = os.path.join(base_path, "assets", "datasheets")
                os.makedirs(datasheets_dir, exist_ok=True)
                
                code = code_entry.get().strip()
                if code:
                    filename = f"{code}_{os.path.basename(file_path)}"
                else:
                    filename = f"datasheet_{int(os.path.getmtime(file_path))}_{os.path.basename(file_path)}"
                
                dest_path = os.path.join(datasheets_dir, filename)
                shutil.copy2(file_path, dest_path)
                current_datasheet_path = os.path.join("assets", "datasheets", filename)
                
                # Show view button
                view_pdf_button.pack(pady=5)
                
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao carregar PDF: {str(e)}")
        
        def view_datasheet_pdf():
            if current_datasheet_path:
                # Se for caminho absoluto, usar diretamente; caso contrário, usar get_base_path()
                if os.path.isabs(current_datasheet_path):
                    full_path = current_datasheet_path
                else:
                    base_path = get_base_path()
                    full_path = os.path.join(base_path, current_datasheet_path)
                
                if os.path.exists(full_path):
                    open_pdf_file(full_path)
                else:
                    messagebox.showerror("Erro", "Arquivo PDF não encontrado!")
            else:
                messagebox.showwarning("Atenção", "Nenhum PDF carregado.")
        
        # Botão para abrir PDF (visible if PDF exists)
        view_pdf_button = ctk.CTkButton(
            scrollable_content,
            text="Ver Datasheet",
            command=view_datasheet_pdf,
            font=ctk.CTkFont(size=12),
            height=32,
            fg_color=["#2196F3", "#2196F3"],
            hover_color=["#1976D2", "#1976D2"],
            width=200
        )
        view_pdf_button.pack(pady=5)
        view_pdf_button.pack_forget()  # Hidden initially
        
        # Botão para carregar/alterar PDF (hidden in view mode)
        load_pdf_button = ctk.CTkButton(
            scrollable_content,
            text="Carregar/Alterar PDF",
            command=load_datasheet_pdf,
            font=ctk.CTkFont(size=12),
            height=32,
            width=200
        )
        load_pdf_button.pack(pady=5)
        load_pdf_button.pack_forget()  # Hidden initially (view mode)
        
        # ========== FORM FIELDS (Below Datasheet) ==========
        # Helper function to create field
        def create_field(parent, label_text):
            frame = ctk.CTkFrame(parent, fg_color="transparent")
            frame.pack(fill="x", padx=15, pady=8)
            
            label = ctk.CTkLabel(
                frame,
                text=label_text,
                font=ctk.CTkFont(size=12),
                anchor="w"
            )
            label.pack(fill="x", pady=(0, 5))
            
            entry = ctk.CTkEntry(
                frame,
                font=ctk.CTkFont(size=13),
                height=32,
                state="normal"  # Start in normal state to allow data insertion
            )
            entry.pack(fill="x")
            return entry
        
        # Create all entry fields in specified order
        code_entry = create_field(scrollable_content, "Código:")
        name_entry = create_field(scrollable_content, "Designação:")
        family_entry = create_field(scrollable_content, "Família:")
        supplier_entry = create_field(scrollable_content, "Fornecedor:")
        supplier_ref_entry = create_field(scrollable_content, "Referência:")
        qty_entry = create_field(scrollable_content, "Quantidade (Un):")
        preco_compra_entry = create_field(scrollable_content, "Preço de Compra (€):")
        price_entry = create_field(scrollable_content, "Preço de Venda (€):")
        price_entry.configure(state="disabled")  # impedir edição manual

        # Função para calcular preço de venda usando margem configurada
        def recalc_price_from_purchase(*args):
            try:
                p_compra_str = preco_compra_entry.get().strip().replace(",", ".")
                p_compra_val = float(p_compra_str) if p_compra_str else 0.0
            except Exception:
                p_compra_val = 0.0
            multiplier = self._get_margin_multiplier()
            p_venda_val = p_compra_val * multiplier
            price_entry.configure(state="normal")
            price_entry.delete(0, "end")
            price_entry.insert(0, f"{p_venda_val:.2f}")
            price_entry.configure(state="disabled")

        preco_compra_entry.bind("<KeyRelease>", recalc_price_from_purchase)
        
        # Store all entries for easy access
        all_entries = {
            "code": code_entry,
            "name": name_entry,
            "family": family_entry,
            "supplier": supplier_entry,
            "supplier_ref": supplier_ref_entry,
            "qty": qty_entry,
            "preco_compra": preco_compra_entry,
            "price": price_entry,
        }
        
        # ========== ACTION BUTTONS (AT BOTTOM) ==========
        action_frame = ctk.CTkFrame(details_window, fg_color="transparent")
        action_frame.pack(fill="x", padx=20, pady=20)
        action_frame.grid_columnconfigure(0, weight=1)
        action_frame.grid_columnconfigure(1, weight=1)
        
        # Edit/Save button
        edit_save_button = ctk.CTkButton(
            action_frame,
            text="Editar",
            command=None,  # Will be set after loading data
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=["#2196F3", "#2196F3"],
            hover_color=["#1976D2", "#1976D2"],
            width=150,
            height=40
        )
        edit_save_button.grid(row=0, column=0, padx=5)
        
        # Cancel/Close button
        cancel_button = ctk.CTkButton(
            action_frame,
            text="Fechar",
            command=details_window.destroy,
            font=ctk.CTkFont(size=14),
            fg_color="transparent",
            hover_color=["#555555", "#333333"],
            width=150,
            height=40
        )
        cancel_button.grid(row=0, column=1, padx=5)
        
        # Function to toggle edit mode
        def toggle_edit_mode():
            nonlocal is_edit_mode
            is_edit_mode = not is_edit_mode
            
            if is_edit_mode:
                # Edit Mode: Enable ALL inputs, show upload buttons
                for entry in all_entries.values():
                    entry.configure(state="normal")
                # Garantir que preço de venda continua bloqueado
                price_entry.configure(state="disabled")
                
                # Show upload buttons
                load_image_button.pack(pady=(0, 20))
                load_pdf_button.pack(pady=5)
                
                # Change button to "Guardar" (Save)
                edit_save_button.configure(
                    text="Guardar",
                    fg_color=["#2196F3", "#2196F3"],
                    hover_color=["#1976D2", "#1976D2"]
                )
                cancel_button.configure(text="Cancelar")
            else:
                # View Mode: Disable ALL inputs, hide upload buttons
                for entry in all_entries.values():
                    entry.configure(state="disabled")
                
                # Hide upload buttons
                load_image_button.pack_forget()
                load_pdf_button.pack_forget()
                
                # Change button back to "Editar"
                edit_save_button.configure(
                    text="Editar",
                    fg_color=["#2196F3", "#2196F3"],
                    hover_color=["#1976D2", "#1976D2"]
                )
                cancel_button.configure(text="Fechar")
        
        # Function to save changes
        def save_changes():
            try:
                code = code_entry.get().strip()
                name = name_entry.get().strip()
                family = family_entry.get().strip() or None
                supplier = supplier_entry.get().strip() or None
                supplier_ref = supplier_ref_entry.get().strip() or None
                qty_str = qty_entry.get().strip()
                preco_compra_str = preco_compra_entry.get().strip().replace(",", ".")
                
                if not code or not name:
                    messagebox.showwarning("Aviso", "Código e Designação são obrigatórios!")
                    return

                # Recalcular sempre o preço de venda usando margem configurada
                try:
                    p_compra = float(preco_compra_str) if preco_compra_str else 0.0
                except ValueError:
                    p_compra = 0.0
                multiplier = self._get_margin_multiplier()
                price = p_compra * multiplier
                preco_compra = float(preco_compra_str) if preco_compra_str else 0.0
                qty = int(qty_str) if qty_str else 0
                
                if price < 0 or qty < 0:
                    messagebox.showwarning("Atenção", "Preço e Quantidade devem ser positivos.")
                    return
                
                def db_operation():
                    return self.app.db_manager.update_component(
                        component_id,
                        code,
                        name,
                        price,
                        qty,
                        current_image_path,
                        current_datasheet_path,
                        family,
                        supplier,
                        supplier_ref,
                        preco_compra,
                    )
                
                def callback(result, error):
                    if error:
                        messagebox.showerror("Erro", f"Erro ao guardar componente: {str(error)}")
                    elif result:
                        messagebox.showinfo("Operação Concluída", "Componente guardado com sucesso.")
                        details_window.destroy()
                        self.after(100, lambda: self.refresh_data(force=True))
                    else:
                        messagebox.showerror("Erro", "Erro ao atualizar componente!")
                
                run_db_operation(self.app.root, db_operation, callback)
                
            except ValueError:
                messagebox.showerror("Erro", "Por favor, insira valores numéricos válidos!")
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao guardar componente: {str(e)}")
        
        # Set button command
        def on_edit_save_click():
            if is_edit_mode:
                save_changes()
            else:
                toggle_edit_mode()
        
        edit_save_button.configure(command=on_edit_save_click)
        
        # Load component data
        def load_component_data():
            def db_operation():
                return self.app.db_manager.get_component_by_id(component_id)
            
            def callback(component, error):
                if error:
                    messagebox.showerror("Erro", f"Erro ao carregar componente: {str(error)}")
                    details_window.destroy()
                elif component:
                    # CRITICAL: Insert data BEFORE disabling fields
                    # All fields start in "normal" state, so we can insert
                    code_entry.insert(0, component.get("code", ""))
                    name_entry.insert(0, component.get("name", ""))
                    family_entry.insert(0, component.get("family", "") or "")
                    supplier_entry.insert(0, component.get("supplier", "") or "")
                    supplier_ref_entry.insert(0, component.get("supplier_ref", "") or "")
                    qty_entry.insert(0, str(component.get("qty", 0)))
                    
                    # Preços: compra e venda
                    selling_price = component.get("price", 0)
                    preco_compra = component.get("preco_compra", None)

                    if preco_compra is not None:
                        try:
                            preco_compra_entry.insert(0, f"{float(preco_compra):.2f}")
                        except Exception:
                            pass
                    # Preencher preço de venda calculado usando margem configurada; fallback para valor da BD
                    price_entry.configure(state="normal")
                    if preco_compra is not None:
                        multiplier = self._get_margin_multiplier()
                        price_entry.delete(0, "end")
                        price_entry.insert(0, f"{(float(preco_compra) * multiplier):.2f}")
                    else:
                        price_entry.delete(0, "end")
                        price_entry.insert(0, f"{selling_price:.2f}")
                    price_entry.configure(state="disabled")
                    
                    # NOW disable all fields (after data insertion)
                    for entry in all_entries.values():
                        entry.configure(state="disabled")
                    
                    # Store image and datasheet paths
                    nonlocal current_image_path, current_datasheet_path
                    current_image_path = component.get("image_path")
                    current_datasheet_path = component.get("datasheet_path")
                    
                    # Load and display image if exists (Large: max height 300px, keeping aspect ratio)
                    if current_image_path:
                        try:
                            # Se for caminho absoluto, usar diretamente; caso contrário, usar get_base_path()
                            if os.path.isabs(current_image_path):
                                full_img_path = current_image_path
                            else:
                                base_path = get_base_path()
                                full_img_path = os.path.join(base_path, current_image_path)
                            
                            if os.path.exists(full_img_path):
                                img = Image.open(full_img_path)
                                img.thumbnail((400, 300), Image.Resampling.LANCZOS)  # Large preview (max 400x300)
                                preview_image = ImageTk.PhotoImage(img)
                                image_preview_label.configure(image=preview_image, text="")
                        except Exception as e:
                            pass  # Silently fail if image can't be loaded
                    
                    # Show PDF button if datasheet exists
                    if current_datasheet_path:
                        view_pdf_button.pack(pady=5)
            
            run_db_operation(self.app.root, db_operation, callback)
        
        # Load data after a small delay
        details_window.after(100, load_component_data)
    
    def delete_component(self, component_id: int):
        """Remove um componente com confirmação segura"""
        # Primeiro obter informações do componente para mostrar no diálogo
        def get_component():
            return self.app.db_manager.get_component_by_id(component_id)
        
        def confirm_and_delete(component, error):
            if error:
                messagebox.showerror("Erro", f"Erro ao carregar componente: {str(error)}")
                return
            
            if not component:
                messagebox.showerror("Erro", "Componente não encontrado!")
                return
            
            # Mostrar diálogo de confirmação com nome do componente
            component_name = component.get("name", "desconhecido")
            confirm_message = (
                f"Tem a certeza que pretende eliminar o componente '{component_name}'?\n\n"
                f"Esta ação é irreversível."
            )
            
            if messagebox.askyesno("Confirmar Eliminação", confirm_message):
                # Proceder com eliminação
                def db_operation():
                    return self.app.db_manager.delete_component(component_id)
                
                def callback(result, error):
                    if error:
                        messagebox.showerror("Erro", f"Erro ao remover componente: {str(error)}")
                    elif result:
                        messagebox.showinfo("Operação Concluída", "Componente removido com sucesso.")
                        self.refresh_data()
                    else:
                        messagebox.showerror("Erro", "Erro ao remover componente!")
                
                run_db_operation(self.app.root, db_operation, callback)
        
        run_db_operation(self.app.root, get_component, confirm_and_delete)
    
    def open_fast_restock_dialog(self):
        """
        Abre diálogo para entrada rápida de stock.
        Fluxo: Pesquisar/Scan -> Selecionar -> Inserir quantidade -> Guardar.
        """
        try:
            # Criar janela de diálogo
            dialog = ctk.CTkToplevel(self)
            dialog.title("Entrada de Stock")
            dialog.geometry("600x500")
            dialog.minsize(500, 400)
            dialog.resizable(True, True)
            dialog.transient(self)
            
            # Centralizar
            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() // 2) - (600 // 2)
            y = (dialog.winfo_screenheight() // 2) - (500 // 2)
            dialog.geometry(f"600x500+{x}+{y}")
            
            # Container principal
            main_frame = ctk.CTkFrame(dialog)
            main_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            # Título
            title_label = ctk.CTkLabel(
                main_frame,
                text="Entrada de Stock",
                font=ctk.CTkFont(size=20, weight="bold")
            )
            title_label.pack(pady=(0, 15))
            
            # Barra de pesquisa (topo)
            search_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
            search_frame.pack(fill="x", pady=(0, 10))
            
            search_label = ctk.CTkLabel(
                search_frame,
                text="Pesquisar:",
                font=ctk.CTkFont(size=14)
            )
            search_label.pack(side="left", padx=(0, 10))
            
            search_entry = ctk.CTkEntry(
                search_frame,
                placeholder_text="Digite o código ou nome...",
                font=ctk.CTkFont(size=14),
                height=35
            )
            search_entry.pack(side="left", fill="x", expand=True)
            search_entry.focus_set()
            
            # Área de resultados (scrollable) - começa vazia
            results_label = ctk.CTkLabel(
                main_frame,
                text="Resultados:",
                font=ctk.CTkFont(size=12),
                anchor="w"
            )
            results_label.pack(fill="x", pady=(10, 5))
            
            results_scrollable = ctk.CTkScrollableFrame(main_frame)
            results_scrollable.pack(fill="both", expand=True, pady=(0, 10))

            # Frame oculto para seleção + quantidade (mostrado após seleção)
            quantity_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
            quantity_frame.pack(fill="x", pady=(5, 0))
            quantity_frame.pack_forget()
            
            selected_info_label = ctk.CTkLabel(
                quantity_frame,
                text="",
                font=ctk.CTkFont(size=14, weight="bold"),
                anchor="w"
            )
            selected_info_label.pack(fill="x", pady=(0, 5))
            
            qty_label = ctk.CTkLabel(
                quantity_frame,
                text="Quantidade a Adicionar:",
                font=ctk.CTkFont(size=12)
            )
            qty_label.pack(anchor="w", pady=(0, 5))
            
            qty_entry = ctk.CTkEntry(
                quantity_frame,
                font=ctk.CTkFont(size=14),
                height=35
            )
            qty_entry.pack(fill="x")
            
            buttons_frame = ctk.CTkFrame(quantity_frame, fg_color="transparent")
            buttons_frame.pack(fill="x", pady=(5, 0))

            # Estado do componente selecionado
            selected_component = {"id": None, "code": "", "name": "", "qty": 0}

            def save_quantity():
                try:
                    qty_str = qty_entry.get().strip()
                    if not qty_str:
                        messagebox.showwarning("Atenção", "Por favor, insira uma quantidade!")
                        return
                    
                    quantity_to_add = int(qty_str)
                    if quantity_to_add == 0:
                        messagebox.showwarning("Atenção", "A quantidade deve ser diferente de zero!")
                        return
                    
                    if selected_component["id"] is None:
                        messagebox.showwarning("Atenção", "Nenhum componente selecionado!")
                        return
                    
                    if selected_component["qty"] + quantity_to_add < 0:
                        messagebox.showwarning(
                            "Atenção",
                            f"Stock insuficiente. Stock atual: {selected_component['qty']}"
                        )
                        return
                    
                    component_id = selected_component["id"]
                    
                    def db_operation():
                        return self.app.db_manager.add_stock_quantity(component_id, quantity_to_add)
                    
                    def callback(new_qty, error):
                        if error:
                            messagebox.showerror("Erro", f"Erro ao adicionar stock: {str(error)}")
                        elif new_qty is not None:
                            messagebox.showinfo(
                                "Stock Atualizado",
                                f"Stock atualizado com sucesso!\n\nNovo total: {new_qty}"
                            )
                            dialog.destroy()
                            self.refresh_data(force=True)
                        else:
                            messagebox.showerror("Erro", "Erro ao adicionar stock!")
                    
                    run_db_operation(self.app.root, db_operation, callback)
                    
                except ValueError:
                    messagebox.showerror("Erro", "Por favor, insira um número válido!")
                except Exception as e:
                    messagebox.showerror("Erro", f"Erro inesperado: {str(e)}")
            
            save_button = ctk.CTkButton(
                buttons_frame,
                text="Guardar",
                command=save_quantity,
                font=ctk.CTkFont(size=14, weight="bold"),
                fg_color=["#4CAF50", "#4CAF50"],
                hover_color=["#45a049", "#45a049"],
                height=35
            )
            save_button.pack(side="left", padx=(0, 10), expand=True)
            
            cancel_button = ctk.CTkButton(
                buttons_frame,
                text="Cancelar",
                command=dialog.destroy,
                font=ctk.CTkFont(size=14),
                fg_color="transparent",
                hover_color=["#555555", "#333333"],
                height=35
            )
            cancel_button.pack(side="left", expand=True)

            # Permitir Enter para guardar rapidamente
            dialog.bind("<Return>", lambda e: save_quantity())

            # Renderização de resultados
            def render_results(components):
                for widget in results_scrollable.winfo_children():
                    widget.destroy()

                if not components:
                    no_data_label = ctk.CTkLabel(
                        results_scrollable,
                        text="Nenhum componente encontrado",
                        font=ctk.CTkFont(size=14),
                        text_color=["#666666", "#999999"]
                    )
                    no_data_label.pack(pady=20)
                    return

                for comp in components:
                    comp_id = comp.get("id")
                    code = comp.get("code", "")
                    name = comp.get("name", "")
                    qty = comp.get("qty", 0)

                    item_frame = ctk.CTkFrame(results_scrollable)
                    item_frame.pack(fill="x", pady=3, padx=5)

                    item_text = f"[{code}] {name} (Atual: {qty})"
                    item_label = ctk.CTkLabel(
                        item_frame,
                        text=item_text,
                        font=ctk.CTkFont(size=13),
                        anchor="w"
                    )
                    item_label.pack(side="left", padx=10, pady=8, fill="x", expand=True)

                    def on_select(local_comp=comp):
                        selected_component["id"] = local_comp.get("id")
                        selected_component["code"] = local_comp.get("code", "")
                        selected_component["name"] = local_comp.get("name", "")
                        selected_component["qty"] = local_comp.get("qty", 0)

                        for widget in results_scrollable.winfo_children():
                            widget.destroy()

                        info_text = f"[{selected_component['code']}] {selected_component['name']} (Stock Atual: {selected_component['qty']})"
                        selected_info_label.configure(text=info_text)
                        quantity_frame.pack(fill="x", pady=(5, 0))
                        qty_entry.delete(0, "end")
                        qty_entry.focus_set()

                    item_label.bind("<Button-1>", lambda e, lc=comp: on_select(lc))

                    select_button = ctk.CTkButton(
                        item_frame,
                        text="Selecionar",
                        command=lambda lc=comp: on_select(lc),
                        font=ctk.CTkFont(size=12),
                        width=100,
                        height=30,
                        fg_color=["#4CAF50", "#4CAF50"],
                        hover_color=["#45a049", "#45a049"]
                    )
                    select_button.pack(side="right", padx=10, pady=5)

            def perform_search(term: str, limit: int = 5, auto_select_on_exact_code: bool = False):
                term = term.strip()
                if not term:
                    for widget in results_scrollable.winfo_children():
                        widget.destroy()
                    quantity_frame.pack_forget()
                    selected_component["id"] = None
                    return

                def db_operation():
                    return self.app.db_manager.search_stock_smart(term, limit=limit)

                def callback(components, error):
                    if error:
                        messagebox.showerror("Erro", f"Erro ao pesquisar componentes: {str(error)}")
                        return

                    if auto_select_on_exact_code and components:
                        term_lower = term.lower().strip()
                        exact_matches = [
                            c for c in components
                            if str(c.get("code", "")).lower().strip() == term_lower
                        ]
                        if len(exact_matches) == 1:
                            comp = exact_matches[0]
                            selected_component["id"] = comp.get("id")
                            selected_component["code"] = comp.get("code", "")
                            selected_component["name"] = comp.get("name", "")
                            selected_component["qty"] = comp.get("qty", 0)

                            for widget in results_scrollable.winfo_children():
                                widget.destroy()

                            info_text = f"[{selected_component['code']}] {selected_component['name']} (Stock Atual: {selected_component['qty']})"
                            selected_info_label.configure(text=info_text)
                            quantity_frame.pack(fill="x", pady=(5, 0))
                            qty_entry.delete(0, "end")
                            qty_entry.focus_set()
                            return

                    # Caso geral: renderizar top N resultados
                    render_results(components)

                run_db_operation(self.app.root, db_operation, callback)

            # Debounce interno para pesquisa
            SEARCH_DELAY = 300
            search_timer = {"id": None}

            def on_search_key_release(event=None):
                try:
                    if search_timer["id"] is not None:
                        dialog.after_cancel(search_timer["id"])
                    term = search_entry.get()
                    search_timer["id"] = dialog.after(
                        SEARCH_DELAY,
                        lambda: perform_search(term, limit=5, auto_select_on_exact_code=False)
                    )
                except Exception:
                    pass

            def on_search_return(event=None):
                term = search_entry.get()
                perform_search(term, limit=10, auto_select_on_exact_code=True)

            search_entry.bind("<KeyRelease>", on_search_key_release)
            search_entry.bind("<Return>", on_search_return)

            # Botão fechar
            close_button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
            close_button_frame.pack(fill="x", pady=(10, 0))
            
            close_button = ctk.CTkButton(
                close_button_frame,
                text="Fechar",
                command=dialog.destroy,
                font=ctk.CTkFont(size=14),
                fg_color="transparent",
                hover_color=["#555555", "#333333"],
                height=35
            )
            close_button.pack(side="right")

        except Exception as e:
            print(f"CRITICAL ERROR: Erro ao abrir Entrada de Stock: {e}")
            messagebox.showerror("Erro", f"Erro inesperado ao abrir Entrada de Stock:\n\n{e}")
    
    def refresh_data(self, force: bool = False):
        """
        Atualiza a lista de componentes a partir da pesquisa (modo search-first).
        
        - Não carrega toda a tabela.
        - Se a pesquisa estiver vazia, mostra apenas uma mensagem de ajuda.
        """
        if self.is_loading:
            return
        
        self.is_loading = True
        # Mostrar indicador de carregamento
        self.loading_label.pack(pady=20)
        
        # Obter termo de pesquisa
        search_term = self.search_entry.get().strip()
        
        def db_operation():
            # Se não houver termo de pesquisa, não carregar nada da BD
            if not search_term:
                return []
            # Usar função otimizada na BD (máx 10 resultados)
            return self.app.db_manager.search_stock_smart(search_term, limit=10)
        
        def callback(components, error):
            self.is_loading = False
            self.loading_label.pack_forget()
            
            if error:
                messagebox.showerror("Erro", f"Erro ao carregar dados: {str(error)}")
                return

            # Calcular hash dos dados para evitar refresh desnecessário
            import hashlib
            data_str = str(sorted([(c["id"], c["code"], c["name"], c["price"], c["qty"]) for c in components]))
            data_hash = hashlib.md5(data_str.encode()).hexdigest()
            
            # Se dados não mudaram e não é refresh forçado, não atualizar UI
            if not force and data_hash == self.current_data_hash:
                return  # Dados não mudaram, não precisa atualizar
            
            self.current_data_hash = data_hash
            
            # Limpar lista atual
            for widget in self.list_container.winfo_children():
                widget.destroy()
            
            # Se não há componentes, mostrar mensagem adequada
            if not components:
                if not search_term:
                    text = "Digite um código ou nome para pesquisar..."
                else:
                    text = "Nenhum componente encontrado"
                no_data_label = ctk.CTkLabel(
                    self.list_container,
                    text=text,
                    font=ctk.CTkFont(size=16),
                    text_color=["#666666", "#999999"]
                )
                no_data_label.pack(pady=50)
                return
            
            # Criar cabeçalho da tabela
            header_frame = ctk.CTkFrame(self.list_container, fg_color=["#e0e0e0", "#2b2b2b"])
            header_frame.pack(fill="x", pady=(0, 10))
            
            # Configurar pesos das colunas (Code:1, Name:4, Family:2, Preço Compra:1, Price:1, Qty:1, Actions:2)
            column_weights = [1, 4, 2, 1, 1, 1, 2]
            for i, weight in enumerate(column_weights):
                if i == 6:  # Actions column - needs minimum width
                    header_frame.grid_columnconfigure(i, weight=weight, uniform="stock_cols", minsize=150)
                else:
                    header_frame.grid_columnconfigure(i, weight=weight, uniform="stock_cols")
            
            headers = ["Código", "Nome", "Família", "Preço Compra", "Preço Venda", "Qtd", "Ações"]
            
            for i, header in enumerate(headers):
                label = ctk.CTkLabel(
                    header_frame,
                    text=header,
                    font=ctk.CTkFont(size=14, weight="bold"),
                    anchor="w"
                )
                label.grid(row=0, column=i, padx=5, pady=10, sticky="ew")
            
            # Adicionar componentes (máx 10 resultados)
            for component in components:
                self.create_component_row(component)
        
        run_db_operation(self.app.root, db_operation, callback)
    
    def create_component_row(self, component: dict):
        """Cria uma linha na lista para um componente"""
        row_frame = ctk.CTkFrame(self.list_container)
        row_frame.pack(fill="x", pady=5)
        
        # Configurar pesos das colunas (idêntico ao header)
        column_weights = [1, 4, 2, 1, 1, 1, 2]
        for i, weight in enumerate(column_weights):
            if i == 6:  # Actions column - needs minimum width
                row_frame.grid_columnconfigure(i, weight=weight, uniform="stock_cols", minsize=150)
            else:
                row_frame.grid_columnconfigure(i, weight=weight, uniform="stock_cols")
        
        # Dados
        code_label = ctk.CTkLabel(
            row_frame,
            text=component["code"],
            font=ctk.CTkFont(size=13),
            anchor="w"
        )
        code_label.grid(row=0, column=0, padx=5, pady=10, sticky="ew")
        
        # Nome (sem indicador visual de foto)
        name_text = component["name"]
        
        name_label = ctk.CTkLabel(
            row_frame,
            text=name_text,
            font=ctk.CTkFont(size=13),
            anchor="w"
        )
        name_label.grid(row=0, column=1, padx=5, pady=10, sticky="ew")
        
        # Família (Family)
        family_text = component.get("family", "") or "—"  # Show "—" if empty
        family_label = ctk.CTkLabel(
            row_frame,
            text=family_text,
            font=ctk.CTkFont(size=13),
            anchor="w",
            text_color=["#666666", "#999999"] if not component.get("family") else ["#333333", "#cccccc"]
        )
        family_label.grid(row=0, column=2, padx=5, pady=10, sticky="ew")
        
        # Preço de venda e preço de compra (preco_compra armazenado na BD)
        selling_price = component["price"]
        preco_compra = component.get("preco_compra", None)

        # Se houver preço de compra na BD, usar; caso contrário, estimar a partir da margem
        if preco_compra is None:
            try:
                default_margin = float(self.app.db_manager.get_setting("default_margin", "30"))
                preco_compra = selling_price / (1 + default_margin / 100)
            except Exception:
                preco_compra = selling_price  # Fallback
        
        cost_label = ctk.CTkLabel(
            row_frame,
            text=f"{preco_compra:.2f} €",
            font=ctk.CTkFont(size=13),
            anchor="w"
        )
        cost_label.grid(row=0, column=3, padx=5, pady=10, sticky="ew")
        
        # Preço de Venda
        price_label = ctk.CTkLabel(
            row_frame,
            text=f"{selling_price:.2f} €",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
            text_color=["#4CAF50", "#4CAF50"]
        )
        price_label.grid(row=0, column=4, padx=5, pady=10, sticky="ew")
        
        # Quantidade com alerta de stock baixo
        qty = component["qty"]
        is_low_stock = qty < 5
        
        qty_label = ctk.CTkLabel(
            row_frame,
            text=str(qty),
            font=ctk.CTkFont(size=13, weight="bold" if is_low_stock else "normal"),
            anchor="w",
            text_color=["#F44336", "#F44336"] if is_low_stock else ["#333333", "#cccccc"]
        )
        qty_label.grid(row=0, column=5, padx=5, pady=10, sticky="ew")
        
        # Botões de ação
        actions_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
        actions_frame.grid(row=0, column=6, padx=5, pady=5, sticky="ew")
        actions_frame.grid_columnconfigure(0, weight=1)
        actions_frame.grid_columnconfigure(1, weight=1)
        
        # Wrappers seguros para os botões
        def safe_edit_command(comp_id):
            """Wrapper seguro para editar componente"""
            try:
                self.edit_component(comp_id)
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao editar componente: {str(e)}")
        
        def safe_delete_command(comp_id):
            """Wrapper seguro para remover componente"""
            try:
                self.delete_component(comp_id)
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao remover componente: {str(e)}")
        
        # View/Details button
        view_button = ctk.CTkButton(
            actions_frame,
            text="Detalhes",
            command=lambda: safe_edit_command(component["id"]),  # Will open details window
            font=ctk.CTkFont(size=12),
            fg_color=["#2196F3", "#2196F3"],
            hover_color=["#1976D2", "#1976D2"],
            width=90,
            height=30
        )
        view_button.pack(side="left", padx=2)
        
        delete_button = ctk.CTkButton(
            actions_frame,
            text="Remover",
            command=lambda: safe_delete_command(component["id"]),
            font=ctk.CTkFont(size=12),
            fg_color=["#f44336", "#f44336"],
            hover_color=["#d32f2f", "#d32f2f"],
            width=80,
            height=30
        )
        delete_button.pack(side="left", padx=2)
    
    def import_from_excel(self):
        """Importa componentes de um ficheiro Excel (folha 'Stock' do Master Excel, se existir)"""
        try:
            # Solicitar ficheiro para importar
            filename = filedialog.askopenfilename(
                filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
                title="Importar Stock do Excel"
            )
            
            if not filename:
                return  # Utilizador cancelou
            
            if not os.path.exists(filename):
                messagebox.showerror("Erro", "Ficheiro não encontrado!")
                return
            
            # Executar importação usando método do DB (smart sheet detection)
            def db_operation():
                return self.app.db_manager.import_stock_from_excel(filename)
            
            def callback(result, error):
                if error:
                    messagebox.showerror("Erro", f"Erro ao importar stock:\n\n{str(error)}")
                    return
                
                imported = result.get("imported", 0)
                updated = result.get("updated", 0)
                message = "Importação concluída.\n\n"
                message += f"{imported} novos componentes.\n{updated} componentes atualizados."
                messagebox.showinfo("Operação Concluída", message)
                self.refresh_data(force=True)
            
            run_db_operation(self.app.root, db_operation, callback)
        
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {str(e)}")
