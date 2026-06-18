"""
Página Inicial (Home) - Dashboard Principal
Exibe logo, estatísticas e botões de navegação
"""

import customtkinter as ctk
from tkinter import messagebox, filedialog
from PIL import Image
import os
import sys
from ui.utils import run_db_operation, resource_path


# Cache global para a imagem do logo
_logo_cache = None
_logo_path = None


def get_logo_image(max_width=600, max_height=150):
    """
    Obtém a imagem do logo convertida para CTkImage, 
    MANTENDO A PROPORÇÃO ORIGINAL (Aspect Ratio).
    """
    global _logo_cache, _logo_path
    
    # Determinar caminho do logo
    if _logo_path is None:
        _logo_path = resource_path("assets/logo.png")
    
    # Se já está em cache, retornar
    if _logo_cache is not None:
        return _logo_cache
    
    # Tentar carregar o logo
    try:
        if os.path.exists(_logo_path):
            pil_image = Image.open(_logo_path)
            
            # --- CÁLCULO DA PROPORÇÃO (A Correção) ---
            # Vamos redimensionar mantendo o aspeto original
            # para a imagem não ficar "esticada" ou "esborrachada"
            original_w, original_h = pil_image.size
            ratio = min(max_width / original_w, max_height / original_h)
            
            new_width = int(original_w * ratio)
            new_height = int(original_h * ratio)
            
            # Criar CTkImage com o tamanho calculado proporcionalmente
            _logo_cache = ctk.CTkImage(
                light_image=pil_image,
                dark_image=pil_image,
                size=(new_width, new_height)
            )
            return _logo_cache
    except Exception as e:
        print(f"Erro ao carregar imagem: {e}")
        pass
    
    return None


class HomePage(ctk.CTkFrame):
    """Página inicial com logo e navegação"""
    
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=["#f0f0f0", "#1a1a1a"])
        self.app = app
        self.stats_frame = None  # Frame para estatísticas
        self.setup_ui()
        self.refresh_data()  # Carregar estatísticas iniciais
    
    def setup_ui(self):
        """Configura a interface da página inicial"""
        # Container principal com padding
        main_container = ctk.CTkFrame(self, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=40, pady=40)
        
        # Logo (usar cache)
        logo_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        logo_frame.pack(pady=(0, 30))
        
        # Chama a função que calcula o tamanho certo automaticamente
        logo_photo = get_logo_image(max_width=600, max_height=150)
        
        if logo_photo:
            logo_label = ctk.CTkLabel(
                logo_frame,
                image=logo_photo,
                text="" 
            )
            logo_label.pack()
        else:
            # Placeholder se logo não existir
            logo_label = ctk.CTkLabel(
                logo_frame,
                text="INDUTECHPRO",
                font=ctk.CTkFont(size=48, weight="bold"),
                text_color=["#FF5722", "#FF5722"]
            )
            logo_label.pack()
        
        # Frame para título e botão de restauro
        title_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        title_frame.pack(fill="x", pady=(0, 30))
        
        # Mensagem de boas-vindas
        welcome_label = ctk.CTkLabel(
            title_frame,
            text="Bem-vindo ao Sistema de Gestão Indutechpro",
            font=ctk.CTkFont(size=24, weight="normal"),
            text_color=["#333333", "#ffffff"]
        )
        welcome_label.pack(side="left")
        
        # Botões de backup/export (canto superior direito)
        backup_buttons_frame = ctk.CTkFrame(title_frame, fg_color="transparent")
        backup_buttons_frame.pack(side="right")
        
        # Botão Exportar Backup Completo (Master Excel)
        export_button = ctk.CTkButton(
            backup_buttons_frame,
            text="Exportar Backup Completo",
            command=self.export_master_excel,
            font=ctk.CTkFont(size=12),
            fg_color=["#2E8B57", "#2E8B57"],
            hover_color=["#228B22", "#228B22"],
            width=200,
            height=35
        )
        export_button.pack(side="right", padx=(0, 10))
        
        # Botão Restaurar Backup
        restore_button = ctk.CTkButton(
            backup_buttons_frame,
            text="Restaurar Backup",
            command=self.restore_backup,
            font=ctk.CTkFont(size=12),
            fg_color=["#FF9800", "#FF9800"],
            hover_color=["#F57C00", "#F57C00"],
            width=150,
            height=35
        )
        restore_button.pack(side="right")
        
        # Container para estatísticas do dashboard
        self.stats_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        self.stats_frame.pack(fill="x", pady=(0, 40))
        
        # Container para os cards de navegação
        cards_container = ctk.CTkFrame(main_container, fg_color="transparent")
        cards_container.pack(fill="both", expand=True)
        
        # Configurar grid 2x2 para os cards
        cards_container.grid_columnconfigure(0, weight=1, uniform="cards")
        cards_container.grid_columnconfigure(1, weight=1, uniform="cards")
        cards_container.grid_rowconfigure(0, weight=1, uniform="cards")
        cards_container.grid_rowconfigure(1, weight=1, uniform="cards")
        
        # Top-Left: Nova Reparação
        self.create_nav_card(
            cards_container,
            "🔧 Nova Reparação",
            "Registe uma nova reparação e utilize componentes do stock",
            lambda: self.app.show_page("service"),
            row=0,
            col=0
        )
        
        # Top-Right: Gerir Stock
        self.create_nav_card(
            cards_container,
            "Gerir Stock",
            "Gerencie o inventário de componentes e peças",
            lambda: self.app.show_page("stock"),
            row=0,
            col=1
        )
        
        # Bottom-Left: Meus Clientes
        self.create_nav_card(
            cards_container,
            "Meus Clientes",
            "Gerencie a base de dados de clientes",
            lambda: self.app.show_page("client_list"),
            row=1,
            col=0
        )
        
        # Bottom-Right: Histórico
        self.create_nav_card(
            cards_container,
            "Histórico",
            "Visualize o histórico de reparações e exporte dados",
            lambda: self.app.show_page("clients"),
            row=1,
            col=1
        )
    
    def create_nav_card(self, parent, title, description, command, row, col):
        """Cria um card de navegação estilizado"""
        # Frame do card
        card = ctk.CTkFrame(
            parent,
            fg_color=["#ffffff", "#2b2b2b"],
            corner_radius=15,
            border_width=2,
            border_color=["#e0e0e0", "#404040"]
        )
        card.grid(row=row, column=col, padx=15, pady=15, sticky="nsew")
        
        # Configurar hover effect (com try/except para não quebrar event loop)
        def safe_on_enter(e):
            """Handler seguro para Enter que não bloqueia o event loop"""
            try:
                card.configure(border_color=["#FF5722", "#FF5722"])
            except Exception:
                pass  # Ignorar erros para não quebrar o event loop
        
        def safe_on_leave(e):
            """Handler seguro para Leave que não bloqueia o event loop"""
            try:
                card.configure(border_color=["#e0e0e0", "#404040"])
            except Exception:
                pass  # Ignorar erros para não quebrar o event loop
        
        card.bind("<Enter>", safe_on_enter)
        card.bind("<Leave>", safe_on_leave)
        
        # Container interno
        inner_frame = ctk.CTkFrame(card, fg_color="transparent")
        inner_frame.pack(fill="both", expand=True, padx=30, pady=30)
        
        # Título
        title_label = ctk.CTkLabel(
            inner_frame,
            text=title,
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=["#FF5722", "#FF5722"]
        )
        title_label.pack(pady=(0, 15))
        
        # Descrição
        desc_label = ctk.CTkLabel(
            inner_frame,
            text=description,
            font=ctk.CTkFont(size=14),
            text_color=["#666666", "#cccccc"],
            wraplength=200,
            justify="center"
        )
        desc_label.pack(pady=(0, 20))
        
        # Botão
        button = ctk.CTkButton(
            inner_frame,
            text="Aceder",
            command=command,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color=["#FF5722", "#FF5722"],
            hover_color=["#E64A19", "#E64A19"],
            corner_radius=8,
            height=40,
            width=150
        )
        button.pack()
    
    def refresh_data(self):
        """Atualiza as estatísticas do dashboard"""
        def db_operation():
            return self.app.db_manager.get_dashboard_stats()
        
        def callback(stats, error):
            if error:
                print(f"Erro ao carregar estatísticas: {str(error)}")
                return
            
            if not stats:
                return
            
            # Limpar estatísticas anteriores
            if self.stats_frame:
                for widget in self.stats_frame.winfo_children():
                    widget.destroy()
            
            # Criar cards de estatísticas
            stats_container = ctk.CTkFrame(self.stats_frame, fg_color="transparent")
            stats_container.pack(fill="x", padx=20)
            
            # Configurar grid
            stats_container.grid_columnconfigure(0, weight=1, uniform="stats")
            stats_container.grid_columnconfigure(1, weight=1, uniform="stats")
            stats_container.grid_columnconfigure(2, weight=1, uniform="stats")
            
            # Card 1: Vendas Totais (Apenas Pagas)
            self._create_stat_card(
                stats_container,
                "Vendas Totais",
                f"€ {stats.get('total_sales', 0.0):.2f}",
                row=0,
                col=0,
                color=["#4CAF50", "#4CAF50"]
            )
            
            # Card 2: Reparações Não Pagas (STATIC)
            pending_count = stats.get('pending_repairs', 0)
            self._create_stat_card(
                stats_container,
                "Reparações Não Pagas",
                str(pending_count),
                row=0,
                col=1,
                color=["#FF9800", "#FF9800"]
            )
            
            # Card 3: Stock Baixo (vermelho se > 0)
            low_stock_count = stats.get('low_stock_count', 0)
            stock_color = ["#F44336", "#F44336"] if low_stock_count > 0 else ["#FF9800", "#FF9800"]
            self._create_stat_card(
                stats_container,
                "Stock Baixo",
                f"{low_stock_count} artigos",
                row=0,
                col=2,
                color=stock_color
            )
        
        run_db_operation(self.app.root, db_operation, callback)
    
    def _create_stat_card(self, parent, title, value, row, col, color, clickable=False, click_command=None):
        """Cria um card de estatística"""
        card = ctk.CTkFrame(
            parent,
            fg_color=["#ffffff", "#2b2b2b"],
            corner_radius=12,
            border_width=2,
            border_color=color
        )
        card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
        
        # Se clicável, adicionar cursor pointer e bind
        if clickable and click_command:
            card.configure(cursor="hand2")
            def on_click(e):
                try:
                    click_command()
                except Exception:
                    pass
            card.bind("<Button-1>", on_click)
        
        inner_frame = ctk.CTkFrame(card, fg_color="transparent")
        inner_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Título
        title_label = ctk.CTkLabel(
            inner_frame,
            text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=["#666666", "#cccccc"]
        )
        title_label.pack(pady=(0, 10))
        
        # Valor
        value_label = ctk.CTkLabel(
            inner_frame,
            text=value,
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=color
        )
        value_label.pack()
    
    def show_pending_repairs(self):
        """Mostra popup com lista de reparações pendentes"""
        def db_operation():
            return self.app.db_manager.get_unpaid_repairs()
        
        def callback(repairs, error):
            if error:
                from tkinter import messagebox
                messagebox.showerror("Erro", f"Erro ao carregar reparações pendentes: {str(error)}")
                return
            
            # Criar popup
            popup = ctk.CTkToplevel(self.app.root)
            popup.title("Reparações Pendentes")
            popup.geometry("800x500")
            popup.transient(self.app.root)
            popup.grab_set()
            
            # Header
            header_frame = ctk.CTkFrame(popup, fg_color="transparent")
            header_frame.pack(fill="x", padx=20, pady=(20, 10))
            
            title_label = ctk.CTkLabel(
                header_frame,
                text=f"Reparações Pendentes ({len(repairs) if repairs else 0})",
                font=ctk.CTkFont(size=24, weight="bold")
            )
            title_label.pack(side="left")
            
            close_button = ctk.CTkButton(
                header_frame,
                text="✕ Fechar",
                command=popup.destroy,
                font=ctk.CTkFont(size=12),
                fg_color=["#666666", "#666666"],
                hover_color=["#555555", "#555555"],
                width=100,
                height=30
            )
            close_button.pack(side="right")
            
            # Tabela
            table_frame = ctk.CTkFrame(popup)
            table_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
            
            # Cabeçalho
            header_row = ctk.CTkFrame(table_frame, fg_color=["#FF5722", "#FF5722"])
            header_row.pack(fill="x", padx=0, pady=0)
            
            headers = ["Cliente", "Data", "Valor em Dívida"]
            widths = [300, 200, 150]
            
            for i, (header, width) in enumerate(zip(headers, widths)):
                label = ctk.CTkLabel(
                    header_row,
                    text=header,
                    font=ctk.CTkFont(size=14, weight="bold"),
                    text_color=["#ffffff", "#ffffff"],
                    width=width,
                    anchor="w" if i < len(headers) - 1 else "e"
                )
                label.pack(side="left", padx=10, pady=15)
            
            # Lista scrollável
            scrollable = ctk.CTkScrollableFrame(table_frame, fg_color=["#ffffff", "#2b2b2b"])
            scrollable.pack(fill="both", expand=True, padx=0, pady=0)
            
            if not repairs:
                no_data = ctk.CTkLabel(
                    scrollable,
                    text="Nenhuma reparação pendente",
                    font=ctk.CTkFont(size=14),
                    text_color=["#999999", "#666666"]
                )
                no_data.pack(pady=20)
            else:
                total_due = 0.0
                for repair in repairs:
                    row_frame = ctk.CTkFrame(scrollable, fg_color=["#f9f9f9", "#2b2b2b"])
                    row_frame.pack(fill="x", padx=5, pady=3)
                    
                    # Cliente
                    client_label = ctk.CTkLabel(
                        row_frame,
                        text=repair.get("client", "N/A"),
                        font=ctk.CTkFont(size=12),
                        width=300,
                        anchor="w"
                    )
                    client_label.pack(side="left", padx=10, pady=10)
                    
                    # Data
                    date_str = repair.get("date", "")
                    try:
                        from datetime import datetime
                        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                        formatted_date = dt.strftime("%d/%m/%Y")
                    except:
                        formatted_date = date_str
                    
                    date_label = ctk.CTkLabel(
                        row_frame,
                        text=formatted_date,
                        font=ctk.CTkFont(size=12),
                        width=200,
                        anchor="w"
                    )
                    date_label.pack(side="left", padx=10, pady=10)
                    
                    # Valor
                    total = float(repair.get("total", 0.0))
                    total_due += total
                    total_label = ctk.CTkLabel(
                        row_frame,
                        text=f"{total:.2f} €",
                        font=ctk.CTkFont(size=12, weight="bold"),
                        width=150,
                        anchor="e",
                        text_color=["#F44336", "#F44336"]
                    )
                    total_label.pack(side="left", padx=10, pady=10)
                
                # Total
                total_frame = ctk.CTkFrame(table_frame, fg_color=["#2b2b2b", "#1a1a1a"])
                total_frame.pack(fill="x", padx=0, pady=(10, 0))
                
                total_label = ctk.CTkLabel(
                    total_frame,
                    text=f"Total em Dívida: {total_due:.2f} €",
                    font=ctk.CTkFont(size=16, weight="bold"),
                    text_color=["#F44336", "#F44336"]
                )
                total_label.pack(padx=20, pady=15)
            
            # Centralizar popup
            popup.update_idletasks()
            x = (popup.winfo_screenwidth() // 2) - (popup.winfo_width() // 2)
            y = (popup.winfo_screenheight() // 2) - (popup.winfo_height() // 2)
            popup.geometry(f"+{x}+{y}")
        
        from ui.utils import run_db_operation
        run_db_operation(self.app.root, db_operation, callback)
    
    def restore_backup(self):
        """Restaura a base de dados a partir de um ficheiro de backup"""
        try:
            # Determinar diretório de backups
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            backups_dir = os.path.join(current_dir, "backups")
            
            # Se a pasta não existir, usar diretório atual
            if not os.path.exists(backups_dir):
                backups_dir = os.getcwd()
            
            # Abrir diálogo para selecionar ficheiro de backup
            backup_file = filedialog.askopenfilename(
                initialdir=backups_dir,
                title="Selecionar Ficheiro de Backup",
                filetypes=[("Database files", "*.db"), ("All files", "*.*")]
            )
            
            if not backup_file:
                return  # Utilizador cancelou
            
            # Validar que é um ficheiro .db
            if not backup_file.endswith('.db'):
                messagebox.showerror("Erro", "Por favor, selecione um ficheiro .db válido!")
                return
            
            # Aviso de segurança
            confirm_message = (
                "Atenção! Isto vai substituir todos os dados atuais pelos do backup selecionado.\n\n"
                f"Ficheiro: {os.path.basename(backup_file)}\n\n"
                "Esta ação é irreversível. Deseja continuar?"
            )
            
            if not messagebox.askyesno("Confirmar Restauro", confirm_message):
                return  # Utilizador cancelou
            
            # Executar restauro em background
            def db_operation():
                return self.app.db_manager.restore_backup(backup_file)
            
            def callback(success, error):
                if error:
                    messagebox.showerror("Erro", f"Erro ao restaurar backup:\n\n{str(error)}")
                    return
                
                if success:
                    messagebox.showinfo(
                        "Sucesso",
                        "Restauro concluído com sucesso!\n\n"
                        "A aplicação vai reiniciar para carregar os dados restaurados."
                    )
                    
                    # Forçar reinício da aplicação
                    # Fechar janela atual
                    self.app.root.destroy()
                    
                    # Reiniciar aplicação
                    import subprocess
                    python = sys.executable
                    script = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                        "main.py"
                    )
                    subprocess.Popen([python, script])
                    sys.exit(0)
                else:
                    messagebox.showerror("Erro", "Falha ao restaurar backup. Verifique o ficheiro selecionado.")
            
            run_db_operation(self.app.root, db_operation, callback)
        
        except Exception as e:
            messagebox.showerror("Erro", f"Erro inesperado ao restaurar backup:\n\n{str(e)}")
    
    def export_master_excel(self):
        """Exporta a base de dados completa para um ficheiro Excel Master (3 folhas)"""
        try:
            # Solicitar localização para salvar
            filename = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
                initialfile="Backup_Indutechpro.xlsx",
                title="Exportar Backup Completo (.xlsx)"
            )
            
            if not filename:
                return  # Utilizador cancelou
            
            # Verificar se o ficheiro está bloqueado
            if os.path.exists(filename):
                try:
                    test_file = open(filename, 'a')
                    test_file.close()
                except (IOError, PermissionError, OSError):
                    messagebox.showerror(
                        "Erro",
                        "O ficheiro está aberto ou não tem permissões de escrita.\n\n"
                        "Por favor, feche o ficheiro Excel se estiver aberto e tente novamente."
                    )
                    return
            
            # Executar exportação em background
            def db_operation():
                return self.app.db_manager.export_master_database(filename)
            
            def callback(success, error):
                if error:
                    messagebox.showerror("Erro", f"Erro ao exportar backup:\n\n{str(error)}")
                    return
                
                if success:
                    messagebox.showinfo(
                        "Operação Concluída",
                        f"Backup completo exportado com sucesso.\n\n"
                        f"Ficheiro: {os.path.basename(filename)}\n"
                        f"Localização: {os.path.dirname(filename)}\n\n"
                        f"O ficheiro contém 3 folhas:\n"
                        f"- Clientes\n"
                        f"- Stock\n"
                        f"- Reparacoes"
                    )
                    
                    # Tentar abrir automaticamente
                    try:
                        if os.name == 'nt':  # Windows
                            os.startfile(filename)
                        elif os.name == 'posix':  # macOS e Linux
                            import subprocess
                            subprocess.call(['open', filename])
                    except:
                        pass  # Ignorar se não conseguir abrir
                else:
                    messagebox.showerror("Erro", "Falha ao exportar backup completo!")
            
            run_db_operation(self.app.root, db_operation, callback)
        
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao exportar backup: {str(e)}")