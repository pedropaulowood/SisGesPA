# SisGesPA

Aplicativo Python local (offline) para controle de créditos/saldos com base em:
- `BD.xls/.xlsx` (planilha de saldos)
- `SolCred.xls/.xlsx` (planilha de solicitações)

## Requisitos
- Windows + Python 3.12
- Dependências do `requirements.txt`

## Estrutura
```text
SisGesPA/
  src/
    app_streamlit.py
    db.py
    models.py
    etl_bd.py
    etl_solcred.py
    services_aprovacao.py
    services_dashboard.py
    services_relatorios.py
    services_auth.py
    utils_money.py
    constants.py
  tests/
  data/
  requirements.txt
  README.md
```

## Instalação
```powershell
cd C:\Users\bk_fa\python\SisGesPA
python -m pip install -r requirements.txt
```

## Inicialização do banco
Cria tabelas, índices e configuração padrão:
```powershell
python -m src.db --init
```

Cria o usuário admin inicial (se não existir):
```powershell
python -m src.db --seed-admin
```

Credenciais iniciais:
- Usuário: `admin`
- Senha temporária: `Admin@123`
- Troca de senha: obrigatória no primeiro login

Banco padrão:
- `C:\Users\bk_fa\python\SisGesPA\data\sisgespa.db`

## Executar aplicação
```powershell
streamlit run src/app_streamlit.py
```

## Fluxo operacional
1. Fazer login.
2. Página **Importar Arquivos**:
- Importar BD (atualiza `id_dim` e `saldos`, com upsert).
- Importar SolCred (upsert por `numero_solicitacao`).
3. Página **Dashboard**:
- Filtros por ODS (meta sigla) e AO do PA.
- Gauge circular de `% Aprovado`.
- KPIs de Valor PA AJU, Solicitado e Aprovado.
- Detalhamento por ODS/AO.
4. Página **Painel de Saldos**:
- Aplicar filtros por Grupo/AI/UGR/UGE/ND/FR.
- Ver alertas de saldo disponível.
5. Página **Painel de Solicitações**:
- Filtrar pendentes/em análise.
- Decidir: `APROVAR` ou `CANCELAR` com justificativa obrigatória.
6. Página **Relatórios**:
- Exportar Excel.
7. Página **Auditoria**:
- Consultar timeline por número de solicitação ou chave.

## Segurança e perfis
- Hash de senha com `bcrypt`.
- Perfis:
  - `ADMIN`: acesso total + gestão de usuários + importação.
  - `AVALIADOR`: consulta/análise.
  - `APROVADOR`: decisão + consulta.
  - `CONSULTA`: leitura.
- Login obrigatório para todas as páginas.
- Auditoria append-only sem tela de edição/exclusão.

## Regras de ETL e matching
- `BD`: cabeçalho detectado pela célula `#Id`.
- `SolCred`: leitura de `header=1` e renomeação por posição.
- Matching `SolCred -> id_dim` usa bloco PA (B–K), incluindo `AOxPO AI` e `AOxPO PA`.
- Se não houver match: `pendente_cadastro=true`, `id=null`, `pendencia_motivo='ID_DIM_NAO_ENCONTRADO'`.
- Reconciliação automática de pendências após importação do BD.

## .xls e fallback
Fluxo padrão usa `pandas.read_excel`.
Se leitura de `.xls` falhar:
1. Tenta conversão para `.xlsx` via LibreOffice (`soffice --headless`).
2. Se `soffice` não existir, o sistema orienta instalar `xlrd` ou converter manualmente para `.xlsx`.

## Testes
Executar:
```powershell
pytest -q
```

Cobertura principal:
- parsing AOxPO
- normalização monetária
- matching `id_dim`
- idempotência de importação BD/SolCred
- reconciliação de pendências
- decisão com auditoria e rollback
- validação de FK (`PRAGMA foreign_keys=ON`)
