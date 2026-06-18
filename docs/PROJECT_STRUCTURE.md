# Estrutura do Projeto

Este projeto esta organizado para separar codigo, dados de trabalho e artefactos gerados.

## Codigo fonte

- `main.py` - ponto de entrada da aplicacao.
- `database/` - acesso SQLite, migracoes simples, backups e import/export.
- `ui/` - interface CustomTkinter.
- `ui/pages/` - paginas principais da aplicacao.
- `tests/` - testes automatizados de seguranca da base de dados.

## Dados locais

- `database/indutechpro.db` - base de dados real da empresa.
- `database/indutechpro.db-wal` e `database/indutechpro.db-shm` - ficheiros auxiliares do SQLite.
- `backups/` - copias automaticas e manuais da base de dados.
- `assets/components/` e `assets/datasheets/` - ficheiros carregados pelo utilizador.

Estes ficheiros nao devem ser apagados nem enviados para repositorios publicos.

## Distribuicao e build

- `build_exe.py` - script para gerar o executavel com PyInstaller.
- `Indutechpro.spec` - configuracao PyInstaller.
- `dist/` - executavel gerado localmente, ignorado pelo Git.
- `build/` - cache/relatorios do PyInstaller, ignorados pelo Git.

`build/` pode ser apagado e recriado. `dist/` deve ser mantido localmente se for o executavel que a empresa usa, mas nao deve ser publicado no repositorio.

## Configuracao

- `requirements-app.txt` - dependencias reais da aplicacao.
- `requirements-dev.txt` - dependencias para testes, build e ferramentas de qualidade.
- `.gitignore` - evita guardar dados reais, caches e builds no controlo de versao.
