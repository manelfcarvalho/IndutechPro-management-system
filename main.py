"""
Indutechpro - Sistema de Gestão de Reparações
Ponto de entrada principal da aplicação
"""

from ui.app import IndutechproApp


def main():
    """Função principal"""
    app = IndutechproApp()
    app.run()


if __name__ == "__main__":
    main()
