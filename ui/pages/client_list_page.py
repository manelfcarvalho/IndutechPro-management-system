"""
Página de Gestão de Clientes (CRM)
Permite visualizar, adicionar, editar e remover clientes
"""

import customtkinter as ctk
from tkinter import messagebox
from typing import List, Dict, Optional
from ui.utils import Debouncer, run_db_operation


class ClientListPage(ctk.CTkFrame):
    """Página de gestão de clientes"""
    
    def __init__(self, parent, app):
        """
        Inicializa a página de clientes
        
        Args:
            parent: Widget pai
            app: Instância da aplicação principal
        """
        super().__init__(parent, fg_color=["#f0f0f0", "#1a1a1a"])
        self.app = app
        self.current_edit_id = None  # ID do cliente sendo editado
        self.setup_ui()
        self.refresh_data()
    
    def setup_ui(self):
        """Configura a interface da página de clientes"""
        # Título
        title_frame = ctk.CTkFrame(self, fg_color="transparent")
        title_frame.pack(fill="x", padx=20, pady=(20, 10))
        
        title_label = ctk.CTkLabel(
            title_frame,
            text="Meus Clientes",
            font=ctk.CTkFont(size=32, weight="bold"),
            text_color=["#FF5722", "#FF5722"]
        )
        title_label.pack(side="left")
        
        # Botão voltar
        back_button = ctk.CTkButton(
            title_frame,
            text="Voltar",
            command=lambda: self.app.show_page("home"),
            font=ctk.CTkFont(size=14),
            fg_color="transparent",
            hover_color=["#555555", "#333333"],
            width=100,
            height=30
        )
        back_button.pack(side="right")
        
        # Container principal
        main_container = ctk.CTkFrame(self, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=20, pady=10)
        
        # Header: Botão Novo Cliente + Pesquisa
        header_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 15))
        
        # Botão Novo Cliente
        new_client_button = ctk.CTkButton(
            header_frame,
            text="Novo Cliente",
            command=self.open_client_dialog,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=["#4CAF50", "#4CAF50"],
            hover_color=["#45a049", "#45a049"],
            width=150,
            height=40
        )
        new_client_button.pack(side="left", padx=(0, 15))
        
        # Botão Importar Excel
        import_button = ctk.CTkButton(
            header_frame,
            text="Importar Excel",
            command=self.import_from_excel,
            font=ctk.CTkFont(size=14),
            fg_color=["#2196F3", "#2196F3"],
            hover_color=["#1976D2", "#1976D2"],
            width=150,
            height=40
        )
        import_button.pack(side="left", padx=(0, 15))
        
        # Barra de pesquisa
        search_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        search_frame.pack(side="left", fill="x", expand=True)
        
        search_label = ctk.CTkLabel(
            search_frame,
            text="Pesquisar",
            font=ctk.CTkFont(size=12)
        )
        search_label.pack(side="left", padx=(0, 10))
        
        self.search_entry = ctk.CTkEntry(
            search_frame,
            font=ctk.CTkFont(size=14),
            placeholder_text="Pesquisar por Nome, Telemóvel ou NIF..."
        )
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_entry.bind("<KeyRelease>", self.on_search)
        
        # Inicializar Debouncer para pesquisa
        def do_search():
            self.refresh_data()
        
        self.search_debouncer = Debouncer(
            do_search,
            self.winfo_toplevel(),
            delay=300
        )
        
        # Tabela de clientes (scrollable)
        table_frame = ctk.CTkFrame(main_container)
        table_frame.pack(fill="both", expand=True)
        
        # Cabeçalho da tabela
        header_row = ctk.CTkFrame(table_frame, fg_color=["#FF5722", "#FF5722"])
        header_row.pack(fill="x", padx=0, pady=0)
        
        # Configurar pesos das colunas (ID:1, Nome:3, Telemóvel:2, NIF:1, Ações:2)
        column_weights = [1, 3, 2, 1, 2]
        for i, weight in enumerate(column_weights):
            header_row.grid_columnconfigure(i, weight=weight, uniform="client_cols")
        
        headers = ["ID", "Nome", "Telemóvel", "NIF", "Ações"]
        
        for i, header in enumerate(headers):
            anchor = "w" if i < len(headers) - 1 else "center"
            label = ctk.CTkLabel(
                header_row,
                text=header,
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=["#ffffff", "#ffffff"],
                anchor=anchor
            )
            label.grid(row=0, column=i, padx=10, pady=15, sticky="ew")
        
        # Container scrollável para linhas
        self.clients_list_container = ctk.CTkScrollableFrame(
            table_frame,
            fg_color=["#ffffff", "#2b2b2b"]
        )
        self.clients_list_container.pack(fill="both", expand=True, padx=0, pady=0)
    
    def on_search(self, _=None):
        """Callback para pesquisa"""
        if hasattr(self, 'search_debouncer'):
            self.search_debouncer()
    
    def refresh_data(self):
        """Atualiza a lista de clientes"""
        query = self.search_entry.get().strip()
        
        def db_operation():
            # Pesquisa otimizada (search-first) com limite curto
            # - query vazia: últimos clientes criados
            # - query com texto: procura em nome, NIF e telefone
            return self.app.db_manager.search_clients_smart(query, limit=10)
        
        def callback(clients, error):
            if error:
                messagebox.showerror("Erro", f"Erro ao carregar clientes: {str(error)}")
                return
            
            # Limpar lista anterior
            for widget in self.clients_list_container.winfo_children():
                widget.destroy()
            
            if not clients:
                no_results = ctk.CTkLabel(
                    self.clients_list_container,
                    text="Nenhum cliente encontrado",
                    font=ctk.CTkFont(size=14),
                    text_color=["#999999", "#666666"]
                )
                no_results.pack(pady=20)
                return
            
            # Criar linhas para cada cliente
            for client in clients:
                self.create_client_row(client)
        
        run_db_operation(self.app.root, db_operation, callback)
    
    def create_client_row(self, client: dict):
        """Cria uma linha na tabela para um cliente"""
        row_frame = ctk.CTkFrame(
            self.clients_list_container,
            fg_color=["#f9f9f9", "#2b2b2b"],
            corner_radius=5
        )
        row_frame.pack(fill="x", padx=5, pady=3)
        
        # Configurar pesos das colunas (idêntico ao header)
        column_weights = [1, 3, 2, 1, 2]
        for i, weight in enumerate(column_weights):
            row_frame.grid_columnconfigure(i, weight=weight, uniform="client_cols")
        
        # ID
        id_label = ctk.CTkLabel(
            row_frame,
            text=str(client.get("id", "N/A")),
            font=ctk.CTkFont(size=12),
            anchor="w"
        )
        id_label.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        
        # Nome
        name_label = ctk.CTkLabel(
            row_frame,
            text=client.get("name", "N/A"),
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w"
        )
        name_label.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        
        # Telemóvel
        phone_label = ctk.CTkLabel(
            row_frame,
            text=client.get("phone", "N/A"),
            font=ctk.CTkFont(size=12),
            anchor="w"
        )
        phone_label.grid(row=0, column=2, padx=10, pady=10, sticky="ew")
        
        # NIF
        nif_label = ctk.CTkLabel(
            row_frame,
            text=client.get("nif", "N/A") or "N/A",
            font=ctk.CTkFont(size=12),
            anchor="w"
        )
        nif_label.grid(row=0, column=3, padx=10, pady=10, sticky="ew")
        
        # Ações
        actions_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
        actions_frame.grid(row=0, column=4, padx=10, pady=10, sticky="ew")
        actions_frame.grid_columnconfigure(0, weight=1)
        actions_frame.grid_columnconfigure(1, weight=1)
        
        # Botão Editar
        edit_button = ctk.CTkButton(
            actions_frame,
            text="Editar",
            command=lambda c=client: self.open_client_dialog(c),
            font=ctk.CTkFont(size=11),
            fg_color=["#2196F3", "#2196F3"],
            hover_color=["#1976D2", "#1976D2"],
            width=80,
            height=30
        )
        edit_button.pack(side="left", padx=2)
        
        # Botão Remover
        remove_button = ctk.CTkButton(
            actions_frame,
            text="Remover",
            command=lambda c=client: self.delete_client(c),
            font=ctk.CTkFont(size=11),
            fg_color=["#f44336", "#f44336"],
            hover_color=["#d32f2f", "#d32f2f"],
            width=80,
            height=30
        )
        remove_button.pack(side="left", padx=2)
    
    def open_client_dialog(self, client: Optional[dict] = None):
        """Abre diálogo para adicionar/editar cliente"""
        is_edit = client is not None
        self.current_edit_id = client.get("id") if client else None
        
        # Criar janela de diálogo
        dialog = ctk.CTkToplevel(self.app.root)
        dialog.title("Editar Cliente" if is_edit else "Novo Cliente")
        dialog.geometry("500x500")
        dialog.minsize(400, 450)
        dialog.transient(self.app.root)
        dialog.grab_set()
        
        # Frame principal
        main_frame = ctk.CTkFrame(dialog)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Título
        title_label = ctk.CTkLabel(
            main_frame,
            text="Editar Cliente" if is_edit else "Novo Cliente",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(pady=(0, 20))
        
        # Campos
        name_label = ctk.CTkLabel(main_frame, text="Nome *", font=ctk.CTkFont(size=14))
        name_label.pack(anchor="w", pady=(0, 5))
        name_entry = ctk.CTkEntry(main_frame, font=ctk.CTkFont(size=14), height=35)
        name_entry.pack(fill="x", pady=(0, 15))
        if client:
            name_entry.insert(0, client.get("name", ""))
        
        phone_label = ctk.CTkLabel(main_frame, text="Telemóvel *", font=ctk.CTkFont(size=14))
        phone_label.pack(anchor="w", pady=(0, 5))
        phone_entry = ctk.CTkEntry(main_frame, font=ctk.CTkFont(size=14), height=35)
        phone_entry.pack(fill="x", pady=(0, 15))
        if client:
            phone_entry.insert(0, client.get("phone", ""))
        
        nif_label = ctk.CTkLabel(main_frame, text="NIF", font=ctk.CTkFont(size=14))
        nif_label.pack(anchor="w", pady=(0, 5))
        nif_entry = ctk.CTkEntry(main_frame, font=ctk.CTkFont(size=14), height=35)
        nif_entry.pack(fill="x", pady=(0, 15))
        if client:
            nif_entry.insert(0, client.get("nif", "") or "")
        
        address_label = ctk.CTkLabel(main_frame, text="Morada", font=ctk.CTkFont(size=14))
        address_label.pack(anchor="w", pady=(0, 5))
        address_entry = ctk.CTkEntry(main_frame, font=ctk.CTkFont(size=14), height=35)
        address_entry.pack(fill="x", pady=(0, 20))
        if client:
            address_entry.insert(0, client.get("address", "") or "")
        
        # Botões
        buttons_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        buttons_frame.pack(fill="x")
        
        def on_save():
            name = name_entry.get().strip()
            phone = phone_entry.get().strip()
            nif = nif_entry.get().strip()
            address = address_entry.get().strip()
            
            if not name:
                messagebox.showerror("Erro", "Por favor, insira o nome do cliente!")
                return
            
            if not phone:
                messagebox.showerror("Erro", "Por favor, insira o telemóvel do cliente!")
                return
            
            def db_operation():
                return self.app.db_manager.add_or_update_client(name, phone, nif, address)
            
            def callback(client_id, error):
                if error:
                    messagebox.showerror("Erro", f"Erro ao guardar cliente: {str(error)}")
                    return
                
                messagebox.showinfo("Operação Concluída", "Cliente guardado com sucesso.")
                dialog.destroy()
                self.refresh_data()
            
            run_db_operation(self.app.root, db_operation, callback)
        
        save_button = ctk.CTkButton(
            buttons_frame,
            text="Guardar",
            command=on_save,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=["#4CAF50", "#4CAF50"],
            hover_color=["#45a049", "#45a049"],
            height=40
        )
        save_button.pack(side="left", padx=(0, 10), expand=True, fill="x")
        
        cancel_button = ctk.CTkButton(
            buttons_frame,
            text="Cancelar",
            command=dialog.destroy,
            font=ctk.CTkFont(size=14),
            fg_color="transparent",
            hover_color=["#555555", "#333333"],
            height=40
        )
        cancel_button.pack(side="left", expand=True, fill="x")
        
        # Centralizar diálogo
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
    
    def delete_client(self, client: dict):
        """Remove um cliente após confirmação"""
        client_name = client.get("name", "desconhecido")
        confirm_message = (
            f"Tem a certeza que deseja apagar o cliente '{client_name}'?\n\n"
            f"Esta ação é irreversível."
        )
        
        if not messagebox.askyesno("Confirmar Eliminação", confirm_message):
            return
        
        def db_operation():
            with self.app.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM clients WHERE id = ?", (client.get("id"),))
                conn.commit()
                return cursor.rowcount > 0
        
        def callback(success, error):
            if error:
                messagebox.showerror("Erro", f"Erro ao apagar cliente: {str(error)}")
                return
            
            if success:
                messagebox.showinfo("Operação Concluída", "Cliente eliminado com sucesso.")
                self.refresh_data()
            else:
                messagebox.showerror("Erro", "Erro ao apagar cliente!")
        
        run_db_operation(self.app.root, db_operation, callback)
    
    def import_from_excel(self):
        """Importa clientes de um ficheiro Excel (folha 'Clientes' do Master Excel, se existir)"""
        try:
            from tkinter import filedialog
            import os
            
            # Solicitar ficheiro para importar
            filename = filedialog.askopenfilename(
                filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
                title="Importar Clientes do Excel"
            )
            
            if not filename:
                return  # Utilizador cancelou
            
            if not os.path.exists(filename):
                messagebox.showerror("Erro", "Ficheiro não encontrado!")
                return
            
            # Executar importação usando método do DB (smart sheet detection)
            def db_operation():
                return self.app.db_manager.import_clients_from_excel(filename)
            
            def callback(result, error):
                if error:
                    messagebox.showerror("Erro", f"Erro ao importar clientes:\n\n{str(error)}")
                    return
                
                imported = result.get("imported", 0)
                updated = result.get("updated", 0)
                message = "Importação concluída.\n\n"
                message += f"{imported} novos clientes.\n{updated} clientes atualizados."
                messagebox.showinfo("Operação Concluída", message)
                self.refresh_data()
            
            run_db_operation(self.app.root, db_operation, callback)
        
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado: {str(e)}")