from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from src.db import create_engine_sqlite, get_session_factory, init_db


BD_HEADERS = [
    "#Id",
    "Grupo",
    "AI",
    "Título da AI",
    "AO da AI",
    "PO da AI",
    "AO do PA",
    "PO do PA",
    "FR",
    "ND",
    "UGR - Código",
    "UGR - Sigla",
    "UGE - Código",
    "UGE - Sigla",
    "Moeda",
    "UG Exterior",
    "Valor do PA Ini",
    "Valor do PA Aju",
    "Dif. Planejamento(Real)",
    "Sol.Lib.Cred.",
    "Sol.Bloq.",
    "Sol.Desbloq.",
    "Aprovado",
    "Liberado",
    "Bloqueado",
    "Corte",
    "Devolvido",
    "Saldo",
    "Pedidos em Trâmite",
    "Bandeja DGOM",
    "A Atender",
    "Gerente",
    "ODS",
    "Aprovador",
    "IRP PA",
    "Gerente de Meta - Código",
    "Gerente de Meta - Sigla",
    "ODS da Meta - Código",
    "ODS da Meta - Sigla",
]


SOL_HEADER_ROW_1 = ["Dados do PA"] + [""] * 10 + ["Dados da Solicitação"] + [""] * 21
SOL_HEADER_ROW_2 = [
    "Exercício",
    "Grupo",
    "AI",
    "AOxPO AI",
    "AOxPO PA",
    "FR",
    "ND",
    "UGR",
    "UGE",
    "Moeda",
    "UG Exterior",
    "Origem",
    "Nº Solicitação",
    "Tipo de Solicitação",
    "Data Criação",
    "Prioridade",
    "Situação",
    "Data Situação",
    "Setor Atual",
    "Perfil Atual",
    "Grupo",
    "AI",
    "AOxPO PA",
    "FR",
    "ND",
    "UGR",
    "UGE",
    "Solicitado",
    "Atendido",
    "Em Atendimento",
    "Devolvido",
    "Saldo a atender",
    "NC",
]


@pytest.fixture
def SessionLocal(tmp_path):
    db_path = tmp_path / "test_sisgespa.db"
    engine = create_engine_sqlite(db_path)
    init_db(engine)
    return get_session_factory(engine)


@pytest.fixture
def session(SessionLocal):
    with SessionLocal() as s:
        yield s


def make_bd_file(path: Path, records: list[dict[str, Any]]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        ["Exercício", 2026] + [""] * (len(BD_HEADERS) - 2),
        [""] * len(BD_HEADERS),
        ["Total"] + [""] * (len(BD_HEADERS) - 1),
        [""] * len(BD_HEADERS),
        [""] * len(BD_HEADERS),
        BD_HEADERS,
    ]

    for rec in records:
        row = [rec.get(col, "") for col in BD_HEADERS]
        rows.append(row)

    df = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, header=False, sheet_name="Crédito do PA")
    return path


def make_solcred_file(path: Path, rows: list[list[Any]]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = [SOL_HEADER_ROW_1, SOL_HEADER_ROW_2, *rows]
    df = pd.DataFrame(content)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, header=False, sheet_name="dados")
    return path

