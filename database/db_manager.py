"""
Gestor de Base de Dados SQLite para Indutechpro
Gerencia conexões, tabelas e operações CRUD com pool de conexões
"""

import sqlite3
import os
import shutil
import threading
import re
import sys
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from contextlib import contextmanager
import pandas as pd


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
        # This file is in database/db_manager.py, so we go up 1 level to get project root
        current_file = os.path.abspath(__file__)
        database_dir = os.path.dirname(current_file)
        project_root = os.path.dirname(database_dir)
        return project_root

# ========== MAPEAMENTO DE COLUNAS PARA EXPORTAÇÃO (DB -> Excel Português) ==========

CLIENTS_MAP = {
    'id': 'ID',
    'name': 'Nome',
    'phone': 'Telemóvel',
    'nif': 'NIF',
    'address': 'Morada'
}

STOCK_MAP = {
    'id': 'ID',
    'code': 'Código',
    'name': 'Designação',  # 'name' in DB becomes 'Designação' in Excel
    'family': 'Família',
    'preco_compra': 'Preço Compra',
    'qty': 'Quantidade',
    'price': 'Preço Venda',
    'supplier': 'Fornecedor',
    'supplier_ref': 'Ref. Fornecedor'
}

REPAIRS_MAP = {
    'id': 'ID',
    'date': 'Data',
    'client': 'Cliente',
    'description': 'Descrição',
    'used_parts': 'Peças Utilizadas',
    'total': 'Total s/ IVA',
    'payment_status': 'Estado Pagamento',
    'hours_worked': 'Horas Trabalho',
    'client_id': 'ID Cliente',
    'device_imei': 'IMEI',
    'repair_status': 'Estado',
    'electricity_hours': 'Horas Eletricidade',
    'package_weight': 'Peso Pacote',
    'transport_cost': 'Custo Transporte',
    'labor_type': 'Tipo Mão de Obra',
    'warranty_number': 'Nº Garantia',
    'horas_teste': 'Horas Teste',
    'preco_hora_teste': 'Preço Hora Teste',
    'problem_summary': 'Tipo de equipamento'
}

# Margem padrão para cálculo automático de preço de venda (30%)
DEFAULT_MARGIN = 1.30

# Colunas que devem ser formatadas como moeda (€) no Excel
MONEY_COLUMNS = ['Preço Compra', 'Preço Venda', 'Total', 'Total s/ IVA', 'Valor', 'Custo']


class DatabaseManager:
    """Classe para gerenciar a base de dados SQLite com pool de conexões"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, db_path: str = "database/indutechpro.db"):
        """Singleton pattern para garantir uma única instância"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DatabaseManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, db_path: str = "database/indutechpro.db"):
        """
        Inicializa o gestor de base de dados
        
        Args:
            db_path: Caminho para o ficheiro da base de dados (relativo ou absoluto)
        """
        # Evitar reinicialização se já foi inicializado
        if hasattr(self, '_initialized'):
            return
        
        # Se db_path é relativo, converter para absoluto usando get_base_path()
        if not os.path.isabs(db_path):
            base_path = get_base_path()
            db_path = os.path.join(base_path, db_path)
        
        # Garantir que o diretório existe
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._connection = None
        self._connection_lock = threading.RLock()
        self._initialized = True
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """
        Context manager para obter conexão com a base de dados
        Garante que a conexão é fechada corretamente
        """
        conn = None
        try:
            # Usar conexão persistente para melhor performance
            with self._connection_lock:
                if self._connection is None:
                    self._connection = sqlite3.connect(
                        self.db_path,
                        check_same_thread=False,  # Permitir uso em múltiplas threads
                        timeout=10.0
                    )
                    self._connection.row_factory = sqlite3.Row
                    # Otimizações SQLite
                    self._connection.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
                    self._connection.execute("PRAGMA synchronous=NORMAL")  # Balance performance/safety
                    self._connection.execute("PRAGMA cache_size=10000")  # 10MB cache
                    self._connection.execute("PRAGMA temp_store=MEMORY")
                conn = self._connection
                yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
    
    def close_connection(self):
        """Fecha a conexão persistente"""
        with self._connection_lock:
            if self._connection:
                self._connection.close()
                self._connection = None
    
    def init_database(self):
        """Inicializa as tabelas da base de dados"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Tabela de componentes (stock)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS components (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    price REAL NOT NULL,
                    qty INTEGER NOT NULL DEFAULT 0
                )
            """)
            
            # Migração: Adicionar colunas de imagem e datasheet
            try:
                cursor.execute("ALTER TABLE components ADD COLUMN image_path TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                pass
            
            try:
                cursor.execute("ALTER TABLE components ADD COLUMN datasheet_path TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                pass
            
            # Migração: Renomear datasheet_url para datasheet_path se existir
            try:
                cursor.execute("ALTER TABLE components RENAME COLUMN datasheet_url TO datasheet_path")
                conn.commit()
            except sqlite3.OperationalError:
                pass
            
            # Migração: Adicionar coluna family (categoria)
            try:
                cursor.execute("ALTER TABLE components ADD COLUMN family TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                pass  # Coluna já existe
            
            # Migração: Adicionar colunas de fornecedor
            try:
                cursor.execute("ALTER TABLE components ADD COLUMN supplier TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                pass  # Coluna já existe
            
            try:
                cursor.execute("ALTER TABLE components ADD COLUMN supplier_ref TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                pass  # Coluna já existe

            # Migração: renomear coluna custo -> preco_compra (ou criar se não existir nenhuma)
            self._rename_custo_to_preco_compra(conn)
            
            # Criar índices para melhor performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_components_code ON components(code)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_components_name ON components(name)
            """)
            
            # Tabela de configurações
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            
            # Tabela de clientes (CRM)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    phone TEXT UNIQUE NOT NULL,
                    nif TEXT,
                    address TEXT
                )
            """)
            
            # Índices para clientes
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_clients_phone ON clients(phone)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_clients_name ON clients(name)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_clients_nif ON clients(nif)
            """)
            
            # Tabela de reparações
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS repairs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client TEXT NOT NULL,
                    description TEXT NOT NULL,
                    used_parts TEXT,
                    total REAL NOT NULL,
                    date TEXT NOT NULL,
                    payment_status TEXT NOT NULL DEFAULT 'Pendente'
                )
            """)
            
            # Migração: Adicionar coluna payment_status se não existir (para tabelas antigas)
            try:
                cursor.execute("ALTER TABLE repairs ADD COLUMN payment_status TEXT NOT NULL DEFAULT 'Pendente'")
                conn.commit()
            except sqlite3.OperationalError:
                # Coluna já existe, ignorar erro
                pass
            
            # Migração: Adicionar coluna hours_worked se não existir
            try:
                cursor.execute("ALTER TABLE repairs ADD COLUMN hours_worked REAL DEFAULT 1.0")
                conn.commit()
            except sqlite3.OperationalError:
                # Coluna já existe, ignorar erro
                pass
            
            # Migração: Adicionar coluna problem_summary se não existir
            try:
                cursor.execute("ALTER TABLE repairs ADD COLUMN problem_summary TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                # Coluna já existe, ignorar erro
                pass
            
            # Migração: Adicionar coluna client_id se não existir
            try:
                cursor.execute("ALTER TABLE repairs ADD COLUMN client_id INTEGER")
                conn.commit()
            except sqlite3.OperationalError:
                # Coluna já existe, ignorar erro
                pass
            
            # Migração: Adicionar coluna device_imei se não existir
            try:
                cursor.execute("ALTER TABLE repairs ADD COLUMN device_imei TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                # Coluna já existe, ignorar erro
                pass
            
            # Migração: Adicionar coluna repair_status se não existir
            try:
                cursor.execute("ALTER TABLE repairs ADD COLUMN repair_status TEXT DEFAULT 'Em Análise'")
                conn.commit()
                # Atualizar registos existentes para terem o valor padrão
                cursor.execute("UPDATE repairs SET repair_status = 'Em Análise' WHERE repair_status IS NULL")
                conn.commit()
            except sqlite3.OperationalError:
                # Coluna já existe, ignorar erro
                pass
            
            # Migração: Adicionar colunas de custos adicionais
            try:
                cursor.execute("ALTER TABLE repairs ADD COLUMN electricity_hours REAL DEFAULT 0.0")
                conn.commit()
            except sqlite3.OperationalError:
                pass
            
            try:
                cursor.execute("ALTER TABLE repairs ADD COLUMN package_weight REAL DEFAULT 0.0")
                conn.commit()
            except sqlite3.OperationalError:
                pass
            
            try:
                cursor.execute("ALTER TABLE repairs ADD COLUMN transport_cost REAL DEFAULT 0.0")
                conn.commit()
            except sqlite3.OperationalError:
                pass
            
            # Migração: Adicionar coluna labor_type se não existir
            try:
                cursor.execute("ALTER TABLE repairs ADD COLUMN labor_type TEXT DEFAULT 'labor1'")
                conn.commit()
                # Atualizar registos existentes para terem o valor padrão
                cursor.execute("UPDATE repairs SET labor_type = 'labor1' WHERE labor_type IS NULL")
                conn.commit()
            except sqlite3.OperationalError:
                pass
            
            # Migração: Adicionar coluna warranty_number se não existir
            try:
                cursor.execute("ALTER TABLE repairs ADD COLUMN warranty_number TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                pass
            
            # Migração: Adicionar colunas de testes/diagnóstico
            try:
                cursor.execute("ALTER TABLE repairs ADD COLUMN horas_teste REAL DEFAULT 0.0")
                conn.commit()
            except sqlite3.OperationalError:
                pass
            
            try:
                cursor.execute("ALTER TABLE repairs ADD COLUMN preco_hora_teste REAL DEFAULT 0.0")
                conn.commit()
            except sqlite3.OperationalError:
                pass

            # Índices para reparações (melhorar pesquisas e filtros)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_repairs_client_id ON repairs(client_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_repairs_client ON repairs(client)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_repairs_device_imei ON repairs(device_imei)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_repairs_repair_status ON repairs(repair_status)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_repairs_payment_status ON repairs(payment_status)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_repairs_date ON repairs(date)
            """)
            
            # Migração: Converter hourly_labor_rate para os 3 novos campos
            # Verificar se já existe hourly_labor_rate (formato antigo)
            cursor.execute("SELECT value FROM settings WHERE key = 'hourly_labor_rate'")
            old_rate_row = cursor.fetchone()
            
            if old_rate_row:
                # Migrar valor antigo para labor_rate_1
                old_rate = old_rate_row[0] if isinstance(old_rate_row, tuple) else old_rate_row["value"]
                try:
                    old_rate_float = float(old_rate)
                except:
                    old_rate_float = 30.0
                
                # Verificar se os novos campos já existem
                cursor.execute("SELECT value FROM settings WHERE key = 'labor_rate_1'")
                if not cursor.fetchone():
                    # Criar os 3 novos campos com valores padrão
                    cursor.execute("INSERT INTO settings (key, value) VALUES ('labor_rate_1', ?)", (str(old_rate_float),))
                    cursor.execute("INSERT INTO settings (key, value) VALUES ('labor_rate_2', '45.0')")
                    cursor.execute("INSERT INTO settings (key, value) VALUES ('placas_price', '50.0')")
                    conn.commit()
            else:
                # Inicializar taxas padrão se não existirem
                cursor.execute("SELECT value FROM settings WHERE key = 'labor_rate_1'")
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO settings (key, value) VALUES ('labor_rate_1', '30.0')")
                    cursor.execute("INSERT INTO settings (key, value) VALUES ('labor_rate_2', '45.0')")
                    cursor.execute("INSERT INTO settings (key, value) VALUES ('placas_price', '50.0')")
                    conn.commit()
            
            cursor.execute("SELECT value FROM settings WHERE key = 'electricity_rate'")
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO settings (key, value) VALUES ('electricity_rate', '0.50')"
                )
                conn.commit()

            cursor.execute("SELECT value FROM settings WHERE key = 'transport_rules'")
            if not cursor.fetchone():
                # Regras padrão: até 2kg = 5€, até 5kg = 10€
                default_rules = [{"max_weight": 2.0, "price": 5.0}, {"max_weight": 5.0, "price": 10.0}]
                import json
                cursor.execute(
                    "INSERT INTO settings (key, value) VALUES ('transport_rules', ?)",
                    (json.dumps(default_rules),)
                )
                conn.commit()
            
            # Criar índices para melhor performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_repairs_client ON repairs(client)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_repairs_date ON repairs(date)
            """)
            
            conn.commit()

    def _rename_custo_to_preco_compra(self, conn: sqlite3.Connection) -> None:
        """
        Migra a coluna 'custo' para 'preco_compra' na tabela components.
        - Se existir 'custo' e não existir 'preco_compra', faz RENAME COLUMN.
        - Se nenhuma das duas existir (bases novas), cria 'preco_compra'.
        """
        try:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(components)")
            cols = [row[1] for row in cursor.fetchall()]

            has_custo = 'custo' in cols
            has_preco_compra = 'preco_compra' in cols

            if has_custo and not has_preco_compra:
                cursor.execute("ALTER TABLE components RENAME COLUMN custo TO preco_compra")
                conn.commit()
            elif not has_custo and not has_preco_compra:
                cursor.execute("ALTER TABLE components ADD COLUMN preco_compra REAL DEFAULT 0.0")
                conn.commit()
        except Exception as e:
            # Não falhar a inicialização da BD por causa da migração
            print(f"Aviso migração custo->preco_compra: {e}")
    
    # ========== OPERAÇÕES COM COMPONENTES ==========
    
    def add_component(
        self,
        code: str,
        name: str,
        price: float,
        qty: int,
        image_path: Optional[str] = None,
        datasheet_path: Optional[str] = None,
        family: Optional[str] = None,
        supplier: Optional[str] = None,
        supplier_ref: Optional[str] = None,
        preco_compra: Optional[float] = None,
    ) -> bool:
        """
        Adiciona um novo componente ao stock
        
        Args:
            code: Código do componente
            name: Nome do componente
            price: Preço de venda
            qty: Quantidade em stock
            image_path: Caminho relativo para a imagem (opcional)
            datasheet_path: Caminho relativo para o PDF do datasheet (opcional)
            family: Família/Categoria do componente (opcional)
            supplier: Fornecedor do componente (opcional)
            supplier_ref: Referência do fornecedor (opcional)
        
        Returns:
            True se sucesso, False se código já existe
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO components (
                        code,
                        name,
                        price,
                        qty,
                        image_path,
                        datasheet_path,
                        family,
                        supplier,
                        supplier_ref,
                        preco_compra
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        code,
                        name,
                        price,
                        qty,
                        image_path,
                        datasheet_path,
                        family,
                        supplier,
                        supplier_ref,
                        preco_compra if preco_compra is not None else 0.0,
                    ),
                )
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False
    
    def get_all_components(self) -> List[Dict]:
        """Retorna todos os componentes"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM components ORDER BY name")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_components_paginated(self, limit: int = 50, offset: int = 0) -> List[Dict]:
        """
        Retorna uma página de componentes para paginação no ecrã de stock.
        
        Args:
            limit: Número máximo de registos a devolver.
            offset: Número de registos a saltar (para a página atual).
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM components ORDER BY name LIMIT ? OFFSET ?",
                (limit, offset)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_components_count(self) -> int:
        """
        Retorna o número total de componentes (para calcular o nº de páginas).
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM components")
            row = cursor.fetchone()
            return row[0] if row else 0
    
    def search_components(self, search_term: str) -> List[Dict]:
        """
        Pesquisa componentes por código, nome ou família
        
        Args:
            search_term: Termo de pesquisa
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            search_pattern = f"%{search_term}%"
            cursor.execute(
                "SELECT * FROM components WHERE code LIKE ? OR name LIKE ? OR family LIKE ? ORDER BY name",
                (search_pattern, search_pattern, search_pattern)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def search_stock_smart(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Pesquisa otimizada para a página de Stock.
        
        - Se query estiver vazia, retorna lista vazia (não carrega toda a tabela).
        - Caso contrário, faz LIKE em código e nome (\"contains\" case-insensitive)
          e limita o número de resultados.
        """
        if not query:
            return []
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Contém em qualquer posição + case-insensitive
            pattern = f"%{query}%"
            cursor.execute(
                """
                SELECT * FROM components
                WHERE LOWER(code) LIKE LOWER(?) OR LOWER(name) LIKE LOWER(?)
                ORDER BY name
                LIMIT ?
                """,
                (pattern, pattern, limit)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_component_by_id(self, component_id: int) -> Optional[Dict]:
        """Retorna um componente pelo ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM components WHERE id = ?", (component_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_component_by_code(self, code: str) -> Optional[Dict]:
        """Retorna um componente pelo código"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM components WHERE code = ?", (code,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def _parse_used_parts(self, used_parts_str: str, valid_codes: Optional[List[str]] = None) -> List[tuple]:
        """
        Parse used_parts string para extrair (id, qty) tuples ou (code, qty) para compatibilidade
        
        Suporta dois formatos:
        - Novo formato: "ID:QTY,ID:QTY" (preferido, evita problemas com caracteres especiais)
        - Formato antigo: "Code (Qty), Code (Qty)" (para compatibilidade com dados existentes)
        
        Args:
            used_parts_str: String no formato "ID:QTY,ID:QTY" ou "Code (Qty), Code (Qty)"
            valid_codes: Lista opcional de códigos válidos para greedy matching (formato antigo)
        
        Returns:
            Lista de tuplas (id_or_code, qty) onde:
            - Se formato novo: id_or_code é int (component ID)
            - Se formato antigo: id_or_code é str (component code)
            - qty é sempre int
        """
        if not used_parts_str or str(used_parts_str).strip() == "" or str(used_parts_str).strip() == "Nenhum":
            return []
        
        components = []
        parts_str = str(used_parts_str).strip()
        
        # Detectar formato: novo (ID:QTY) ou antigo (Code (Qty))
        # Se contém ":" e não contém "(", assume formato novo
        if ":" in parts_str and "(" not in parts_str:
            # Novo formato: "ID:QTY,ID:QTY"
            parts_list = parts_str.split(",")
            for part_str in parts_list:
                part_str = part_str.strip()
                if not part_str:
                    continue
                
                # Formato: "ID:QTY"
                if ":" in part_str:
                    try:
                        comp_id_str, qty_str = part_str.split(":", 1)
                        comp_id = int(comp_id_str.strip())
                        qty = int(qty_str.strip())
                        components.append((comp_id, qty))
                    except (ValueError, AttributeError):
                        # Se não conseguir converter, ignorar
                        continue
                else:
                    # Formato inválido, ignorar
                    continue
        else:
            # Formato antigo: "Code (Qty), Code (Qty)" - para compatibilidade
            # Usar greedy matching se valid_codes for fornecido
            if valid_codes:
                # Greedy matching: tentar encontrar o código mais longo que corresponde
                # Ordenar códigos por tamanho (mais longo primeiro) para greedy matching
                sorted_codes = sorted(valid_codes, key=len, reverse=True)
                
                # Processar string caractere por caractere, tentando encontrar matches
                remaining = parts_str
                while remaining:
                    remaining = remaining.strip()
                    if not remaining:
                        break
                    
                    # Tentar encontrar um padrão "Code (Qty)" começando do início
                    best_match = None
                    best_code = None
                    best_qty = 1
                    
                    # Tentar cada código válido (do mais longo para o mais curto)
                    for code in sorted_codes:
                        # Escapar caracteres especiais do código para regex
                        escaped_code = re.escape(code)
                        # Padrão: código seguido de espaços opcionais, depois (Qty)
                        pattern = rf"^{escaped_code}\s*\((\d+)x?\)"
                        match = re.match(pattern, remaining)
                        if match:
                            # Encontrou match, usar este (é o mais longo devido à ordenação)
                            best_match = match
                            best_code = code
                            try:
                                best_qty = int(match.group(1).strip())
                            except ValueError:
                                best_qty = 1
                            break
                    
                    if best_match and best_code:
                        # Adicionar componente encontrado
                        components.append((best_code, best_qty))
                        # Remover parte processada (código + (Qty))
                        match_end = best_match.end()
                        remaining = remaining[match_end:]
                        # Remover vírgula e espaços seguintes se existirem
                        remaining = remaining.lstrip(", ").lstrip()
                    else:
                        # Não encontrou match, tentar padrão genérico como fallback
                        match = re.match(r"^(.+?)\s*\((\d+)x?\)", remaining)
                        if match:
                            code = match.group(1).strip()
                            try:
                                qty = int(match.group(2).strip())
                                components.append((code, qty))
                            except ValueError:
                                components.append((code, 1))
                            # Remover parte processada
                            match_end = match.end()
                            remaining = remaining[match_end:].lstrip(", ").lstrip()
                        else:
                            # Não conseguiu fazer match, parar para evitar loop infinito
                            break
            else:
                # Fallback: método antigo (pode falhar com códigos contendo vírgulas)
                # Split by comma (pode ter espaço após vírgula)
                parts_list = parts_str.split(",")
                for part_str in parts_list:
                    part_str = part_str.strip()
                    if not part_str:
                        continue
                    
                    # Try to match pattern: "Code (Qty)" or "Code (Qty)x"
                    match = re.match(r"(.+?)\s*\((\d+)x?\)", part_str)
                    if match:
                        code = match.group(1).strip()
                        try:
                            qty = int(match.group(2).strip())
                            components.append((code, qty))
                        except ValueError:
                            # Se não conseguir converter qty, tratar como 1
                            components.append((code, 1))
                    else:
                        # If no pattern match, treat entire string as code with qty=1
                        components.append((part_str, 1))
        
        return components
    
    def get_component_name_by_code(self, code: str) -> str:
        """
        Retorna o nome de um componente pelo código
        
        Args:
            code: Código do componente
        
        Returns:
            Nome do componente ou "Desconhecido" se não encontrado
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM components WHERE code = ?", (code,))
            row = cursor.fetchone()
            if row:
                return row["name"] if isinstance(row, dict) else row[0]
            return "Desconhecido"
    
    def update_all_sale_prices(self, margin_percentage: float) -> bool:
        """
        Atualiza em massa todos os preços de venda dos componentes baseado na nova margem.
        
        Args:
            margin_percentage: Percentagem de margem (ex: 30.0 para 30%)
        
        Returns:
            True se sucesso, False caso contrário
        """
        try:
            # Calcular multiplicador: 1 + (margem / 100)
            multiplier = 1 + (margin_percentage / 100)
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Atualizar todos os componentes: preço_venda = preço_compra * multiplicador
                # Apenas atualiza componentes que têm preço_compra > 0
                cursor.execute(
                    """
                    UPDATE components 
                    SET price = preco_compra * ?
                    WHERE preco_compra IS NOT NULL 
                    AND preco_compra > 0
                    """,
                    (multiplier,)
                )
                conn.commit()
                return cursor.rowcount >= 0  # rowcount pode ser 0 se não houver componentes
        except Exception as e:
            print(f"Erro ao atualizar preços de venda em massa: {str(e)}")
            return False
    
    def get_components_by_ids(self, component_ids: List[int]) -> Dict[int, Dict]:
        """
        Retorna múltiplos componentes pelos IDs (mais eficiente que múltiplas consultas)
        
        Returns:
            Dicionário com {id: component_dict}
        """
        if not component_ids:
            return {}
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" * len(component_ids))
            cursor.execute(f"SELECT * FROM components WHERE id IN ({placeholders})", component_ids)
            rows = cursor.fetchall()
            return {row["id"]: dict(row) for row in rows}
    
    def update_component_qty(self, component_id: int, new_qty: int) -> bool:
        """
        Atualiza a quantidade de um componente
        
        Args:
            component_id: ID do componente
            new_qty: Nova quantidade (deve ser >= 0)
        """
        if new_qty < 0:
            return False
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE components SET qty = ? WHERE id = ?",
                (new_qty, component_id)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def add_stock_quantity(self, component_id: int, quantity_to_add: int) -> Optional[int]:
        """
        Adiciona quantidade ao stock existente de um componente
        
        Args:
            component_id: ID do componente
            quantity_to_add: Quantidade a adicionar (pode ser negativa para subtrair)
        
        Returns:
            Nova quantidade total após adição, ou None se erro
        """
        if quantity_to_add == 0:
            # Se quantidade a adicionar é 0, apenas retornar quantidade atual
            component = self.get_component_by_id(component_id)
            return component.get("qty", 0) if component else None
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Adicionar à quantidade existente
                cursor.execute(
                    "UPDATE components SET qty = qty + ? WHERE id = ? AND qty + ? >= 0",
                    (quantity_to_add, component_id, quantity_to_add)
                )
                conn.commit()
                
                if cursor.rowcount > 0:
                    # Retornar a nova quantidade
                    cursor.execute("SELECT qty FROM components WHERE id = ?", (component_id,))
                    row = cursor.fetchone()
                    if row:
                        return row["qty"] if isinstance(row, dict) else row[0]
                return None
        except Exception as e:
            print(f"Erro ao adicionar stock: {str(e)}")
            return None
    
    def update_component(
        self,
        component_id: int,
        code: str,
        name: str,
        price: float,
        qty: int,
        image_path: Optional[str] = None,
        datasheet_path: Optional[str] = None,
        family: Optional[str] = None,
        supplier: Optional[str] = None,
        supplier_ref: Optional[str] = None,
        preco_compra: Optional[float] = None,
    ) -> bool:
        """
        Atualiza todos os dados de um componente
        
        Args:
            component_id: ID do componente
            code: Código do componente
            name: Nome do componente
            price: Preço de venda
            qty: Quantidade em stock
            image_path: Caminho relativo para a imagem (opcional)
            datasheet_path: Caminho relativo para o PDF do datasheet (opcional)
            family: Família/Categoria do componente (opcional)
            supplier: Fornecedor do componente (opcional)
            supplier_ref: Referência do fornecedor (opcional)
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE components
                    SET
                        code = ?,
                        name = ?,
                        price = ?,
                        qty = ?,
                        image_path = ?,
                        datasheet_path = ?,
                        family = ?,
                        supplier = ?,
                        supplier_ref = ?,
                        preco_compra = ?
                    WHERE id = ?
                    """,
                    (
                        code,
                        name,
                        price,
                        qty,
                        image_path,
                        datasheet_path,
                        family,
                        supplier,
                        supplier_ref,
                        preco_compra if preco_compra is not None else 0.0,
                        component_id,
                    ),
                )
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.IntegrityError:
            return False
    
    def delete_component(self, component_id: int) -> bool:
        """Remove um componente"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM components WHERE id = ?", (component_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    # ========== OPERAÇÕES COM REPARAÇÕES ==========
    
    # ========== OPERAÇÕES COM CLIENTES (CRM) ==========
    
    def add_or_update_client(self, name: str, phone: str, nif: str = "", address: str = "") -> int:
        """
        Adiciona ou atualiza um cliente
        
        Args:
            name: Nome do cliente
            phone: Telefone (único, usado como chave)
            nif: NIF (opcional)
            address: Morada (opcional)
        
        Returns:
            ID do cliente (novo ou existente)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Verificar se cliente já existe (por telefone)
            cursor.execute("SELECT id FROM clients WHERE phone = ?", (phone,))
            existing = cursor.fetchone()
            
            if existing:
                # Atualizar cliente existente
                client_id = existing["id"] if isinstance(existing, dict) else existing[0]
                cursor.execute(
                    "UPDATE clients SET name = ?, nif = ?, address = ? WHERE id = ?",
                    (name, nif, address, client_id)
                )
                conn.commit()
                return client_id
            else:
                # Inserir novo cliente
                cursor.execute(
                    "INSERT INTO clients (name, phone, nif, address) VALUES (?, ?, ?, ?)",
                    (name, phone, nif, address)
                )
                client_id = cursor.lastrowid
                conn.commit()
                return client_id
    
    def search_client(self, query: str) -> List[Dict]:
        """
        Pesquisa clientes por nome ou telefone
        
        Args:
            query: Termo de pesquisa (nome ou telefone)
        
        Returns:
            Lista de clientes encontrados
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            search_pattern = f"%{query}%"
            cursor.execute(
                "SELECT * FROM clients WHERE name LIKE ? OR phone LIKE ? ORDER BY name LIMIT 20",
                (search_pattern, search_pattern)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def search_clients_smart(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Pesquisa otimizada para a lista de clientes (Meus Clientes).
        
        - Se query estiver vazia: devolve os N clientes mais recentes (ORDER BY id DESC LIMIT N)
        - Se query tiver texto: pesquisa em name, nif e phone (LIKE '%query%') e limita a N resultados.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if not query:
                cursor.execute(
                    "SELECT * FROM clients ORDER BY id DESC LIMIT ?",
                    (limit,)
                )
            else:
                pattern = f"%{query}%"
                cursor.execute(
                    """
                    SELECT * FROM clients
                    WHERE name LIKE ? OR nif LIKE ? OR phone LIKE ?
                    ORDER BY name
                    LIMIT ?
                    """,
                    (pattern, pattern, pattern, limit)
                )
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_client_by_id(self, client_id: int) -> Dict:
        """
        Obtém detalhes de um cliente por ID
        
        Args:
            client_id: ID do cliente
        
        Returns:
            Dicionário com dados do cliente ou None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def add_repair(self, client: str, description: str, used_parts: str, total: float, payment_status: str = "Pendente", hours_worked: float = 1.0, client_id: int = None, problem_summary: str = "", device_imei: str = "", repair_status: str = "Em Análise", electricity_hours: float = 0.0, package_weight: float = 0.0, transport_cost: float = 0.0, labor_type: str = "labor1", warranty_number: str = "", horas_teste: float = 0.0, preco_hora_teste: float = 0.0) -> int:
        """
        Adiciona uma nova reparação
        
        Args:
            client: Nome do cliente (mantido para compatibilidade)
            description: Descrição da reparação
            used_parts: Componentes utilizados
            total: Custo total
            payment_status: Estado do pagamento (padrão: "Pendente")
            hours_worked: Horas de trabalho ou unidades (padrão: 1.0) - agora genérico (Qty)
            client_id: ID do cliente (opcional, para ligação com tabela clients)
            problem_summary: Tipo de equipamento (opcional)
            device_imei: IMEI ou Número de Série do dispositivo (opcional)
            repair_status: Estado do workflow da reparação (padrão: "Em Análise")
            electricity_hours: Horas de eletricidade utilizadas (padrão: 0.0)
            package_weight: Peso da encomenda em kg (padrão: 0.0)
            transport_cost: Custo de transporte calculado (padrão: 0.0)
            labor_type: Tipo de mão de obra ('labor1', 'labor2', ou 'placas') (padrão: 'labor1')
            warranty_number: Número de garantia ou seguradora (opcional)
            horas_teste: Horas gastas em testes/diagnóstico (padrão: 0.0)
            preco_hora_teste: Preço por hora de teste (padrão: 0.0)
        
        Returns:
            ID da reparação criada
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "INSERT INTO repairs (client, description, used_parts, total, date, payment_status, hours_worked, client_id, problem_summary, device_imei, repair_status, electricity_hours, package_weight, transport_cost, labor_type, warranty_number, horas_teste, preco_hora_teste) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (client, description, used_parts, total, date_str, payment_status, hours_worked, client_id, problem_summary, device_imei, repair_status, electricity_hours, package_weight, transport_cost, labor_type, warranty_number, horas_teste, preco_hora_teste)
            )
            repair_id = cursor.lastrowid
            conn.commit()
            return repair_id

    def add_repair_with_stock_update(
        self,
        client: str,
        phone: str,
        nif: str,
        address: str,
        description: str,
        used_parts: str,
        total: float,
        components_to_consume: List[tuple],
        payment_status: str = "Pendente",
        hours_worked: float = 1.0,
        problem_summary: str = "",
        device_imei: str = "",
        repair_status: str = "Em Análise",
        electricity_hours: float = 0.0,
        package_weight: float = 0.0,
        transport_cost: float = 0.0,
        labor_type: str = "labor1",
        warranty_number: str = "",
        horas_teste: float = 0.0,
        preco_hora_teste: float = 0.0,
    ) -> int:
        """
        Cria/atualiza o cliente, regista a reparacao e abate stock numa unica transacao.
        Mantem compatibilidade com o schema existente e evita reparacoes sem stock abatido.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT id FROM clients WHERE phone = ?", (phone,))
            existing_client = cursor.fetchone()
            if existing_client:
                client_id = existing_client["id"]
                cursor.execute(
                    "UPDATE clients SET name = ?, nif = ?, address = ? WHERE id = ?",
                    (client, nif, address, client_id)
                )
            else:
                cursor.execute(
                    "INSERT INTO clients (name, phone, nif, address) VALUES (?, ?, ?, ?)",
                    (client, phone, nif, address)
                )
                client_id = cursor.lastrowid

            consumed_by_component = {}
            for comp_id, qty in components_to_consume or []:
                qty = int(qty)
                if qty <= 0:
                    raise ValueError("Quantidade de componente invalida.")
                consumed_by_component[int(comp_id)] = consumed_by_component.get(int(comp_id), 0) + qty

            for comp_id, qty in consumed_by_component.items():
                cursor.execute(
                    """
                    UPDATE components
                    SET qty = qty - ?
                    WHERE id = ? AND qty >= ?
                    """,
                    (qty, comp_id, qty)
                )
                if cursor.rowcount == 0:
                    cursor.execute("SELECT code, name, qty FROM components WHERE id = ?", (comp_id,))
                    component = cursor.fetchone()
                    if component:
                        raise ValueError(
                            f"Stock insuficiente para {component['code']} - {component['name']}. "
                            f"Disponivel: {component['qty']}, necessario: {qty}."
                        )
                    raise ValueError(f"Componente ID {comp_id} nao encontrado.")

            date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "INSERT INTO repairs (client, description, used_parts, total, date, payment_status, hours_worked, client_id, problem_summary, device_imei, repair_status, electricity_hours, package_weight, transport_cost, labor_type, warranty_number, horas_teste, preco_hora_teste) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (client, description, used_parts, total, date_str, payment_status, hours_worked, client_id, problem_summary, device_imei, repair_status, electricity_hours, package_weight, transport_cost, labor_type, warranty_number, horas_teste, preco_hora_teste)
            )
            repair_id = cursor.lastrowid
            conn.commit()
            return repair_id
    
    def update_repair_payment_status(self, repair_id: int, payment_status: str) -> bool:
        """
        Atualiza o estado de pagamento de uma reparação
        
        Args:
            repair_id: ID da reparação
            payment_status: Novo estado ("Pago" ou "Pendente")
        
        Returns:
            True se sucesso
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE repairs SET payment_status = ? WHERE id = ?",
                (payment_status, repair_id)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def toggle_payment_status(self, repair_id: int) -> str:
        """
        Alterna o estado de pagamento de uma reparação
        
        Args:
            repair_id: ID da reparação
        
        Returns:
            Novo estado ("Pago" ou "Pendente")
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Obter estado atual
            cursor.execute("SELECT payment_status FROM repairs WHERE id = ?", (repair_id,))
            row = cursor.fetchone()
            if row:
                current_status = row["payment_status"] if isinstance(row, dict) else row[0]
                new_status = "Pago" if current_status != "Pago" else "Pendente"
                # Atualizar
                cursor.execute(
                    "UPDATE repairs SET payment_status = ? WHERE id = ?",
                    (new_status, repair_id)
                )
                conn.commit()
                return new_status
            return "Pendente"
    
    def update_repair_status(self, repair_id: int, new_status: str) -> bool:
        """
        Atualiza o estado do workflow de uma reparação
        
        Args:
            repair_id: ID da reparação
            new_status: Novo estado ("Em Análise", "Aguardar Peças", "Pronto a Entregar")
        
        Returns:
            True se sucesso
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE repairs SET repair_status = ? WHERE id = ?",
                (new_status, repair_id)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def update_repair_with_stock_validation(self, repair_id: int, new_data_dict: Dict[str, Any]) -> bool:
        """
        Atualiza dados de uma reparação com validação de stock
        
        Valida se há stock suficiente antes de atualizar e ajusta o stock automaticamente.
        
        Args:
            repair_id: ID da reparação
            new_data_dict: Dicionário com campos a atualizar (deve incluir 'used_parts')
        
        Returns:
            True se sucesso
        
        Raises:
            ValueError: Se stock insuficiente para algum componente
        """
        if not new_data_dict:
            return False
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 1. Obter dados originais da reparação
                cursor.execute("SELECT used_parts FROM repairs WHERE id = ?", (repair_id,))
                row = cursor.fetchone()
                if not row:
                    raise ValueError(f"Reparação {repair_id} não encontrada")
                
                # sqlite3.Row doesn't have .get(), use index access
                # Since we're selecting a single column, use row[0] and handle None
                old_used_parts_str = row[0] if row[0] else ""
                
                # 2. Parse componentes antigos e novos
                old_components = self._parse_used_parts(old_used_parts_str)
                new_used_parts_str = new_data_dict.get("used_parts", "")
                new_components = self._parse_used_parts(new_used_parts_str)
                
                # 3. Normalizar para IDs: converter códigos para IDs se necessário
                def normalize_to_ids(components_list):
                    """Converte lista de (id_or_code, qty) para (id, qty)"""
                    normalized = []
                    for id_or_code, qty in components_list:
                        if isinstance(id_or_code, int):
                            # Já é um ID
                            normalized.append((id_or_code, qty))
                        else:
                            # É um código, buscar ID
                            component = self.get_component_by_code(id_or_code)
                            if component:
                                normalized.append((component.get("id"), qty))
                            # Se não encontrar, ignorar (componente pode ter sido removido)
                    return normalized
                
                old_components_normalized = normalize_to_ids(old_components)
                new_components_normalized = normalize_to_ids(new_components)
                
                # 4. Criar dicionários para facilitar lookup (usando IDs)
                old_dict = {}
                for comp_id, qty in old_components_normalized:
                    old_dict[comp_id] = old_dict.get(comp_id, 0) + qty
                new_dict = {}
                for comp_id, qty in new_components_normalized:
                    new_dict[comp_id] = new_dict.get(comp_id, 0) + qty
                
                # 5. Calcular delta e validar stock
                all_ids = set(old_dict.keys()) | set(new_dict.keys())
                
                for comp_id in all_ids:
                    old_qty = old_dict.get(comp_id, 0)
                    new_qty = new_dict.get(comp_id, 0)
                    qty_needed = new_qty - old_qty
                    
                    # Se precisa de mais stock
                    component = self.get_component_by_id(comp_id)
                    if component:
                        # Buscar componente por ID
                        cursor.execute("SELECT id, name, qty FROM components WHERE id = ?", (comp_id,))
                        component = cursor.fetchone()
                        if not component:
                            raise ValueError(f"Componente ID {comp_id} não encontrado na base de dados")
                        
                        # component is a dict, so .get() is safe
                        current_stock = component["qty"]
                        component_name = component["name"]
                        
                        if current_stock < qty_needed:
                            raise ValueError(
                                f"Stock insuficiente para '{component_name}'. "
                                f"Só existem {current_stock} unidades, mas são necessárias {qty_needed}."
                            )
                
                # 6. Se validação passou, atualizar stock
                for comp_id in all_ids:
                    old_qty = old_dict.get(comp_id, 0)
                    new_qty = new_dict.get(comp_id, 0)
                    qty_needed = new_qty - old_qty
                    
                    # Se não há mudança, pular
                    if qty_needed == 0:
                        continue
                    
                    if qty_needed > 0:
                        # component is a dict, so .get() is safe
                        component_id = component.get("id")
                        current_qty = component.get("qty", 0)
                        
                        if qty_needed > 0:
                            # Consumir stock (adicionar mais componentes)
                            new_stock = current_qty - qty_needed
                            self.update_component_qty(component_id, new_stock)
                        elif qty_needed < 0:
                            # Restaurar stock (remover ou diminuir componentes)
                            # qty_needed é negativo, então abs(qty_needed) é a quantidade a restaurar
                            new_stock = current_qty + abs(qty_needed)
                            self.update_component_qty(component_id, new_stock)
                
                # 6. Atualizar reparação
                set_clauses = []
                values = []
                
                allowed_fields = [
                    'device_imei', 'problem_summary', 'description', 
                    'hours_worked', 'used_parts', 'total',
                    'electricity_hours', 'package_weight', 'transport_cost',
                    'labor_type', 'warranty_number', 'horas_teste', 'preco_hora_teste'
                ]
                
                for field, value in new_data_dict.items():
                    if field in allowed_fields:
                        set_clauses.append(f"{field} = ?")
                        values.append(value)
                
                if not set_clauses:
                    return False
                
                values.append(repair_id)
                sql = f"UPDATE repairs SET {', '.join(set_clauses)} WHERE id = ?"
                cursor.execute(sql, values)
                conn.commit()
                
                return cursor.rowcount > 0
        except ValueError:
            # Re-raise ValueError (stock validation errors)
            raise
        except Exception as e:
            print(f"Erro ao atualizar reparação com validação de stock: {str(e)}")
            raise ValueError(f"Erro ao atualizar reparação: {str(e)}")
    
    def update_repair_data(self, repair_id: int, new_data_dict: Dict[str, Any]) -> bool:
        """
        Atualiza dados de uma reparação com base num dicionário de campos
        
        Args:
            repair_id: ID da reparação
            new_data_dict: Dicionário com campos a atualizar:
                - device_imei: IMEI ou Número de Série do dispositivo
                - problem_summary: Tipo de equipamento
                - description: Descrição completa da reparação
                - hours_worked: Horas de mão de obra
                - used_parts: Componentes utilizados (string formatada)
                - total: Custo total (será recalculado se necessário)
                - Outros campos conforme necessário
        
        Returns:
            True se sucesso, False caso contrário
        """
        if not new_data_dict:
            return False
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Construir query dinâmica baseada nos campos fornecidos
                set_clauses = []
                values = []
                
                # Campos permitidos para atualização
                allowed_fields = [
                    'device_imei', 'problem_summary', 'description', 
                    'hours_worked', 'used_parts', 'total',
                    'electricity_hours', 'package_weight', 'transport_cost',
                    'labor_type', 'warranty_number', 'horas_teste', 'preco_hora_teste'
                ]
                
                for field, value in new_data_dict.items():
                    if field in allowed_fields:
                        set_clauses.append(f"{field} = ?")
                        values.append(value)
                
                if not set_clauses:
                    return False  # Nenhum campo válido para atualizar
                
                # Adicionar repair_id para WHERE clause
                values.append(repair_id)
                
                # Executar UPDATE
                sql = f"UPDATE repairs SET {', '.join(set_clauses)} WHERE id = ?"
                cursor.execute(sql, values)
                conn.commit()
                
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Erro ao atualizar dados da reparação: {str(e)}")
            return False
    
    def delete_repair(self, repair_id: int) -> bool:
        """
        Remove uma reparação e restaura o stock dos componentes utilizados
        
        Args:
            repair_id: ID da reparação
        
        Returns:
            True se sucesso
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 1. Obter dados da reparação antes de apagar
                cursor.execute("SELECT used_parts FROM repairs WHERE id = ?", (repair_id,))
                row = cursor.fetchone()
                
                if not row:
                    return False  # Reparação não encontrada
                
                # sqlite3.Row doesn't have .get(), use index access
                # Since we're selecting a single column, use row[0] and handle None
                used_parts_str = row[0] if row[0] else ""
                
                # 2. Parse componentes e restaurar stock
                if used_parts_str and used_parts_str.strip() and used_parts_str.strip() != "Nenhum":
                    components = self._parse_used_parts(used_parts_str)
                    
                    for id_or_code, qty in components:
                        # Determinar se é ID ou código
                        if isinstance(id_or_code, int):
                            # É um ID, buscar diretamente
                            component = self.get_component_by_id(id_or_code)
                        else:
                            # É um código (formato antigo), buscar por código
                            component = self.get_component_by_code(id_or_code)
                        
                        if component:
                            component_id = component.get("id")
                            cursor.execute(
                                "UPDATE components SET qty = qty + ? WHERE id = ?",
                                (qty, component_id)
                            )
                
                # 3. Apagar reparação
                cursor.execute("DELETE FROM repairs WHERE id = ?", (repair_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Erro ao apagar reparação e restaurar stock: {str(e)}")
            return False
    
    def get_repair_by_id(self, repair_id: int) -> Optional[Dict]:
        """Obtém uma reparação por ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM repairs WHERE id = ?", (repair_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all_repairs(
        self,
        payment_filter: Optional[str] = None,
        status_filter: Optional[str] = None,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Retorna todas as reparações ordenadas por data (mais recente primeiro)
        
        Args:
            payment_filter: Filtro opcional por status de pagamento ("Pago" ou "Pendente")
            status_filter: Filtro opcional por status do workflow ("Em Análise", "Aguardar Peças", "Pronto a Entregar")
            date_start: Data início (YYYY-MM-DD) para filtrar por intervalo (opcional)
            date_end: Data fim (YYYY-MM-DD) para filtrar por intervalo (opcional)
            limit: Limite máximo de linhas a devolver (padrão: 50)
        
        Returns:
            Lista de reparações
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Construir query dinâmica com AND
            query = "SELECT * FROM repairs"
            conditions = []
            params = []
            
            if payment_filter and payment_filter != "All":
                conditions.append("payment_status = ?")
                params.append(payment_filter)
            
            if status_filter and status_filter != "All":
                conditions.append("repair_status = ?")
                params.append(status_filter)
            
            # Filtro por datas (comparar apenas YYYY-MM-DD; a coluna date pode ter hora)
            if date_start:
                conditions.append("substr(date, 1, 10) >= ?")
                params.append(date_start)
            if date_end:
                conditions.append("substr(date, 1, 10) <= ?")
                params.append(date_end)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            query += " ORDER BY date DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def search_repairs(
        self,
        search_term: str,
        payment_filter: Optional[str] = None,
        status_filter: Optional[str] = None,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Pesquisa reparações (super search) por:
        - Nome do cliente (repairs.client / clients.name)
        - NIF (clients.nif) via JOIN
        - Dispositivo (IMEI/Serial) (repairs.device_imei)
        - Tipo de equipamento (repairs.problem_summary)
        - Descrição (repairs.description)
        
        Args:
            search_term: Termo de pesquisa
            payment_filter: Filtro opcional por status de pagamento ("Pago" ou "Pendente")
            status_filter: Filtro opcional por status do workflow ("Em Análise", "Aguardar Peças", "Pronto a Entregar")
            date_start: Data início (YYYY-MM-DD) para filtrar por intervalo (opcional)
            date_end: Data fim (YYYY-MM-DD) para filtrar por intervalo (opcional)
            limit: Limite máximo de linhas a devolver (padrão: 50)
        
        Returns:
            Lista de reparações encontradas
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            search_pattern = f"%{search_term}%"
            
            # Construir query dinâmica com AND
            query = """
                SELECT r.* FROM repairs r
                LEFT JOIN clients c ON r.client_id = c.id
                WHERE (
                    r.client LIKE ?
                    OR r.description LIKE ?
                    OR r.device_imei LIKE ?
                    OR r.problem_summary LIKE ?
                    OR c.nif LIKE ?
                    OR c.name LIKE ?
                    OR c.phone LIKE ?
                )
            """
            params = [
                search_pattern,
                search_pattern,
                search_pattern,
                search_pattern,
                search_pattern,
                search_pattern,
                search_pattern,
            ]
            
            if payment_filter and payment_filter != "All":
                query += " AND r.payment_status = ?"
                params.append(payment_filter)
            
            if status_filter and status_filter != "All":
                query += " AND r.repair_status = ?"
                params.append(status_filter)
            
            if date_start:
                query += " AND substr(r.date, 1, 10) >= ?"
                params.append(date_start)
            if date_end:
                query += " AND substr(r.date, 1, 10) <= ?"
                params.append(date_end)
            
            query += " ORDER BY r.date DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    # ========== OPERAÇÕES COM CONFIGURAÇÕES ==========
    
    def get_setting(self, key: str, default_value: str = "") -> str:
        """
        Obtém o valor de uma configuração
        
        Args:
            key: Chave da configuração
            default_value: Valor padrão se não existir
        
        Returns:
            Valor da configuração ou default_value
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else default_value
    
    def set_setting(self, key: str, value: str) -> bool:
        """
        Define o valor de uma configuração
        
        Args:
            key: Chave da configuração
            value: Valor a definir
        
        Returns:
            True se sucesso
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (key, value)
                )
                conn.commit()
                return True
        except Exception:
            return False
    
    def get_transport_rules(self) -> List[Dict]:
        """
        Retorna as regras de transporte como lista de dicionários
        
        Returns:
            Lista de regras: [{"max_weight": float, "price": float}, ...]
        """
        import json
        rules_json = self.get_setting("transport_rules", "[]")
        try:
            rules = json.loads(rules_json)
            if isinstance(rules, list):
                return rules
            return []
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_transport_rules(self, rules_list: List[Dict]) -> bool:
        """
        Guarda as regras de transporte como JSON string
        
        Args:
            rules_list: Lista de dicionários [{"max_weight": float, "price": float}, ...]
        
        Returns:
            True se sucesso
        """
        import json
        try:
            rules_json = json.dumps(rules_list)
            return self.set_setting("transport_rules", rules_json)
        except Exception:
            return False
    
    # ========== EXPORTAÇÃO / IMPORTAÇÃO MASTER (EXCEL) ==========
    def _read_excel_sheet(self, filename: str, preferred_sheet: str, dtype: Optional[Dict] = None, converters: Optional[Dict] = None) -> pd.DataFrame:
        """
        Lê um ficheiro Excel e devolve o DataFrame da folha pretendida.
        Se a folha especificada não existir, devolve a primeira folha.
        
        Args:
            filename: Caminho do ficheiro Excel
            preferred_sheet: Nome da folha preferida
            dtype: Dicionário opcional de tipos de dados para colunas (ex: {'Código': str})
            converters: Dicionário opcional de funções conversoras para colunas (ex: {'Código': force_text})
        """
        xls = pd.ExcelFile(filename, engine="openpyxl")
        sheet_name = preferred_sheet if preferred_sheet in xls.sheet_names else xls.sheet_names[0]
        return pd.read_excel(xls, sheet_name=sheet_name, dtype=dtype, converters=converters)
    
    def _map_row_to_db(self, row, mapping_dict: Dict[str, str]) -> Dict[str, Any]:
        """
        Mapeia uma linha do Excel (com cabeçalhos em português) de volta para colunas da base de dados.
        
        Args:
            row: Pandas Series representando uma linha do DataFrame
            mapping_dict: Dicionário de mapeamento DB -> Excel (ex: CLIENTS_MAP, STOCK_MAP)
        
        Returns:
            Dicionário com chaves de colunas da base de dados e valores da linha
        """
        # Inverter o mapeamento: {'ID': 'id', 'Nome': 'name', ...}
        inv_map = {v: k for k, v in mapping_dict.items()}
        db_data = {}
        
        for excel_header, value in row.items():
            # Tentar mapeamento direto (português -> DB)
            if excel_header in inv_map:
                db_key = inv_map[excel_header]
                db_data[db_key] = value
            # Fallback: se o cabeçalho já está em inglês (compatibilidade retroativa)
            elif excel_header.lower() in mapping_dict:
                db_key = excel_header.lower()
                db_data[db_key] = value
        
        return db_data

    def export_master_database(self, filename: str) -> bool:
        """
        Exporta a base de dados completa para um ficheiro Excel com 3 folhas:
        - Clientes
        - Stock
        - Reparacoes
        """
        try:
            with self.get_connection() as conn:
                # Clientes
                clients_df = pd.read_sql_query(
                    "SELECT id, name, phone, nif, address FROM clients",
                    conn,
                )
                # Aplicar mapeamento de colunas para português
                clients_df = clients_df.rename(columns=CLIENTS_MAP)

                # Stock / Componentes (garantir que preco_compra é lido)
                components_df = pd.read_sql_query(
                    """
                    SELECT 
                        id,
                        code,
                        name,
                        family,
                        supplier,
                        supplier_ref,
                        preco_compra,
                        price,
                        qty
                    FROM components
                    """,
                    conn,
                )

                # Se por alguma razão a coluna ainda vier como 'custo', mapear para preco_compra
                if 'preco_compra' not in components_df.columns and 'custo' in components_df.columns:
                    components_df['preco_compra'] = components_df['custo']

                # CRITICAL: Convert 'code' column to string to preserve leading zeros and special characters
                # This must be done BEFORE renaming columns
                if 'code' in components_df.columns:
                    # Convert to string, handling NaN properly
                    components_df['code'] = components_df['code'].astype(str)
                    # Replace 'nan' strings and other NaN representations with empty string
                    components_df['code'] = components_df['code'].replace('nan', '').replace('NaT', '').replace('None', '')
                    # Ensure no None values remain
                    components_df['code'] = components_df['code'].fillna('')
                    
                    # CRITICAL: Verify all values are strings (not dicts or other objects)
                    # If any value is not a string, convert it
                    def ensure_string(val):
                        if isinstance(val, str):
                            return val
                        # If it's a dict, list, or other object, convert to string representation
                        return str(val) if val is not None else ''
                    
                    components_df['code'] = components_df['code'].apply(ensure_string)

                # Aplicar mapeamento de colunas para português
                components_df = components_df.rename(columns=STOCK_MAP)
                
                # CRITICAL: Verify 'Código' column exists after mapping
                if 'Código' not in components_df.columns:
                    raise ValueError("'Código' column not found after mapping! Check STOCK_MAP.")

                # Garantir ordem específica das colunas: ID, Código, Designação, Família,
                # Fornecedor, Ref. Fornecedor, Quantidade, Preço Compra, Preço Venda
                column_order = [
                    'ID',
                    'Código',
                    'Designação',
                    'Família',
                    'Fornecedor',
                    'Ref. Fornecedor',
                    'Quantidade',
                    'Preço Compra',
                    'Preço Venda',
                ]
                column_order = [col for col in column_order if col in components_df.columns]
                components_df = components_df[column_order]

                # Reparações (histórico completo) - Processar com expansão horizontal de componentes
                repairs_raw = pd.read_sql_query("SELECT * FROM repairs", conn)
                
                # Helper function to translate component IDs to human-readable format
                def translate_used_parts_to_readable(used_parts_str):
                    """
                    Translates used_parts string (ID:QTY format) to human-readable format.
                    Returns list of tuples: (formatted_string, qty) where formatted_string is "Code - Name"
                    (quantity is stored separately in the qty field, not in the formatted string)
                    """
                    if not used_parts_str or pd.isna(used_parts_str) or str(used_parts_str).strip() == "" or str(used_parts_str).strip() == "Nenhum":
                        return []
                    
                    # Use the existing _parse_used_parts method to parse the string
                    parsed_components = self._parse_used_parts(str(used_parts_str))
                    
                    readable_components = []
                    for id_or_code, qty in parsed_components:
                        # Determine if it's an ID (int) or code (str)
                        if isinstance(id_or_code, int):
                            # It's an ID, fetch component details
                            component = self.get_component_by_id(id_or_code)
                            if component:
                                code = component.get("code", f"ID {id_or_code}")
                                name = component.get("name", code)
                                # Format: "Code - Name" (quantity is in separate Qtd column)
                                formatted = f"{code} - {name}"
                                readable_components.append((formatted, qty))
                            else:
                                # Component not found, use ID as fallback
                                formatted = f"ID {id_or_code}"
                                readable_components.append((formatted, qty))
                        else:
                            # It's a code (old format), fetch component details by code
                            component = self.get_component_by_code(id_or_code)
                            if component:
                                code = component.get("code", id_or_code)
                                name = component.get("name", code)
                                # Format: "Code - Name" (quantity is in separate Qtd column)
                                formatted = f"{code} - {name}"
                                readable_components.append((formatted, qty))
                            else:
                                # Component not found, use code as fallback
                                formatted = f"{id_or_code}"
                                readable_components.append((formatted, qty))
                    
                    return readable_components
                
                # Find maximum number of components across all repairs
                max_components = 0
                parsed_repairs = []
                
                for _, row in repairs_raw.iterrows():
                    used_parts_str = row.get("used_parts", "") or ""
                    # Translate ID:QTY format to readable format
                    components = translate_used_parts_to_readable(used_parts_str)
                    max_components = max(max_components, len(components))
                    parsed_repairs.append((row, components))
                
                # Build DataFrame with dynamic component columns
                repairs_data = []
                
                for repair_row, components in parsed_repairs:
                    # Static columns (in order)
                    row_data = {
                        "ID": repair_row.get("id", ""),
                        "Data": repair_row.get("date", ""),
                        "Cliente": repair_row.get("client", ""),
                        "Tipo de Equipamento": repair_row.get("problem_summary", "") or "",
                        "Descrição": repair_row.get("description", ""),
                        "IMEI": repair_row.get("device_imei", "") or "",
                        "Nº Garantia": repair_row.get("warranty_number", "") or "",
                    }
                    
                    # Dynamic component columns
                    for i in range(max_components):
                        comp_num = i + 1
                        if i < len(components):
                            formatted_str, qty = components[i]
                            # formatted_str is already "Code - Name (Qty)", so we use it directly
                            # For Excel, we'll put the full formatted string in Componente column and qty in Qtd column
                            row_data[f"Componente {comp_num}"] = formatted_str
                            row_data[f"Qtd {comp_num}"] = qty
                        else:
                            row_data[f"Componente {comp_num}"] = ""
                            row_data[f"Qtd {comp_num}"] = ""
                    
                    # Final static columns
                    row_data["Total s/ IVA"] = repair_row.get("total", 0.0)
                    row_data["Estado Pagamento"] = repair_row.get("payment_status", "Pendente")
                    
                    repairs_data.append(row_data)
                
                # Create DataFrame with explicit column order
                static_cols_before = ["ID", "Data", "Cliente", "Tipo de Equipamento", "Descrição", "IMEI", "Nº Garantia"]
                component_cols = []
                for i in range(max_components):
                    comp_num = i + 1
                    component_cols.append(f"Componente {comp_num}")
                    component_cols.append(f"Qtd {comp_num}")
                static_cols_after = ["Total s/ IVA", "Estado Pagamento"]
                
                repairs_columns = static_cols_before + component_cols + static_cols_after
                repairs_df = pd.DataFrame(repairs_data, columns=repairs_columns)

            with pd.ExcelWriter(filename, engine="openpyxl") as writer:
                # A. WRITE ALL SHEETS
                clients_df.to_excel(writer, sheet_name="Clientes", index=False)
                components_df.to_excel(writer, sheet_name="Stock", index=False)
                repairs_df.to_excel(writer, sheet_name="Reparacoes", index=False)

                # B. ADJUST WIDTHS AND FORMAT CURRENCY FOR *ALL* SHEETS
                # Iterate explicitly through the sheet names we just created
                for sheet_name in ["Clientes", "Stock", "Reparacoes"]:
                    worksheet = writer.sheets[sheet_name]
                    
                    # Find the column index and letter for 'Código' (if it exists in this sheet)
                    codigo_col_index = None
                    codigo_col_letter = None
                    for idx, cell in enumerate(worksheet[1], 1):  # Row 1 is header
                        if cell.value == 'Código':
                            codigo_col_index = idx
                            codigo_col_letter = cell.column_letter
                            break
                    
                    # If 'Código' column exists, set entire column format to TEXT
                    # This prevents Excel from auto-converting values like "1:2" to time
                    if codigo_col_letter and codigo_col_index:
                        # Apply text format to the entire column (including header)
                        for row in worksheet.iter_rows(min_row=1, max_row=worksheet.max_row, min_col=codigo_col_index, max_col=codigo_col_index):
                            for cell in row:
                                # Ensure value is string (convert if needed)
                                if cell.value is not None:
                                    if not isinstance(cell.value, str):
                                        cell.value = str(cell.value)
                                # Set format to text ('@' is Excel's text format code)
                                cell.number_format = '@'
                    
                    for column in worksheet.columns:
                        max_length = 0
                        column_letter = column[0].column_letter
                        header_value = column[0].value  # Get header for currency check
                        column_idx = column[0].column  # Column index (1-based)
                        
                        # Check if this column should be formatted as currency
                        is_money_column = header_value in MONEY_COLUMNS if header_value else False
                        # Check if this is the 'Código' column (needs text format)
                        is_codigo_column = (column_idx == codigo_col_index) if codigo_col_index else False
                        
                        for cell in column:
                            try:
                                if cell.value:
                                    cell_len = len(str(cell.value))
                                    if cell_len > max_length:
                                        max_length = cell_len
                                    
                                    # Apply currency format to data cells (skip header row)
                                    if is_money_column and cell.row > 1:
                                        # Format as Euro currency: #,##0.00 "€"
                                        cell.number_format = '#,##0.00 "€"'
                                    
                                    # Apply text format to 'Código' column (skip header row)
                                    # Note: We already set the format above, but ensure value is string
                                    if is_codigo_column and cell.row > 1:
                                        # Force text format to prevent Excel from auto-converting
                                        # Convert value to string and set as text
                                        if not isinstance(cell.value, str):
                                            cell.value = str(cell.value)
                                        cell.number_format = '@'  # '@' is Excel's text format code
                            except Exception:
                                # Silently skip cells that can't be formatted
                                pass
                        
                        # Set width (max_length + padding)
                        # Minimum width of 10 to ensure readability
                        adjusted_width = max(max_length + 2, 10)
                        worksheet.column_dimensions[column_letter].width = adjusted_width

            return True
        except Exception as e:
            print(f"Erro ao exportar base de dados para Excel: {str(e)}")
            return False

    def import_clients_from_excel(self, filename: str) -> Dict:
        """
        Importa/atualiza clientes a partir de um ficheiro Excel.
        Procura a folha 'Clientes'; se não existir, usa a primeira folha.
        Suporta cabeçalhos em português (via CLIENTS_MAP) e inglês (compatibilidade retroativa).

        Upsert por:
        - id (se existir)
        - caso contrário, por nif (se existir e não vazio)
        - caso contrário, por phone (único)
        
        Usa SQL dinâmico para atualizar todas as colunas presentes no Excel.
        """
        df = self._read_excel_sheet(filename, "Clientes")
        
        # Normalizar nomes de colunas para lookup flexível (fallback)
        col_map = {c.lower(): c for c in df.columns}

        def get_column(possible_names):
            """Fallback: busca flexível de colunas"""
            for name in possible_names:
                col = col_map.get(name.lower())
                if col:
                    return col
            return None

        def clean_value(value, value_type=str):
            """Limpa e converte valores (remove NaN, strip strings, converte tipos)"""
            if value is None or pd.isna(value):
                return None
            if value_type == str:
                cleaned = str(value).strip()
                return cleaned if cleaned else None
            elif value_type == int:
                try:
                    return int(float(value)) if not pd.isna(value) else None
                except (ValueError, TypeError):
                    return None
            return value

        imported = 0
        updated = 0

        with self.get_connection() as conn:
            cursor = conn.cursor()
            for _, row in df.iterrows():
                # Usar mapeamento reverso (português -> DB)
                db_data = self._map_row_to_db(row, CLIENTS_MAP)
                
                # Limpar e normalizar valores com fallback para campos críticos
                name = db_data.get('name')
                if name is None or pd.isna(name):
                    name_col = get_column(["name", "nome", "Nome"])
                    name = clean_value(row[name_col] if name_col else None) or ""
                else:
                    name = clean_value(name) or ""
                
                phone = db_data.get('phone')
                if phone is None or pd.isna(phone):
                    phone_col = get_column(["phone", "telemovel", "telemóvel", "telefone", "Telemóvel"])
                    phone = clean_value(row[phone_col] if phone_col else None) or ""
                else:
                    phone = clean_value(phone) or ""
                
                if not name or not phone:
                    continue

                # Limpar todos os valores do db_data
                cleaned_data = {}
                for key, value in db_data.items():
                    if key == 'name':
                        cleaned_data[key] = name
                    elif key == 'phone':
                        cleaned_data[key] = phone
                    elif key == 'id':
                        cleaned_data[key] = clean_value(value, int)
                    else:
                        # Outros campos (nif, address, etc.)
                        cleaned_data[key] = clean_value(value, str)

                client_id = cleaned_data.get('id')
                nif = cleaned_data.get('nif')

                # Tentar encontrar cliente existente
                found_id = None
                if client_id:
                    cursor.execute("SELECT id FROM clients WHERE id = ?", (client_id,))
                    row_db = cursor.fetchone()
                    if row_db:
                        found_id = row_db[0]
                
                # Se não encontrou por ID, tentar por NIF
                if not found_id and nif:
                    cursor.execute("SELECT id FROM clients WHERE nif = ?", (nif,))
                    row_db = cursor.fetchone()
                    if row_db:
                        found_id = row_db[0]
                
                # Se ainda não encontrou, tentar por phone
                if not found_id:
                    cursor.execute("SELECT id FROM clients WHERE phone = ?", (phone,))
                    row_db = cursor.fetchone()
                    if row_db:
                        found_id = row_db[0]

                if found_id:
                    # UPDATE LOGIC (Dynamic)
                    # Filter out 'id' from update fields (we don't update the ID itself)
                    update_fields = {k: v for k, v in cleaned_data.items() if k != 'id' and v is not None}
                    
                    if update_fields:
                        # Create string: "name=?, phone=?, nif=?, address=?, ..."
                        set_clause = ", ".join([f"{col} = ?" for col in update_fields.keys()])
                        values = list(update_fields.values())
                        values.append(found_id)  # Add ID for the WHERE clause
                        
                        sql = f"UPDATE clients SET {set_clause} WHERE id = ?"
                        cursor.execute(sql, values)
                        updated += 1
                else:
                    # INSERT LOGIC (Dynamic)
                    # Filter out None values and 'id' (auto-increment)
                    insert_fields = {k: v for k, v in cleaned_data.items() if k != 'id' and v is not None}
                    
                    if insert_fields:
                        columns = ", ".join(insert_fields.keys())
                        placeholders = ", ".join(["?" for _ in insert_fields.keys()])
                        values = list(insert_fields.values())
                        
                        sql = f"INSERT INTO clients ({columns}) VALUES ({placeholders})"
                        cursor.execute(sql, values)
                        imported += 1

            conn.commit()

        return {"imported": imported, "updated": updated}

    def import_stock_from_excel(self, filename: str) -> Dict:
        """
        Importa/atualiza stock a partir de um ficheiro Excel.
        Procura a folha 'Stock'; se não existir, usa a primeira folha.
        Suporta cabeçalhos em português (via STOCK_MAP) e inglês (compatibilidade retroativa).

        Upsert por código (components.code).
        Usa SQL dinâmico para atualizar todas as colunas presentes no Excel.
        
        CRITICAL: Preserva códigos exatamente como aparecem no Excel, sem conversões automáticas.
        """
        # STEP 1: Define converter function to force text conversion at read time
        def force_text(val):
            """Force any value to be treated as text string"""
            if val is None or pd.isna(val):
                return ""
            return str(val).strip()
        
        # Use converters to force text conversion for critical columns
        # This prevents pandas from auto-converting to dates/times/numbers
        converters = {
            'Código': force_text,
            'Ref. Fornecedor': force_text,
            # Also include English alternatives for backward compatibility
            'code': force_text,
            'Code': force_text,
            'supplier_ref': force_text,
            'Supplier Ref': force_text
        }
        
        # Read Excel with converters
        df = self._read_excel_sheet(filename, "Stock", converters=converters)
        
        # STEP 2: Post-process the data with aggressive cleaning
        # Even with converters, pandas might still load some values as datetime/float
        def clean_code_column(val):
            """
            Clean code column values to ensure they are raw strings.
            Handles Date/Time objects, Floats, and other auto-conversions.
            """
            # Handle None/NaN
            if val is None or pd.isna(val):
                return ""
            
            # Handle Date/Time objects specifically
            if hasattr(val, 'strftime'):
                # If it's a time like 01:02:00, try to return "1:2" or just the string representation
                # Check if it's a time object (date is 1900-01-01)
                if isinstance(val, pd.Timestamp):
                    try:
                        if val.date() == pd.Timestamp('1900-01-01').date():
                            # It's a time, format as H:M
                            if val.hour is not None and val.minute is not None:
                                return f"{val.hour}:{val.minute}"
                        elif val.hour == 0 and val.minute == 0 and val.second == 0:
                            # It's a date, format as D-M
                            if val.day <= 31 and val.month <= 12:
                                return f"{val.day}-{val.month}"
                    except (AttributeError, ValueError, TypeError):
                        pass
                elif isinstance(val, datetime):
                    try:
                        if val.date() == datetime(1900, 1, 1).date():
                            if hasattr(val, 'hour') and val.hour is not None:
                                return f"{val.hour}:{val.minute}"
                        elif val.hour == 0 and val.minute == 0 and val.second == 0:
                            if val.day <= 31 and val.month <= 12:
                                return f"{val.day}-{val.month}"
                    except (AttributeError, ValueError, TypeError):
                        pass
                # Fallback: return string representation
                return str(val)
            
            # Handle Floats (e.g. 123.0 -> "123")
            if isinstance(val, float):
                if val.is_integer():
                    return str(int(val))
                return str(val)
            
            # For everything else, convert to string and strip
            return str(val).strip()
        
        # Apply cleaning to code columns
        code_column_names = ['Código', 'Ref. Fornecedor', 'code', 'Code', 'supplier_ref', 'Supplier Ref']
        for col_name in code_column_names:
            if col_name in df.columns:
                # Apply cleaning function
                df[col_name] = df[col_name].apply(clean_code_column)
                # Replace NaN representations
                df[col_name] = df[col_name].replace('nan', '').replace('NaT', '').replace('None', '')
        
        col_map = {c.lower(): c for c in df.columns}

        def get_column(possible_names):
            """Fallback: busca flexível de colunas"""
            for name in possible_names:
                col = col_map.get(name.lower())
                if col:
                    return col
            return None

        def clean_value(value, value_type=str):
            """Limpa e converte valores (remove NaN, strip strings, converte tipos)"""
            if value is None or pd.isna(value):
                return None
            if value_type == str:
                cleaned = str(value).strip()
                return cleaned if cleaned else None
            elif value_type == int:
                try:
                    return int(float(value)) if not pd.isna(value) else 0
                except (ValueError, TypeError):
                    return 0
            elif value_type == float:
                try:
                    return float(value) if not pd.isna(value) else 0.0
                except (ValueError, TypeError):
                    return 0.0
            return value

        imported = 0
        updated = 0
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for index, row in df.iterrows():
                # Usar mapeamento reverso (português -> DB)
                db_data = self._map_row_to_db(row, STOCK_MAP)
                
                # Limpar e normalizar valores com fallback para campos críticos
                # CRITICAL: Preservar código exatamente como está (sem conversões numéricas, sem splits)
                # Note: Code columns have already been cleaned by clean_code_column() above
                
                # Get code from db_data first
                code = db_data.get('code')
                
                # If code is None or NaN, try to get it directly from the row
                if code is None or pd.isna(code):
                    code_col = get_column(["code", "codigo", "Código"])
                    if code_col:
                        # CRITICAL: Get the cell value using row[column_name], not the whole column
                        raw_code = row[code_col]  # This gets the cell value for this specific row
                        
                        # Code should already be a cleaned string from DataFrame processing
                        if pd.isna(raw_code):
                            code = ""
                        else:
                            # CRITICAL: Ensure it's a scalar value, not a Series, dict, or other collection
                            # If it's a Series (shouldn't happen with iterrows, but check anyway)
                            if isinstance(raw_code, pd.Series):
                                raw_code = raw_code.iloc[0] if len(raw_code) > 0 else ""
                            
                            # If it's a dict, list, or tuple, convert to string
                            if isinstance(raw_code, dict):
                                code = str(raw_code)  # Convert dict to string as fallback
                            elif isinstance(raw_code, (list, tuple)):
                                raw_code = raw_code[0] if len(raw_code) > 0 else ""
                                code = str(raw_code).strip() if raw_code else ""
                            else:
                                # Normal case: it's a scalar value
                                code = str(raw_code).strip() if raw_code else ""
                    else:
                        code = ""
                else:
                    # Already got code from db_data, but ensure it's a string
                    if pd.isna(code):
                        code = ""
                    else:
                        # CRITICAL: Check if code is a dict (this would be the bug)
                        if isinstance(code, dict):
                            code = str(code)  # Convert dict to string as fallback
                        else:
                            code = str(code).strip() if code else ""
                
                # CRITICAL: Não fazer split, não fazer parsing. O código é usado "as is".
                
                name = db_data.get('name')
                if name is None or pd.isna(name):
                    name_col = get_column(["name", "nome", "Nome", "Designação", "designação"])
                    name = clean_value(row[name_col] if name_col else None) or ""
                else:
                    name = clean_value(name) or ""
                
                if not code or not name:
                    continue

                # Extrair Preço Compra e Preço Venda do Excel (com fallback)
                p_compra_raw = db_data.get('preco_compra')
                if p_compra_raw is None or pd.isna(p_compra_raw):
                    # Fallback: buscar diretamente da linha Excel
                    preco_compra_col = get_column(["preco_compra", "preço compra", "Preço Compra", "custo", "Custo"])
                    p_compra_raw = row[preco_compra_col] if preco_compra_col else None
                
                p_venda_raw = db_data.get('price')
                if p_venda_raw is None or pd.isna(p_venda_raw):
                    # Fallback: buscar diretamente da linha Excel
                    preco_venda_col = get_column(["price", "preço venda", "Preço Venda", "preco_venda"])
                    p_venda_raw = row[preco_venda_col] if preco_venda_col else None

                # Limpar e converter Preço Compra
                try:
                    if p_compra_raw is None or pd.isna(p_compra_raw) or str(p_compra_raw).strip() == '':
                        p_compra = 0.0
                    else:
                        p_compra = float(p_compra_raw)
                except (ValueError, TypeError):
                    p_compra = 0.0

                # Limpar e converter Preço Venda (com lógica de auto-cálculo)
                try:
                    if p_venda_raw is None or pd.isna(p_venda_raw) or str(p_venda_raw).strip() == '':
                        p_venda_excel = 0.0
                    else:
                        p_venda_excel = float(p_venda_raw)
                except (ValueError, TypeError):
                    p_venda_excel = 0.0

                # DECISION LOGIC: Se Preço Venda está vazio/zero, calcular automaticamente
                if p_venda_excel > 0:
                    # Case A: User specified a price. Respect it.
                    final_p_venda = p_venda_excel
                else:
                    # Case B: Empty/Zero. Auto-calculate from Preço Compra.
                    final_p_venda = p_compra * DEFAULT_MARGIN

                # Limpar todos os valores do db_data
                cleaned_data = {}
                for key, value in db_data.items():
                    if key == 'code':
                        cleaned_data[key] = code
                    elif key == 'name':
                        cleaned_data[key] = name
                    elif key == 'qty':
                        cleaned_data[key] = clean_value(value, int)
                    elif key == 'price':
                        # Usar o valor calculado (final_p_venda) em vez do valor bruto
                        cleaned_data[key] = final_p_venda
                    elif key == 'preco_compra':
                        cleaned_data[key] = p_compra
                    else:
                        # Outros campos (family, supplier, supplier_ref, etc.)
                        cleaned_data[key] = clean_value(value, str)

                # Verificar se componente já existe por código
                cursor.execute("SELECT id FROM components WHERE code = ?", (code,))
                row_db = cursor.fetchone()
                
                if row_db:
                    # UPDATE LOGIC (Dynamic)
                    # Filter out 'id' and 'code' from update fields (code is the lookup key)
                    update_fields = {k: v for k, v in cleaned_data.items() if k not in ['id', 'code'] and v is not None}
                    
                    if update_fields:
                        # Create string: "name=?, price=?, family=?, ..."
                        set_clause = ", ".join([f"{col} = ?" for col in update_fields.keys()])
                        values = list(update_fields.values())
                        values.append(row_db[0])  # Add ID for the WHERE clause
                        
                        sql = f"UPDATE components SET {set_clause} WHERE id = ?"
                        cursor.execute(sql, values)
                        updated += 1
                else:
                    # INSERT LOGIC (Dynamic)
                    # Filter out None values and 'id' (auto-increment)
                    insert_fields = {k: v for k, v in cleaned_data.items() if k != 'id' and v is not None}
                    
                    if insert_fields:
                        columns = ", ".join(insert_fields.keys())
                        placeholders = ", ".join(["?" for _ in insert_fields.keys()])
                        values = list(insert_fields.values())
                        
                        sql = f"INSERT INTO components ({columns}) VALUES ({placeholders})"
                        cursor.execute(sql, values)
                        imported += 1

            conn.commit()

        return {"imported": imported, "updated": updated}

    def import_repairs_from_excel(self, filename: str) -> Dict:
        """
        Importa/atualiza reparações a partir de um ficheiro Excel.
        Procura a folha 'Reparacoes'; se não existir, usa a primeira folha.
        Suporta cabeçalhos em português (via REPAIRS_MAP) e inglês (compatibilidade retroativa).

        Lazy Import Logic:
        - Auto-cria clientes se não existirem (usa nome do cliente)
        - Componentes não encontrados são armazenados como texto
        - ID é opcional (auto-increment se não fornecido)
        - Campos obrigatórios têm valores padrão se vazios
        
        Upsert por ID (repairs.id) usando INSERT OR REPLACE.
        Usa SQL dinâmico para atualizar todas as colunas presentes no Excel.
        """
        df = self._read_excel_sheet(filename, "Reparacoes")
        
        # Normalizar nomes de colunas para lookup flexível (fallback)
        col_map = {c.lower(): c for c in df.columns}

        def get_column(possible_names):
            """Fallback: busca flexível de colunas"""
            for name in possible_names:
                col = col_map.get(name.lower())
                if col:
                    return col
            return None

        def clean_value(value, value_type=str):
            """Limpa e converte valores (remove NaN, strip strings, converte tipos)"""
            if value is None or pd.isna(value):
                return None
            if value_type == str:
                cleaned = str(value).strip()
                return cleaned if cleaned else None
            elif value_type == int:
                try:
                    return int(float(value)) if not pd.isna(value) else None
                except (ValueError, TypeError):
                    return None
            elif value_type == float:
                try:
                    return float(value) if not pd.isna(value) else None
                except (ValueError, TypeError):
                    return None
            return value

        imported = 0
        updated = 0
        errors = []
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            for idx, row in df.iterrows():
                try:
                    # Usar mapeamento reverso (português -> DB) como nos outros imports
                    db_data = self._map_row_to_db(row, REPAIRS_MAP)
                    
                    # Log verbose
                    row_num = idx + 2  # +2 porque Excel começa em linha 1 e tem header
                    client_name = db_data.get('client') or get_column(["client", "cliente", "Cliente"])
                    if client_name:
                        client_name = clean_value(row[client_name] if isinstance(client_name, str) else client_name) or ""
                    else:
                        client_name = ""
                    
                    # ---------------------------------------------------------
                    # DIRECT SQL LOOKUP: Extract client name and find/create in DB
                    # ---------------------------------------------------------
                    # Step 1: Extract client name from Excel row
                    client_col = get_column(["client", "cliente", "Cliente", "Nome Cliente"])
                    if client_col:
                        client_name_raw = row[client_col]
                    else:
                        # Fallback: try from db_data mapping
                        client_name_raw = db_data.get('client')
                    
                    # Clean and strip the client name
                    if client_name_raw is not None and not pd.isna(client_name_raw):
                        client_name = str(client_name_raw).strip()
                    else:
                        client_name = "Unknown"
                    
                    if not client_name or client_name == "":
                        client_name = "Unknown"
                    
                    # Step 2: Try to find client in DB (Case Insensitive Search using SQL)
                    cursor.execute("SELECT id FROM clients WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))", (client_name,))
                    result = cursor.fetchone()
                    
                    if result:
                        # Found existing client (sqlite3.Row supports bracket notation)
                        client_id = result['id']
                    else:
                        # Not found? Create it immediately
                        try:
                            # Extract phone, nif, address from Excel if available
                            phone_col = get_column(["phone", "telemovel", "telemóvel", "telefone", "Phone"])
                            phone = clean_value(row[phone_col] if phone_col else None) if phone_col else None
                            if not phone:
                                phone = f"000000000{idx}"  # Telefone temporário único
                            
                            nif_col = get_column(["nif", "NIF"])
                            nif = clean_value(row[nif_col] if nif_col else None) if nif_col else ""
                            if not nif:
                                nif = ""
                            
                            address_col = get_column(["address", "morada", "Morada", "Address"])
                            address = clean_value(row[address_col] if address_col else None) if address_col else ""
                            if not address:
                                address = ""
                            
                            # Insert new client using original name (preserves casing)
                            cursor.execute(
                                "INSERT INTO clients (name, phone, nif, address) VALUES (?, ?, ?, ?)",
                                (client_name, phone, nif, address)
                            )
                            client_id = cursor.lastrowid
                            conn.commit()  # Important: Save immediately so next row finds it
                        except Exception as e:
                            errors.append(f"Row {row_num}: Failed to create client '{client_name}': {str(e)}")
                            continue  # Skip this row if client creation fails
                    
                    # Use client name for storage (preserves casing from Excel)
                    client_name_clean = client_name if client_name and client_name != "Unknown" else "N/A"
                    
                    # Limpar todos os valores do db_data
                    cleaned_data = {}
                    for key, value in db_data.items():
                        if key == 'id':
                            cleaned_data[key] = clean_value(value, int)
                        elif key in ['total', 'hours_worked', 'electricity_hours', 'package_weight', 
                                     'transport_cost', 'horas_teste', 'preco_hora_teste']:
                            cleaned_data[key] = clean_value(value, float)
                        elif key == 'client_id':
                            # Usar client_id encontrado/criado acima
                            cleaned_data[key] = client_id
                        else:
                            # Outros campos (strings)
                            cleaned = clean_value(value, str)
                            # Garantir valores padrão para campos obrigatórios
                            if key == 'client' and (not cleaned or cleaned == ""):
                                cleaned = client_name_clean  # Usar nome limpo
                            elif key == 'description' and (not cleaned or cleaned == ""):
                                cleaned = "N/A"
                            elif key == 'repair_status' and (not cleaned or cleaned == ""):
                                cleaned = "Em Análise"
                            elif key == 'payment_status' and (not cleaned or cleaned == ""):
                                cleaned = "Pendente"
                            elif key == 'date' and (not cleaned or cleaned == ""):
                                # Usar data atual se não fornecida
                                cleaned = datetime.now().strftime("%Y-%m-%d")
                            cleaned_data[key] = cleaned
                    
                    # Adicionar client_id se foi criado/encontrado
                    if client_id and 'client_id' not in cleaned_data:
                        cleaned_data['client_id'] = client_id
                    
                    # Garantir que client (nome) está presente
                    if 'client' not in cleaned_data or not cleaned_data['client']:
                        cleaned_data['client'] = client_name_clean
                    
                    # Garantir valores mínimos obrigatórios
                    if 'description' not in cleaned_data or not cleaned_data['description']:
                        cleaned_data['description'] = "N/A"
                    if 'date' not in cleaned_data or not cleaned_data['date']:
                        cleaned_data['date'] = datetime.now().strftime("%Y-%m-%d")
                    if 'total' not in cleaned_data or cleaned_data['total'] is None:
                        cleaned_data['total'] = 0.0
                    if 'repair_status' not in cleaned_data or not cleaned_data['repair_status']:
                        cleaned_data['repair_status'] = "Em Análise"
                    if 'payment_status' not in cleaned_data or not cleaned_data['payment_status']:
                        cleaned_data['payment_status'] = "Pendente"
                    
                    # ID é opcional - se não fornecido, será auto-increment
                    repair_id = cleaned_data.get('id')
                    exists = False
                    
                    if repair_id is not None and not (isinstance(repair_id, float) and pd.isna(repair_id)):
                        # Verificar se já existe
                        cursor.execute("SELECT id FROM repairs WHERE id = ?", (repair_id,))
                        exists = cursor.fetchone() is not None
                    else:
                        # Remover ID None para permitir auto-increment
                        cleaned_data.pop('id', None)
                    
                    # Filtrar None values (exceto campos numéricos que podem ser 0)
                    filtered_data = {}
                    for k, v in cleaned_data.items():
                        if v is not None:
                            filtered_data[k] = v
                        elif k in ['total', 'hours_worked', 'electricity_hours', 'package_weight', 
                                   'transport_cost', 'horas_teste', 'preco_hora_teste']:
                            # Campos numéricos podem ser 0
                            filtered_data[k] = 0.0
                    
                    if filtered_data:
                        cols = list(filtered_data.keys())
                        values = [filtered_data[c] for c in cols]
                        placeholders = ", ".join(["?"] * len(cols))
                        col_list = ", ".join(cols)
                        
                        if exists:
                            # UPDATE: usar UPDATE em vez de INSERT OR REPLACE para manter controle
                            set_clause = ", ".join([f"{col} = ?" for col in cols if col != 'id'])
                            update_values = [filtered_data[c] for c in cols if c != 'id']
                            update_values.append(repair_id)
                            sql = f"UPDATE repairs SET {set_clause} WHERE id = ?"
                            cursor.execute(sql, update_values)
                            updated += 1
                        else:
                            # INSERT
                            sql = f"INSERT INTO repairs ({col_list}) VALUES ({placeholders})"
                            cursor.execute(sql, values)
                            imported += 1
                
                except Exception as e:
                    error_msg = f"Row {idx + 2}: {str(e)}"
                    errors.append(error_msg)
                    print(f"  [ERROR] {error_msg}")
                    continue

            conn.commit()
        
        # Log final
        print(f"\nImport completed: {imported} imported, {updated} updated")
        if errors:
            print(f"Errors encountered: {len(errors)}")
            for err in errors[:10]:  # Mostrar apenas primeiros 10 erros
                print(f"  - {err}")

        return {"imported": imported, "updated": updated, "errors": len(errors)}

    # ========== SISTEMA DE BACKUP ==========
    
    def create_backup(self) -> bool:
        """
        Cria um backup automático da base de dados
        
        Returns:
            True se backup foi criado com sucesso
        """
        try:
            # Garantir que o ficheiro da base de dados existe
            if not os.path.exists(self.db_path):
                print("Aviso: Ficheiro de base de dados não encontrado para backup")
                return False
            
            # Determinar diretório do projeto (raiz) usando get_base_path()
            project_root = get_base_path()
            
            # Criar pasta backups se não existir
            backups_dir = os.path.join(project_root, "backups")
            os.makedirs(backups_dir, exist_ok=True)
            
            # Gerar nome do ficheiro com timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
            backup_filename = f"backup_loja_{timestamp}.db"
            backup_path = os.path.join(backups_dir, backup_filename)
            
            # Criar backup consistente mesmo quando SQLite esta em WAL.
            with self.get_connection() as source_conn:
                try:
                    source_conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
                except Exception:
                    pass
                backup_conn = sqlite3.connect(backup_path)
                try:
                    source_conn.backup(backup_conn)
                finally:
                    backup_conn.close()
            
            # Limpar backups antigos (opcional - mais de 30 dias)
            self._clean_old_backups(backups_dir, days=30)
            
            print(f"Backup criado com sucesso: {backup_filename}")
            return True
        
        except Exception as e:
            print(f"Erro ao criar backup: {str(e)}")
            return False
    
    def _clean_old_backups(self, backups_dir: str, days: int = 30):
        """
        Remove backups mais antigos que o número de dias especificado
        
        Args:
            backups_dir: Diretório onde estão os backups
            days: Número de dias para manter (padrão: 30)
        """
        try:
            if not os.path.exists(backups_dir):
                return
            
            cutoff_date = datetime.now() - timedelta(days=days)
            deleted_count = 0
            
            for filename in os.listdir(backups_dir):
                if not filename.startswith("backup_loja_") or not filename.endswith(".db"):
                    continue
                
                file_path = os.path.join(backups_dir, filename)
                
                # Obter data de modificação do ficheiro
                file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                
                # Se ficheiro é mais antigo que cutoff_date, apagar
                if file_mtime < cutoff_date:
                    try:
                        os.remove(file_path)
                        deleted_count += 1
                    except Exception:
                        pass  # Ignorar erros ao apagar ficheiros individuais
            
            if deleted_count > 0:
                print(f"Limpeza: {deleted_count} backup(s) antigo(s) removido(s)")
        
        except Exception:
            pass  # Ignorar erros na limpeza
    
    def restore_backup(self, backup_file_path: str) -> bool:
        """
        Restaura a base de dados a partir de um ficheiro de backup
        
        Args:
            backup_file_path: Caminho completo para o ficheiro de backup
        
        Returns:
            True se restauro foi bem-sucedido, False caso contrário
        """
        try:
            # Validar que o ficheiro de backup existe
            if not os.path.exists(backup_file_path):
                print(f"Erro: Ficheiro de backup não encontrado: {backup_file_path}")
                return False
            
            # Validar que é um ficheiro .db
            if not backup_file_path.endswith('.db'):
                print("Erro: Ficheiro de backup deve ter extensão .db")
                return False
            
            # Fechar conexão explicitamente para evitar "File is locked"
            self.close_connection()
            
            # Pequeno delay para garantir que a conexão foi fechada
            import time
            time.sleep(0.2)
            
            # Verificar se ainda há conexões abertas (tentar novamente se necessário)
            if os.path.exists(self.db_path):
                try:
                    # Tentar abrir o ficheiro em modo exclusivo para verificar se está bloqueado
                    test_conn = sqlite3.connect(self.db_path, timeout=1.0)
                    test_conn.close()
                except sqlite3.OperationalError:
                    # Se ainda estiver bloqueado, esperar mais um pouco
                    time.sleep(0.5)
            
            # Remover ficheiros WAL/SHM antigos para evitar misturar estado antigo com a BD restaurada
            for suffix in ("-wal", "-shm"):
                sidecar_path = self.db_path + suffix
                if os.path.exists(sidecar_path):
                    try:
                        os.remove(sidecar_path)
                    except Exception:
                        pass

            # Copiar ficheiro de backup sobre a base de dados atual
            shutil.copyfile(backup_file_path, self.db_path)
            
            # Re-estabelecer conexão
            # Resetar flag de inicialização para forçar nova conexão
            if hasattr(self, '_initialized'):
                # Criar nova conexão
                with self._connection_lock:
                    if self._connection:
                        try:
                            self._connection.close()
                        except:
                            pass
                    self._connection = None
                
                # Re-inicializar base de dados (garantir schema correto)
                self.init_database()
            
            print(f"Backup restaurado com sucesso de: {os.path.basename(backup_file_path)}")
            return True
        
        except Exception as e:
            print(f"Erro ao restaurar backup: {str(e)}")
            # Tentar re-estabelecer conexão mesmo em caso de erro
            try:
                self.init_database()
            except:
                pass
            return False
    
    # ========== ESTATÍSTICAS DO DASHBOARD ==========
    
    def get_dashboard_stats(self) -> Dict:
        """
        Obtém estatísticas para o dashboard
        
        Returns:
            Dicionário com:
            - total_sales: Soma de total de reparações pagas (apenas 'Pago')
            - pending_repairs: Número de reparações com status 'Pendente'
            - low_stock_count: Número de componentes com qty < 5
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Total de vendas (APENAS reparações pagas)
                cursor.execute(
                    "SELECT SUM(total) FROM repairs WHERE payment_status = 'Pago'"
                )
                result = cursor.fetchone()
                total_sales = float(result[0]) if result and result[0] is not None else 0.0
                
                # Contar reparações pendentes
                cursor.execute("SELECT COUNT(*) FROM repairs WHERE payment_status = 'Pendente'")
                result = cursor.fetchone()
                pending_repairs = result[0] if result else 0
                
                # Contar componentes com stock baixo (qty < 5)
                cursor.execute("SELECT COUNT(*) FROM components WHERE qty < 5")
                result = cursor.fetchone()
                low_stock_count = result[0] if result else 0
                
                return {
                    "total_sales": total_sales,
                    "pending_repairs": pending_repairs,
                    "low_stock_count": low_stock_count
                }
        except Exception as e:
            print(f"Erro ao obter estatísticas: {str(e)}")
            return {
                "total_sales": 0.0,
                "pending_repairs": 0,
                "low_stock_count": 0
            }
    
    def get_unpaid_repairs(self) -> List[Dict]:
        """
        Obtém lista de reparações não pagas (pendentes)
        
        Returns:
            Lista de dicionários com dados das reparações pendentes
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM repairs WHERE payment_status = 'Pendente' ORDER BY date DESC"
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            print(f"Erro ao obter reparações não pagas: {str(e)}")
            return []
    
    def get_paid_sales_total(self) -> float:
        """
        Obtém o total de vendas pagas
        
        Returns:
            Soma de total de reparações com payment_status = 'Pago'
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT SUM(total) FROM repairs WHERE payment_status = 'Pago'"
                )
                result = cursor.fetchone()
                return float(result[0]) if result and result[0] is not None else 0.0
        except Exception as e:
            print(f"Erro ao obter total de vendas pagas: {str(e)}")
            return 0.0
