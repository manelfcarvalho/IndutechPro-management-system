"""
Página de Gestão de Clientes (CRM)
Permite visualizar, adicionar, editar e remover clientes
"""

import customtkinter as ctk
from tkinter import messagebox
from typing import List, Dict, Optional
from ui.utils import Debouncer, run_db_operation
from ui.theme import (
    apply_modern_style,
    create_action_button,
    create_action_footer,
    create_page_header,
    create_table_action_button,
    create_table_actions_frame,
    create_table_cell,
    create_table_header,
    create_table_row,
    create_toolbar_button,
)


class ClientListPage(ctk.CTkFrame):
    """Página de gestão de clientes"""

    def __init__(self, parent, app):
        """
        Inicializa a página de clientes

        Args:
            parent: Widget pai
            app: Instância da aplicação principal
        """
        super().__init__(parent, fg_color="#151617")
        self.app = app
        self.current_edit_id = None  # ID do cliente sendo editado
        self.setup_ui()
        self.refresh_data()

    def setup_ui(self):
        """Configura a interface da página de clientes"""
        # Título
        _, buttons_frame = create_page_header(
            self,
            "Clientes",
            "Gerir contactos, dados fiscais e historico por cliente.",
        )

        # Botão voltar
        # Container principal
        main_container = ctk.CTkFrame(self, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=20, pady=(8, 12))

        # Header: Botão Novo Cliente + Pesquisa

        # Botão Novo Cliente
        create_toolbar_button(buttons_frame, "Novo Cliente", self.open_client_dialog, role="success", width=130)

        # Botão Importar Excel
        create_toolbar_button(buttons_frame, "Importar Excel", self.import_from_excel, role="primary", width=130)

        # Barra de pesquisa
        search_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        search_frame.pack(fill="x", pady=(0, 12))

        search_label = ctk.CTkLabel(
            search_frame,
            text="Pesquisar",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#b8b8b8",
        )
        search_label.pack(side="left", padx=(0, 10))

        self.search_entry = ctk.CTkEntry(
            search_frame,
            font=ctk.CTkFont(size=14),
            placeholder_text="Pesquisar por Nome, Telemóvel ou NIF..."
        )
        self.search_entry.configure(height=34)
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
        table_frame = ctk.CTkFrame(
            main_container,
            fg_color="#202124",
            corner_radius=8,
            border_width=1,
            border_color="#35363a",
        )
        table_frame.pack(fill="both", expand=True)

        # Cabeçalho da tabela
        header_row = create_table_header(
            table_frame,
            ["ID", "Nome", "Telemovel", "NIF", "Acoes"],
            [1, 3, 2, 1, 2],
            "client_cols",
            padx=18,
            pady=(16, 8),
        )

        # Configurar pesos das colunas (ID:1, Nome:3, Telemóvel:2, NIF:1, Ações:2)



        # Container scrollável para linhas
        self.clients_list_container = ctk.CTkScrollableFrame(
            table_frame,
            fg_color="#151617",
            corner_radius=8,
            border_width=1,
            border_color="#35363a",
        )
        self.clients_list_container.pack(fill="both", expand=True, padx=18, pady=(0, 14))

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
        row_frame = create_table_row(
            self.clients_list_container,
            [1, 3, 2, 1, 2],
            "client_cols",
        )

        # Configurar pesos das colunas (idêntico ao header)

        # ID
        id_label = create_table_cell(
            row_frame,
            text=str(client.get("id", "N/A")),
            column=0,
            text_color="#8f949c",
            padx=10,
            pady=10,
        )

        # Nome
        name_label = create_table_cell(
            row_frame,
            text=client.get("name", "N/A"),
            column=1,
            weight="bold",
            text_color="#f5f5f5",
            padx=10,
            pady=10,
        )

        # Telemóvel
        phone_label = create_table_cell(
            row_frame,
            text=client.get("phone", "N/A"),
            column=2,
            text_color="#c9ced6",
            padx=10,
            pady=10,
        )

        # NIF
        nif_label = create_table_cell(
            row_frame,
            text=client.get("nif", "N/A") or "N/A",
            column=3,
            text_color="#c9ced6",
            padx=10,
            pady=10,
        )

        # Ações
        actions_frame = create_table_actions_frame(row_frame, row=0, column=4, padx=10, pady=8)

        # Botão Editar
        edit_button = create_table_action_button(
            actions_frame,
            text="Editar",
            command=lambda c=client: self.open_client_dialog(c),
            role="primary",
            width=80,
        )

        # Botão Remover
        remove_button = create_table_action_button(
            actions_frame,
            text="Remover",
            command=lambda c=client: self.delete_client(c),
            role="danger",
            width=80,
        )

    def open_client_dialog(self, client: Optional[dict] = None):
        """Abre diálogo para adicionar/editar cliente"""
        is_edit = client is not None
        client_id = client.get("id") if client else None
        self.current_edit_id = client_id

        # Criar janela de diálogo
        dialog = ctk.CTkToplevel(self.app.root)
        dialog.title("Editar Cliente" if is_edit else "Novo Cliente")
        dialog.geometry("500x500")
        dialog.minsize(400, 450)
        dialog.configure(fg_color="#151617")
        dialog.transient(self.app.root)
        dialog.grab_set()

        # Frame principal
        main_frame = ctk.CTkFrame(
            dialog,
            fg_color="#202124",
            corner_radius=8,
            border_width=1,
            border_color="#35363a",
        )
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Título
        title_label = ctk.CTkLabel(
            main_frame,
            text="Editar Cliente" if is_edit else "Novo Cliente",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#f5f5f5",
        )
        title_label.pack(anchor="w", padx=18, pady=(18, 18))

        # Campos
        name_label = ctk.CTkLabel(main_frame, text="Nome *", font=ctk.CTkFont(size=12, weight="bold"), text_color="#b8b8b8")
        name_label.pack(anchor="w", padx=18, pady=(0, 5))
        name_entry = ctk.CTkEntry(main_frame, font=ctk.CTkFont(size=14), height=34)
        name_entry.pack(fill="x", padx=18, pady=(0, 12))
        if client:
            name_entry.insert(0, client.get("name", ""))

        phone_label = ctk.CTkLabel(main_frame, text="Telemóvel *", font=ctk.CTkFont(size=14))
        phone_label.configure(text="Telemovel *", font=ctk.CTkFont(size=12, weight="bold"), text_color="#b8b8b8")
        phone_label.pack(anchor="w", padx=18, pady=(0, 5))
        phone_entry = ctk.CTkEntry(main_frame, font=ctk.CTkFont(size=14), height=34)
        phone_entry.pack(fill="x", padx=18, pady=(0, 12))
        if client:
            phone_entry.insert(0, client.get("phone", ""))

        nif_label = ctk.CTkLabel(main_frame, text="NIF", font=ctk.CTkFont(size=12, weight="bold"), text_color="#b8b8b8")
        nif_label.pack(anchor="w", padx=18, pady=(0, 5))
        nif_entry = ctk.CTkEntry(main_frame, font=ctk.CTkFont(size=14), height=34)
        nif_entry.pack(fill="x", padx=18, pady=(0, 12))
        if client:
            nif_entry.insert(0, client.get("nif", "") or "")

        address_label = ctk.CTkLabel(main_frame, text="Morada", font=ctk.CTkFont(size=12, weight="bold"), text_color="#b8b8b8")
        address_label.pack(anchor="w", padx=18, pady=(0, 5))
        address_entry = ctk.CTkEntry(main_frame, font=ctk.CTkFont(size=14), height=34)
        address_entry.pack(fill="x", padx=18, pady=(0, 18))
        if client:
            address_entry.insert(0, client.get("address", "") or "")

        # Botões
        buttons_frame = create_action_footer(main_frame)

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
                return self._save_client_record(client_id, name, phone, nif, address)

            def callback(client_id, error):
                if error:
                    messagebox.showerror("Erro", f"Erro ao guardar cliente: {str(error)}")
                    return

                messagebox.showinfo("Operação Concluída", "Cliente guardado com sucesso.")
                dialog.destroy()
                self.refresh_data()

            run_db_operation(self.app.root, db_operation, callback)

        save_button = create_action_button(
            buttons_frame,
            text="Guardar",
            command=on_save,
            role="success",
            width=130,
        )

        cancel_button = create_action_button(
            buttons_frame,
            text="Cancelar",
            command=dialog.destroy,
            role="secondary",
            width=120,
        )
        apply_modern_style(dialog)

        # Centralizar diálogo
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

    def _save_client_record(self, client_id: Optional[int], name: str, phone: str, nif: str, address: str) -> int:
        """Cria ou atualiza cliente mantendo a edicao presa ao ID original."""
        if client_id:
            return self.app.db_manager.update_client(client_id, name, phone, nif, address)
        return self.app.db_manager.add_or_update_client(name, phone, nif, address)

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
            return self.app.db_manager.delete_client(client.get("id"))

        def callback(success, error):
            if error:
                if isinstance(error, ValueError):
                    messagebox.showwarning("Cliente com historico", str(error))
                else:
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
