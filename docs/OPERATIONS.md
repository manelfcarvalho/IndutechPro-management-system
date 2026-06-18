# Operacao e Manutencao

## Regra principal

Antes de atualizar a aplicacao numa empresa que ja esta a usar o sistema, faz sempre uma copia de:

- `database/indutechpro.db`
- `database/indutechpro.db-wal`, se existir
- `database/indutechpro.db-shm`, se existir
- `assets/components/`, se existir
- `assets/datasheets/`, se existir

## Instalar dependencias

```powershell
python -m pip install -r requirements-app.txt
```

## Executar em desenvolvimento

```powershell
python main.py
```

## Testar

```powershell
python -m unittest discover tests
```

## Gerar executavel

```powershell
python -m pip install -r requirements-dev.txt
```

```powershell
python build_exe.py
```

O executavel fica em `dist/Indutechpro.exe`.

## Atualizar uma instalacao existente

1. Fecha a aplicacao em todos os computadores.
2. Faz backup da pasta `database/` e dos assets carregados pelos utilizadores.
3. Substitui apenas o executavel/codigo.
4. Mantem a pasta `database/` existente.
5. Abre a aplicacao e confirma se clientes, stock e reparacoes aparecem.

## O que e seguro limpar

- `__pycache__/`
- `.DS_Store`
- `build/`, se nao precisares dos relatorios do ultimo build

## O que nao deve ser apagado sem backup

- `database/`
- `backups/`
- `assets/components/`
- `assets/datasheets/`
- `dist/Indutechpro.exe`, se for o executavel usado pela empresa
