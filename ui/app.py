"""
Controlador Principal da Aplicação Indutechpro
Gerencia a janela principal e navegação entre páginas
"""

import customtkinter as ctk
import threading
import time
from PIL import Image
import os
from database.db_manager import DatabaseManager
from ui.utils import resource_path
from ui.pages.home_page import HomePage
from ui.pages.stock_page import StockPage
from ui.pages.service_page import ServicePage
from ui.pages.clients_page import ClientsPage
from ui.pages.client_list_page import ClientListPage


class IndutechproApp:
    """Classe principal da aplicação"""
    
    def __init__(self):
        """Inicializa a aplicação"""
        # Configurar tema CustomTkinter
        ctk.set_appearance_mode("dark")  # Modo escuro
        ctk.set_default_color_theme("blue")  # Tema base azul
        
        # Cores personalizadas para Indutechpro (Laranja e Azul Escuro)
        # Sobrescrever cores padrão
        ctk.set_widget_scaling(1.0)
        
        # Criar janela principal
        self.root = ctk.CTk()
        self.root.title("Indutechpro - Sistema de Gestão")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)
        
        # Mac-specific optimizations: Prevent aggressive redraws on focus
        try:
            # Disable automatic updates on focus events
            self.root.update_idletasks()
            # Prevent window from redrawing aggressively on focus gain (Mac)
            # This reduces lag when Alt+Tab'ing back into the app
            self.root.configure(highlightthickness=0)
        except:
            pass
        
        # Fechar conexão ao sair
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Track current page to prevent unnecessary refreshes
        self.current_page_name = None
        self._prevent_focus_refresh = True  # Prevent refresh on focus events
        
        # Bind focus events but prevent automatic refresh
        self.root.bind("<FocusIn>", self._on_focus_in)
        self.root.bind("<Map>", self._on_map)
        
        # Container para páginas (criar primeiro para splash overlay)
        self.container = ctk.CTkFrame(self.root, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Criar splash screen como Frame overlay
        self.splash_frame = self._create_splash_overlay()
        
        # Dicionário para armazenar páginas
        self.pages = {}
        
        # Inicializar em background thread
        self._init_app_async()
    
    def _create_splash_overlay(self):
        """Cria o splash screen como Frame overlay"""
        splash_frame = ctk.CTkFrame(
            self.root,
            fg_color=["#1a1a1a", "#1a1a1a"],
            corner_radius=0
        )
        splash_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        splash_frame.lift()
        
        # Container centralizado
        center_frame = ctk.CTkFrame(splash_frame, fg_color="transparent")
        center_frame.place(relx=0.5, rely=0.5, anchor="center")
        
        # Logo
        logo_path = resource_path("assets/logo.png")
        
        try:
            if os.path.exists(logo_path):
                pil_image = Image.open(logo_path)
                original_w, original_h = pil_image.size
                max_width, max_height = 300, 200
                ratio = min(max_width / original_w, max_height / original_h)
                new_width = int(original_w * ratio)
                new_height = int(original_h * ratio)
                
                logo_image = ctk.CTkImage(
                    light_image=pil_image,
                    dark_image=pil_image,
                    size=(new_width, new_height)
                )
                
                logo_label = ctk.CTkLabel(
                    center_frame,
                    image=logo_image,
                    text=""
                )
                logo_label.pack(pady=(20, 30))
            else:
                logo_label = ctk.CTkLabel(
                    center_frame,
                    text="INDUTECHPRO",
                    font=ctk.CTkFont(size=48, weight="bold"),
                    text_color=["#FF5722", "#FF5722"]
                )
                logo_label.pack(pady=(20, 30))
        except Exception:
            logo_label = ctk.CTkLabel(
                center_frame,
                text="INDUTECHPRO",
                font=ctk.CTkFont(size=48, weight="bold"),
                text_color=["#FF5722", "#FF5722"]
            )
            logo_label.pack(pady=(20, 30))
        
        # Texto de carregamento
        self.splash_label = ctk.CTkLabel(
            center_frame,
            text="A inicializar sistema...",
            font=ctk.CTkFont(size=16),
            text_color=["#cccccc", "#cccccc"]
        )
        self.splash_label.pack(pady=(0, 20))
        
        # Barra de progresso
        self.splash_progress = ctk.CTkProgressBar(
            center_frame,
            width=400,
            height=20,
            progress_color=["#FF5722", "#FF5722"],
            fg_color=["#2b2b2b", "#2b2b2b"]
        )
        self.splash_progress.pack(pady=(0, 20))
        self.splash_progress.set(0)
        
        # Versão/Info
        version_label = ctk.CTkLabel(
            center_frame,
            text="Sistema de Gestão de Reparações",
            font=ctk.CTkFont(size=12),
            text_color=["#999999", "#999999"]
        )
        version_label.pack(pady=(10, 0))
        
        return splash_frame
    
    def _init_app_async(self):
        """Inicializa aplicação em background thread"""
        def init_worker():
            loading_steps = [
                "A inicializar sistema...",
                "A verificar base de dados...",
                "A carregar componentes...",
                "Pronto!"
            ]
            
            for i, step in enumerate(loading_steps):
                # Atualizar UI no main thread
                self.root.after(0, lambda s=step, p=(i+1)/len(loading_steps): self._update_splash(s, p))
                time.sleep(0.6)  # Delay profissional
            
            # Finalizar inicialização
            self.root.after(0, self._finish_init)
        
        thread = threading.Thread(target=init_worker, daemon=True)
        thread.start()
    
    def _update_splash(self, message: str, progress: float):
        """Atualiza splash screen no main thread"""
        try:
            if hasattr(self, 'splash_label'):
                self.splash_label.configure(text=message)
            if hasattr(self, 'splash_progress'):
                self.splash_progress.set(progress)
            self.root.update_idletasks()
        except:
            pass
    
    def _finish_init(self):
        """Finaliza inicialização e remove splash"""
        try:
            # Inicializar base de dados
            self.db_manager = DatabaseManager()
            
            # Criar todas as páginas
            self.create_pages()
            
            # Remover splash overlay
            if hasattr(self, 'splash_frame'):
                self.splash_frame.destroy()
            
            # Mostrar página inicial (Home)
            self.show_page("home", force_refresh=True)
        except Exception as e:
            # Se houver erro, ainda assim remover splash
            if hasattr(self, 'splash_frame'):
                self.splash_frame.destroy()
            raise e
    
    def create_pages(self):
        """Cria todas as páginas da aplicação"""
        self.pages["home"] = HomePage(self.container, self)
        self.pages["stock"] = StockPage(self.container, self)
        self.pages["service"] = ServicePage(self.container, self)
        self.pages["clients"] = ClientsPage(self.container, self)
        self.pages["client_list"] = ClientListPage(self.container, self)
    
    def show_page(self, page_name: str, force_refresh: bool = False):
        """
        Mostra uma página específica
        
        Args:
            page_name: Nome da página ("home", "stock", "service", "clients")
            force_refresh: Se True, força refresh mesmo se página já está visível
        """
        if page_name not in self.pages:
            return
        
        target_page = self.pages[page_name]
        
        # Se já é a página atual e não é refresh forçado, não fazer nada
        if page_name == self.current_page_name and not force_refresh:
            return
        
        # Se a página já está visível mas é uma mudança de página, apenas esconder outras
        is_already_visible = False
        try:
            if target_page.winfo_viewable():
                is_already_visible = True
        except:
            pass
        
        # Esconder todas as páginas
        for page in self.pages.values():
            page.pack_forget()
        
        # Mostrar página solicitada
        target_page.pack(fill="both", expand=True)
        self.current_page_name = page_name
        
        # Apenas atualizar dados se:
        # 1. É um refresh forçado (primeira vez ou ação do utilizador)
        # 2. A página não estava visível antes (mudança de página)
        # 3. ServicePage sempre precisa de refresh para mostrar componentes atualizados
        # 4. HomePage sempre atualiza estatísticas quando mostrada
        if force_refresh or not is_already_visible or page_name == "service" or page_name == "home":
            if hasattr(target_page, "refresh_data"):
                # ServicePage precisa sempre de dados frescos quando navega para ela
                if page_name == "service":
                    target_page.refresh_data(force=True)
                else:
                    target_page.refresh_data()
    
    def _on_focus_in(self, _):
        """
        Handler para quando a janela ganha foco
        NÃO atualiza dados automaticamente para evitar lag
        """
        try:
            # Apenas atualizar o display, não recarregar dados
            if self._prevent_focus_refresh:
                return
            # Se precisar de atualizar no futuro, fazer aqui de forma otimizada
        except Exception:
            pass  # Ignorar erros para não quebrar o event loop
    
    def _on_map(self, _):
        """
        Handler para quando a janela é mapeada (mostrada)
        NÃO atualiza dados automaticamente
        """
        try:
            # Não fazer nada - evita refresh desnecessário
            pass
        except Exception:
            pass  # Ignorar erros para não quebrar o event loop
    
    def on_closing(self):
        """Limpa recursos ao fechar a aplicação"""
        if hasattr(self, 'db_manager'):
            # Criar backup automático antes de fechar
            try:
                self.db_manager.create_backup()
                print("Backup criado com sucesso")
            except Exception as e:
                print(f"Erro ao criar backup: {str(e)}")
            
            # Fechar conexão
            self.db_manager.close_connection()
        self.root.destroy()
    
    def run(self):
        """Inicia o loop principal da aplicação"""
        # Mac optimization: Reduce update frequency
        try:
            # Set update interval to be less aggressive
            self.root.after(100, lambda: None)  # Initial delay
        except:
            pass
        self.root.mainloop()
