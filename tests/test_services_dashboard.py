from __future__ import annotations

import pytest

from src.etl_bd import import_bd
from src.etl_solcred import import_solcred
from src.services_aprovacao import decidir_solicitacao
from src.services_dashboard import calcular_kpis_dashboard, get_dashboard_agregado
from tests.conftest import make_bd_file, make_solcred_file
from tests.test_etl_bd import _sample_bd_record
from tests.test_etl_solcred import _solcred_row


def test_dashboard_agregacao_por_ods_e_ao(SessionLocal, tmp_path):
    bd_record = _sample_bd_record()
    bd_record["ODS da Meta - Sigla"] = "ODS-ALFA"
    bd_record["Valor do PA Ini"] = 1000
    bd_record["Dif. Planejamento(Real)"] = 0
    bd_path = make_bd_file(tmp_path / "BD_dashboard.xlsx", [bd_record])

    row1 = _solcred_row("E4A2.2026.SC.70000")
    row2 = _solcred_row("E4A2.2026.SC.70001")
    row1[27] = "100,00"
    row1[31] = "100,00"
    row2[27] = "200,00"
    row2[31] = "200,00"
    sol_path = make_solcred_file(tmp_path / "Sol_dashboard.xlsx", [row1, row2])

    with SessionLocal() as session:
        import_bd(session, bd_path, usuario="tester")
    with SessionLocal() as session:
        import_solcred(session, sol_path, usuario="tester")
    with SessionLocal() as session:
        decidir_solicitacao(
            session,
            numero_solicitacao="E4A2.2026.SC.70000",
            acao="APROVAR",
            justificativa="",
            usuario="aprovador",
        )
    with SessionLocal() as session:
        df = get_dashboard_agregado(session)

    assert len(df) == 1
    row = df.iloc[0]
    assert row["ods_meta_sigla"] == "ODS-ALFA"
    assert row["ao_pa"] == "2000"
    assert row["valor_pa_aju"] == pytest.approx(1000.0)
    assert row["valor_solicitado"] == pytest.approx(300.0)
    assert row["valor_aprovado"] == pytest.approx(100.0)
    assert row["saldo_atual"] == pytest.approx(900.0)
    assert row["percentual_aprovado"] == pytest.approx(10.0, rel=1e-3)

    kpis = calcular_kpis_dashboard(df)
    assert kpis["valor_pa_aju_total"] == pytest.approx(1000.0)
    assert kpis["valor_solicitado"] == pytest.approx(300.0)
    assert kpis["valor_aprovado"] == pytest.approx(100.0)
    assert kpis["saldo_atual"] == pytest.approx(900.0)
    assert kpis["percentual_aprovado"] == pytest.approx(10.0, rel=1e-3)


def test_dashboard_valor_aprovado_vem_do_bd(SessionLocal, tmp_path):
    bd_record = _sample_bd_record()
    bd_record["ODS da Meta - Sigla"] = "ODS-BETA"
    bd_record["Aprovado"] = 450
    bd_record["Valor do PA Ini"] = 1000
    bd_record["Dif. Planejamento(Real)"] = 0
    bd_path = make_bd_file(tmp_path / "BD_dashboard_aprovado.xlsx", [bd_record])

    with SessionLocal() as session:
        import_bd(session, bd_path, usuario="tester")
    with SessionLocal() as session:
        df = get_dashboard_agregado(session)

    assert len(df) == 1
    row = df.iloc[0]
    assert row["ods_meta_sigla"] == "ODS-BETA"
    assert row["ao_pa"] == "2000"
    assert row["valor_aprovado"] == pytest.approx(450.0)
    assert row["saldo_atual"] == pytest.approx(550.0)
