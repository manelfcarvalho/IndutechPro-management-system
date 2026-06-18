"""
Splash Screen (Tela de Carregamento)
Exibida durante a inicialização da aplicação
"""

import customtkinter as ctk
from PIL import Image
import os
from ui.utils import resource_path


class SplashScreen:
    """Tela de carregamento profissional"""
    
    def __init__(self, callback=None):
        """
        Inicializa o splash screen
        
        Args:
            callback: Função a chamar quando o splash screen terminar
        """
        # Configurar tema antes de criar a janela
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # Criar janela borderless
        self.root = ctk.CTk()
        self.root.overrideredirect(True)  # Remover barra de título
        
        # Tamanho da janela
        width = 500
        height = 400
        
        # Centralizar na tela
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.configure(fg_color=["#ffffff", "#1a1a1a"])  # Branco claro ou escuro conforme tema
        
        # Callback para quando terminar
        self.callback = callback
        
        # Variáveis de progresso
        self.progress_value = 0.0
        self.loading_steps = [
            "A inicializar sistema...",
            "A verificar base de dados...",
            "A carregar componentes...",
            "Pronto!"
        ]
        self.current_step = 0
        
        self.setup_ui()
        self.start_loading()
    
    def setup_ui(self):
        """Configura a interface do splash screen"""
        # Container principal
        main_frame = ctk.CTkFrame(
            self.root,
            fg_color="transparent"
        )
        main_frame.pack(fill="both", expand=True, padx=40, pady=40)
        
        # Logo
        logo_path = resource_path("assets/logo.png")
        
        try:
            if os.path.exists(logo_path):
                pil_image = Image.open(logo_path)
                # Redimensionar mantendo proporção
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
                    main_frame,
                    image=logo_image,
                    text=""
                )
                logo_label.pack(pady=(20, 30))
            else:
                # Placeholder se logo não existir
                logo_label = ctk.CTkLabel(
                    main_frame,
                    text="INDUTECHPRO",
                    font=ctk.CTkFont(size=48, weight="bold"),
                    text_color=["#FF5722", "#FF5722"]
                )
                logo_label.pack(pady=(20, 30))
        except Exception:
            # Fallback se houver erro
            logo_label = ctk.CTkLabel(
                main_frame,
                text="INDUTECHPRO",
                font=ctk.CTkFont(size=48, weight="bold"),
                text_color=["#FF5722", "#FF5722"]
            )
            logo_label.pack(pady=(20, 30))
        
        # Texto de carregamento
        self.loading_label = ctk.CTkLabel(
            main_frame,
            text=self.loading_steps[0],
            font=ctk.CTkFont(size=16),
            text_color=["#333333", "#cccccc"]
        )
        self.loading_label.pack(pady=(0, 20))
        
        # Barra de progresso
        self.progress_bar = ctk.CTkProgressBar(
            main_frame,
            width=400,
            height=20,
            progress_color=["#FF5722", "#FF5722"],  # Cor laranja da marca
            fg_color=["#e0e0e0", "#2b2b2b"]
        )
        self.progress_bar.pack(pady=(0, 20))
        self.progress_bar.set(0)
        
        # Versão/Info (opcional)
        version_label = ctk.CTkLabel(
            main_frame,
            text="Sistema de Gestão de Reparações",
            font=ctk.CTkFont(size=12),
            text_color=["#666666", "#999999"]
        )
        version_label.pack(pady=(10, 0))
    
    def start_loading(self):
        """Inicia a animação de carregamento"""
        self.update_progress()
    
    def update_progress(self):
        """Atualiza a barra de progresso e texto"""
        # Incrementar progresso (0 a 1.0)
        if self.progress_value < 1.0:
            # Calcular incremento baseado no número de steps
            step_duration = 1.0 / len(self.loading_steps)
            target_progress = (self.current_step + 1) * step_duration
            
            # Incremento suave
            increment = 0.02
            self.progress_value = min(self.progress_value + increment, target_progress)
            
            # Atualizar barra
            self.progress_bar.set(self.progress_value)
            
            # Verificar se mudou de step
            if self.progress_value >= target_progress and self.current_step < len(self.loading_steps) - 1:
                self.current_step += 1
                self.loading_label.configure(text=self.loading_steps[self.current_step])
            
            # Continuar animação
            self.root.after(50, self.update_progress)  # Atualizar a cada 50ms
        else:
            # Carregamento completo
            self.progress_bar.set(1.0)
            self.loading_label.configure(text="Pronto!")
            
            # Aguardar um pouco antes de fechar
            self.root.after(300, self.finish)
    
    def finish(self):
        """Finaliza o splash screen e chama o callback"""
        # Fechar splash screen
        self.root.quit()  # Sair do mainloop
        self.root.destroy()  # Destruir janela
        
        # Executar callback após fechar
        if self.callback:
            try:
                self.callback()
            except Exception:
                pass
    
    def run(self):
        """Inicia o loop do splash screen"""
        self.root.mainloop()
