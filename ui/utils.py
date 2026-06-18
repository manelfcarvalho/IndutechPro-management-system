"""
Utilitários para a interface de utilizador
Inclui threading helpers, debouncer e loading overlay
"""

import os
import sys
import threading
import time
import customtkinter as ctk
from typing import Callable, Any, Optional


def get_base_path():
    """
    Determines the root directory correctly in both scenarios:
    - When running as a frozen executable (PyInstaller)
    - When running as a raw Python script
    
    Returns:
        str: Absolute path to the base directory
    """
    # Check if running as compiled exe (PyInstaller)
    if getattr(sys, 'frozen', False):
        # Use the directory where the .exe is located
        return os.path.dirname(sys.executable)
    else:
        # Use the directory where this script is running
        # Get the directory of the main.py file (project root)
        # This file is in ui/utils.py, so we go up 2 levels to get project root
        current_file = os.path.abspath(__file__)
        ui_dir = os.path.dirname(current_file)
        project_root = os.path.dirname(ui_dir)
        return project_root


def resource_path(relative_path):
    """
    Get absolute path to resource, works for dev and for PyInstaller.
    Uses get_base_path() to determine the correct base directory.
    
    Args:
        relative_path: Path relative to the base directory (e.g., "assets/logo.png")
    
    Returns:
        str: Absolute path to the resource
    """
    base_path = get_base_path()
    return os.path.join(base_path, relative_path)


class Debouncer:
    """Classe para adiar execução de funções (debounce)"""
    def __init__(self, func: Callable, master, delay: int = 300):
        self.func = func
        self.master = master
        self.delay = delay
        self.after_id: Optional[str] = None
        self._lock = threading.Lock()  # Thread-safe debouncer
    
    def __call__(self, *args, **kwargs):
        """Chama a função após delay, cancelando chamadas anteriores"""
        try:
            with self._lock:
                if self.after_id:
                    try:
                        self.master.after_cancel(self.after_id)
                    except:
                        pass  # Ignorar se já foi cancelado
                
                # Agendar nova chamada
                self.after_id = self.master.after(
                    self.delay, 
                    lambda: self._safe_call(*args, **kwargs)
                )
        except Exception:
            # Se falhar, tentar chamar diretamente (fallback)
            try:
                self._safe_call(*args, **kwargs)
            except:
                pass
    
    def _safe_call(self, *args, **kwargs):
        """Chama a função de forma segura com try/except"""
        try:
            self.func(*args, **kwargs)
        except Exception:
            pass  # Ignorar erros para não quebrar o event loop


def run_db_operation(root, db_func: Callable, ui_callback: Callable, *args, **kwargs):
    """
    Executa uma operação de base de dados em background thread
    Garante que callbacks UI são executados no main thread
    
    Args:
        root: Root window para agendar callbacks no main thread
        db_func: Função da base de dados a executar
        ui_callback: Callback para atualizar UI (recebe resultado, erro)
        *args, **kwargs: Argumentos para db_func
    """
    def worker():
        try:
            result = db_func(*args, **kwargs)
            # Agendar callback no main thread de forma segura
            def safe_callback():
                try:
                    ui_callback(result, None)
                except Exception as e:
                    # Log error but don't crash
                    error_msg = str(e)  # Capture as string immediately
                    print(f"Error in UI callback: {error_msg}")
            
            root.after(0, safe_callback)
        except Exception as e:
            # Capture exception message as string immediately (before closure)
            error_msg = str(e)
            error_obj = e  # Keep reference to exception object for callback
            
            # Agendar callback de erro no main thread
            def error_callback():
                try:
                    ui_callback(None, error_obj)
                except Exception:
                    # Se callback falhar, apenas log
                    print(f"Error in error callback: {error_msg}")
            
            root.after(0, error_callback)
    
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread


class LoadingOverlay:
    """
    Overlay de carregamento profissional
    Mostra um indicador visual enquanto operações pesadas executam
    """
    
    def __init__(self, parent, message: str = "A carregar..."):
        """
        Inicializa o overlay de carregamento
        
        Args:
            parent: Widget pai onde o overlay será exibido
            message: Mensagem a mostrar
        """
        self.parent = parent
        self.message = message
        self.overlay_frame = None
        self.progress_bar = None
        self.label = None
        self._is_visible = False
    
    def show(self, message: Optional[str] = None):
        """
        Mostra o overlay de carregamento
        
        Args:
            message: Mensagem opcional (usa a padrão se None)
        """
        if self._is_visible:
            return  # Já está visível
        
        if message:
            self.message = message
        
        # Criar frame overlay (semi-transparente)
        # Nota: CustomTkinter não suporta rgba diretamente, usar cor sólida escura
        self.overlay_frame = ctk.CTkFrame(
            self.parent,
            fg_color=["#000000", "#000000"],  # Preto sólido
            corner_radius=0  # Sem cantos arredondados para cobrir tudo
        )
        
        # Cobrir todo o parent
        self.overlay_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        
        # Container para conteúdo centralizado
        content_container = ctk.CTkFrame(
            self.overlay_frame,
            fg_color="transparent"
        )
        content_container.place(relx=0.5, rely=0.5, anchor="center")
        
        # Container interno (card branco/escuro)
        inner_frame = ctk.CTkFrame(
            content_container,
            fg_color=["#ffffff", "#2b2b2b"],
            corner_radius=10
        )
        inner_frame.pack(padx=40, pady=40)
        
        # Label de mensagem
        self.label = ctk.CTkLabel(
            inner_frame,
            text=self.message,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=["#333333", "#ffffff"]
        )
        self.label.pack(pady=(30, 20), padx=40)
        
        # Barra de progresso indeterminada
        self.progress_bar = ctk.CTkProgressBar(
            inner_frame,
            width=300,
            height=6,
            progress_color=["#FF5722", "#FF5722"],
            fg_color=["#e0e0e0", "#444444"],
            mode="indeterminate"
        )
        self.progress_bar.pack(pady=(0, 30), padx=40)
        self.progress_bar.start()  # Iniciar animação
        
        self.overlay_frame.lift()  # Trazer para frente
        
        self._is_visible = True
        
        # Forçar atualização visual
        self.parent.update_idletasks()
    
    def hide(self):
        """Esconde o overlay de carregamento"""
        if not self._is_visible or not self.overlay_frame:
            return
        
        try:
            if self.progress_bar:
                self.progress_bar.stop()
            
            if self.overlay_frame:
                self.overlay_frame.destroy()
                self.overlay_frame = None
                self.progress_bar = None
                self.label = None
            
            self._is_visible = False
            
            # Forçar atualização visual
            self.parent.update_idletasks()
        except Exception:
            # Ignorar erros ao esconder
            self._is_visible = False
    
    def update_message(self, message: str):
        """
        Atualiza a mensagem do overlay
        
        Args:
            message: Nova mensagem
        """
        if self.label and self._is_visible:
            self.label.configure(text=message)
            self.parent.update_idletasks()


def run_db_operation_with_loading(
    root, 
    parent_widget, 
    db_func: Callable, 
    ui_callback: Callable,
    loading_message: str = "A carregar...",
    min_delay: float = 0.6,
    *args, 
    **kwargs
):
    """
    Executa uma operação de base de dados com overlay de carregamento
    Inclui delay artificial para feedback profissional
    
    Args:
        root: Root window para agendar callbacks no main thread
        parent_widget: Widget onde mostrar o overlay
        db_func: Função da base de dados a executar
        ui_callback: Callback para atualizar UI (recebe resultado, erro)
        loading_message: Mensagem a mostrar no overlay
        min_delay: Delay mínimo em segundos (padrão 0.6s)
        *args, **kwargs: Argumentos para db_func
    """
    # Criar overlay
    overlay = LoadingOverlay(parent_widget, loading_message)
    
    def worker():
        try:
            # Mostrar overlay no main thread
            root.after(0, overlay.show)
            
            # Pequeno delay para garantir que overlay aparece
            time.sleep(0.1)
            
            # Pequeno delay para garantir que overlay aparece
            time.sleep(0.1)
            
            # Executar operação de base de dados
            start_time = time.time()
            result = db_func(*args, **kwargs)
            elapsed = time.time() - start_time
            
            # Garantir delay mínimo para feedback profissional (0.5s como solicitado)
            if elapsed < min_delay:
                time.sleep(min_delay - elapsed)
            
            # Esconder overlay e executar callback no main thread
            def finish():
                try:
                    overlay.hide()
                    ui_callback(result, None)
                except Exception as e:
                    overlay.hide()
                    error_msg = str(e)  # Capture as string immediately
                    print(f"Error in UI callback: {error_msg}")
                    ui_callback(None, e)
            
            root.after(0, finish)
        except Exception as e:
            # Capture exception message as string immediately (before closure)
            error_msg = str(e)
            error_obj = e  # Keep reference to exception object for callback
            
            # Esconder overlay e executar callback de erro
            def error_finish():
                try:
                    overlay.hide()
                    ui_callback(None, error_obj)
                except Exception:
                    overlay.hide()
                    print(f"Error in error callback: {error_msg}")
            
            root.after(0, error_finish)
    
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread, overlay
