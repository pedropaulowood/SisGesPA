from __future__ import annotations

from src.etl_bd import import_bd
from src.etl_solcred import import_solcred, match_id_dim
from src.models import Solicitacao
from tests.conftest import make_bd_file, make_solcred_file
from tests.test_etl_bd import _sample_bd_record


def _solcred_row(numero: str, fr: str = "1050000000", nd: str = "33903000") -> list[object]:
    return [
        2026,  # Exercício
        "AS",  # Grupo
        "E.4A2.AN.0",  # AI
        "2000 x 0001",  # AOxPO AI
        "2000 x 0001",  # AOxPO PA
        fr,  # FR
        nd,  # ND
        "20003",  # UGR
        "20003",  # UGE
        "R$",  # Moeda
        "",  # UG Exterior
        "20000",  # Origem
        numero,  # Nº Solicitação
        "Liberação de Crédito",  # Tipo
        "13/01/2026",  # Data Criação
        "Normal",  # Prioridade
        "Em Análise",  # Situação
        "13/01/2026",  # Data Situação
        "20000",  # Setor Atual
        "EMA",  # Perfil Atual
        "AS",  # Grupo (sol)
        "E.4A2.AN.0",  # AI (sol)
        "2000 x 0001",  # AOxPO PA (sol)
        fr,  # FR (sol)
        nd,  # ND (sol)
        "20003",  # UGR (sol)
        "20003",  # UGE (sol)
        "216.456,82",  # Solicitado
        "0,00",  # Atendido
        "0,00",  # Em Atendimento
        "0,00",  # Devolvido
        "216.456,82",  # Saldo a atender
        "",  # NC
    ]


def test_matching_id_dim_and_import_solcred(SessionLocal, tmp_path):
    bd_path = make_bd_file(tmp_path / "BD_test.xlsx", [_sample_bd_record()])
    sol_path = make_solcred_file(tmp_path / "Sol_test.xlsx", [_solcred_row("E4A2.2026.SC.00014")])

    with SessionLocal() as session:
        import_bd(session, bd_path, usuario="tester")

    with SessionLocal() as session:
        summary = import_solcred(session, sol_path, usuario="tester")
    assert summary["inserted"] == 1
    assert summary["pendentes"] == 0

    with SessionLocal() as session:
        sol = session.query(Solicitacao).filter_by(numero_solicitacao="E4A2.2026.SC.00014").first()
        assert sol is not None
        assert sol.id is not None
        assert sol.pendente_cadastro is False

        match_id = match_id_dim(
            session,
            {
                "grupo": "AS",
                "ai": "E.4A2.AN.0",
                "ao_ai": "2000",
                "po_ai": "0001",
                "ao_pa": "2000",
                "po_pa": "0001",
                "fr": "1050000000",
                "nd": "33903000",
                "ugr": "20003",
                "uge": "20003",
                "moeda": "R$",
                "ug_exterior": "",
            },
        )
        assert match_id == sol.id


def test_import_solcred_pending_when_no_match(SessionLocal, tmp_path):
    sol_path = make_solcred_file(tmp_path / "Sol_pending.xlsx", [_solcred_row("E4A2.2026.SC.99999")])

    with SessionLocal() as session:
        summary = import_solcred(session, sol_path, usuario="tester")
    assert summary["inserted"] == 1
    assert summary["pendentes"] == 1

    with SessionLocal() as session:
        sol = session.query(Solicitacao).filter_by(numero_solicitacao="E4A2.2026.SC.99999").first()
        assert sol is not None
        assert sol.id is None
        assert sol.pendente_cadastro is True
        assert sol.pendencia_motivo == "ID_DIM_NAO_ENCONTRADO"


def test_import_solcred_linhas_duplicadas_no_mesmo_arquivo(SessionLocal, tmp_path):
    bd_path = make_bd_file(tmp_path / "BD_base.xlsx", [_sample_bd_record()])

    numero = "E4A2.2026.SC.12345"
    row_1 = _solcred_row(numero)
    row_2 = _solcred_row(numero)
    row_1[27] = "100,00"
    row_1[31] = "100,00"
    row_2[27] = "200,00"
    row_2[31] = "200,00"
    sol_path = make_solcred_file(tmp_path / "Sol_duplicado.xlsx", [row_1, row_2])

    with SessionLocal() as session:
        import_bd(session, bd_path, usuario="tester")

    with SessionLocal() as session:
        summary = import_solcred(session, sol_path, usuario="tester")

    assert summary["inserted"] == 1
    assert summary["updated"] == 1

    with SessionLocal() as session:
        sol = session.query(Solicitacao).filter_by(numero_solicitacao=numero).first()
        assert sol is not None
        assert float(sol.solicitado) == 200.0
