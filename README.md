# Indutechpro

Aplicacao desktop para gestao de reparacoes, clientes, stock, folha de obra/PDF, importacao/exportacao Excel e backups locais.

O projeto foi organizado para uso real em empresa: o codigo pode evoluir sem obrigar a recriar a base de dados ja existente.


## Estrutura

```text
.
|-- main.py                  # Entrada da aplicacao
|-- database/                # Base de dados e camada SQLite
|-- ui/                      # Interface CustomTkinter
|-- assets/                  # Logo e ficheiros da aplicacao
|-- tests/                   # Testes automatizados
|-- docs/                    # Documentacao operacional
|-- scripts/                 # Scripts de manutencao
|-- build_exe.py             # Gera o executavel Windows
|-- requirements-app.txt     # Dependencias reais da app
`-- requirements-dev.txt     # Dependencias para testes/build/qualidade
```

Mais detalhe em [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md).

## Instalar Dependencias

Recomendado usar Python 3.11 ou superior.

```powershell
python -m pip install -r requirements-app.txt
```

## Executar em Desenvolvimento

```powershell
python main.py
```

## Testar

```powershell
python -m unittest discover tests
```

Ou:

```powershell
.\scripts\run_tests.ps1
```

## Gerar Executavel

Para gerar builds, instala tambem as dependencias de desenvolvimento:

```powershell
python -m pip install -r requirements-dev.txt
```

```powershell
python build_exe.py
```

O executavel fica em:

```text
dist/Indutechpro.exe
```

Nota: o build nao embute a base de dados real dentro do executavel. A app usa/cria a pasta `database/` junto ao executavel, preservando os dados existentes.

## Atualizar Uma Empresa Que Ja Usa a App

1. Fecha a aplicacao.
2. Faz backup da pasta `database/`.
3. Faz backup de `assets/components/` e `assets/datasheets/`, se existirem.
4. Substitui o codigo/executavel.
5. Mantem a base de dados existente.
6. Abre a app e confirma clientes, stock e reparacoes.

Mais detalhe em [docs/OPERATIONS.md](docs/OPERATIONS.md).

## Limpeza Segura

Para limpar caches Python geradas localmente:

```powershell
.\scripts\clean_generated.ps1
```

Isto nao apaga a base de dados, backups, assets nem executaveis.

## Funcionalidades

- Gestao de clientes
- Gestao de stock e componentes
- Registo de reparacoes
- Estados de reparacao e pagamento
- Calculo de mao de obra, eletricidade, transporte e testes
- Geracao de PDF
- Importacao/exportacao Excel
- Backups automaticos da base de dados

## Direitos

Copyright (c) 2026 Manel. All rights reserved.

Este projeto e publicado para portfolio e avaliacao tecnica. Nao e concedida permissao para copiar, modificar, distribuir, sublicenciar ou usar este software sem autorizacao previa por escrito.
