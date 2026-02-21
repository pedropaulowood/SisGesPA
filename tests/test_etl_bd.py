from __future__ import annotations

import pandas as pd

from src import etl_bd
from src.etl_bd import find_header_row_by_token, import_bd, load_excel_with_fallback
from src.models import IdDim, Saldos
from tests.conftest import make_bd_file


def _sample_bd_record() -> dict[str, object]:
    return {
        "#Id": "1001",
        "Grupo": "AS",
        "AI": "E.4A2.AN.0",
        "Título da AI": "Título Teste",
        "AO da AI": "2000",
        "PO da AI": "0001",
        "AO do PA": "2000",
        "PO do PA": "0001",
        "FR": "1050000000",
        "ND": "33903000",
        "UGR - Código": "20003",
        "UGR - Sigla": "UGR",
        "UGE - Código": "20003",
        "UGE - Sigla": "UGE",
        "Moeda": "R$",
        "UG Exterior": "",
        "Valor do PA Ini": 1000,
        "Valor do PA Aju": 1000,
        "Dif. Planejamento(Real)": 0,
        "Sol.Lib.Cred.": 0,
        "Sol.Bloq.": 0,
        "Sol.Desbloq.": 0,
        "Aprovado": 0,
        "Liberado": 0,
        "Bloqueado": 0,
        "Corte": 0,
        "Devolvido": 0,
        "Saldo": 1000,
        "Pedidos em Trâmite": 0,
        "Bandeja DGOM": 0,
        "A Atender": 0,
        "Gerente": "G1",
        "ODS": "ODS1",
        "Aprovador": "APR1",
        "IRP PA": "IRP",
        "Gerente de Meta - Código": "001",
        "Gerente de Meta - Sigla": "GM",
        "ODS da Meta - Código": "ODS-C",
        "ODS da Meta - Sigla": "ODS-S",
    }


def test_find_header_row_and_import_bd(SessionLocal, tmp_path):
    file_path = make_bd_file(tmp_path / "BD_test.xlsx", [_sample_bd_record()])
    raw = load_excel_with_fallback(file_path, sheet_name=0, header=None)
    header_idx = find_header_row_by_token(raw, "#Id")
    assert header_idx == 5

    with SessionLocal() as session:
        summary = import_bd(session, file_path=file_path, usuario="tester")
    assert summary["id_dim_inserted"] == 1
    assert summary["saldos_inserted"] == 1

    with SessionLocal() as session:
        ids = session.query(IdDim).all()
        saldos = session.query(Saldos).all()
        assert len(ids) == 1
        assert len(saldos) == 1


def test_import_bd_idempotente(SessionLocal, tmp_path):
    file_path = make_bd_file(tmp_path / "BD_test.xlsx", [_sample_bd_record()])

    with SessionLocal() as session:
        first = import_bd(session, file_path=file_path, usuario="tester")
    with SessionLocal() as session:
        second = import_bd(session, file_path=file_path, usuario="tester")

    assert first["id_dim_inserted"] == 1
    assert second["id_dim_inserted"] == 0
    assert second["saldos_updated"] >= 1

    with SessionLocal() as session:
        assert session.query(IdDim).count() == 1
        assert session.query(Saldos).count() == 1


def test_load_excel_with_fallback_remove_temp_convertido(monkeypatch, tmp_path):
    xls_path = tmp_path / "origem.xls"
    xls_path.write_bytes(b"fake-xls")

    temp_dir = tmp_path / "tmp_convertido"
    temp_dir.mkdir()
    converted = temp_dir / "origem.xlsx"
    converted.write_bytes(b"fake-xlsx")

    def _fake_read_excel(path, sheet_name=0, header=0):  # type: ignore[no-untyped-def]
        if str(path).lower().endswith(".xls"):
            raise ValueError("falha de leitura xls")
        return pd.DataFrame([{"ok": 1}])

    monkeypatch.setattr(etl_bd.pd, "read_excel", _fake_read_excel)
    monkeypatch.setattr(etl_bd, "_convert_xls_to_xlsx", lambda _: converted)

    df = load_excel_with_fallback(xls_path)
    assert not df.empty
    assert temp_dir.exists() is False
