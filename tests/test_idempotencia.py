from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from src.etl_bd import import_bd
from src.etl_solcred import import_solcred
from src.models import AuditoriaEvento, Saldos, Solicitacao
from src.services_aprovacao import decidir_em_lote, decidir_solicitacao
from tests.conftest import make_bd_file, make_solcred_file
from tests.test_etl_bd import _sample_bd_record
from tests.test_etl_solcred import _solcred_row


def test_solcred_import_idempotente(SessionLocal, tmp_path):
    bd_path = make_bd_file(tmp_path / "BD.xlsx", [_sample_bd_record()])
    sol_path = make_solcred_file(tmp_path / "Sol.xlsx", [_solcred_row("E4A2.2026.SC.01000")])

    with SessionLocal() as session:
        import_bd(session, bd_path, usuario="tester")

    with SessionLocal() as session:
        first = import_solcred(session, sol_path, usuario="tester")
    with SessionLocal() as session:
        second = import_solcred(session, sol_path, usuario="tester")

    assert first["inserted"] == 1
    assert second["updated"] == 1

    with SessionLocal() as session:
        assert session.query(Solicitacao).count() == 1


def test_reconcile_pending_after_bd_import(SessionLocal, tmp_path):
    sol_path = make_solcred_file(tmp_path / "Sol_pending.xlsx", [_solcred_row("E4A2.2026.SC.02000")])
    bd_path = make_bd_file(tmp_path / "BD_match.xlsx", [_sample_bd_record()])

    with SessionLocal() as session:
        import_solcred(session, sol_path, usuario="tester")
    with SessionLocal() as session:
        sol = session.query(Solicitacao).filter_by(numero_solicitacao="E4A2.2026.SC.02000").first()
        assert sol is not None and sol.pendente_cadastro

    with SessionLocal() as session:
        import_bd(session, bd_path, usuario="tester")

    with SessionLocal() as session:
        sol = session.query(Solicitacao).filter_by(numero_solicitacao="E4A2.2026.SC.02000").first()
        assert sol is not None
        assert sol.pendente_cadastro is False
        assert sol.id is not None


def test_decisao_transacao_auditoria(SessionLocal, tmp_path):
    bd_path = make_bd_file(tmp_path / "BD.xlsx", [_sample_bd_record()])
    sol_path = make_solcred_file(
        tmp_path / "Sol.xlsx",
        [
            _solcred_row("E4A2.2026.SC.03000"),
            _solcred_row("E4A2.2026.SC.03001"),
        ],
    )

    with SessionLocal() as session:
        import_bd(session, bd_path, usuario="tester")
    with SessionLocal() as session:
        import_solcred(session, sol_path, usuario="tester")

    with SessionLocal() as session:
        res = decidir_solicitacao(
            session,
            numero_solicitacao="E4A2.2026.SC.03000",
            acao="APROVAR",
            justificativa="",
            usuario="aprovador",
        )
    assert res["ok"] is True

    with SessionLocal() as session:
        sol = session.query(Solicitacao).filter_by(numero_solicitacao="E4A2.2026.SC.03000").first()
        assert sol is not None
        assert sol.sol_situacao == "APROVADA"
        assert float(sol.atendido) > 0
        assert session.query(AuditoriaEvento).filter_by(chave="E4A2.2026.SC.03000").count() >= 1

    # Valida rollback em lote: uma solicitação inválida deve cancelar tudo.
    with SessionLocal() as session:
        try:
            decidir_em_lote(
                session,
                numeros=["E4A2.2026.SC.03001", "INEXISTENTE"],
                acao="CANCELAR",
                justificativa="lote",
                usuario="aprovador",
            )
        except ValueError:
            pass

    with SessionLocal() as session:
        sol = session.query(Solicitacao).filter_by(numero_solicitacao="E4A2.2026.SC.03001").first()
        assert sol is not None
        assert sol.sol_situacao in {"Em Análise", "EM_ANALISE", ""}


def test_fk_pragma_enabled(SessionLocal):
    with SessionLocal() as session:
        session.add(Saldos(id=999999))
        try:
            session.commit()
            raised = False
        except IntegrityError:
            session.rollback()
            raised = True
    assert raised is True


def test_cancelar_exige_justificativa(SessionLocal, tmp_path):
    bd_path = make_bd_file(tmp_path / "BD_cancel.xlsx", [_sample_bd_record()])
    sol_path = make_solcred_file(tmp_path / "Sol_cancel.xlsx", [_solcred_row("E4A2.2026.SC.04000")])

    with SessionLocal() as session:
        import_bd(session, bd_path, usuario="tester")
    with SessionLocal() as session:
        import_solcred(session, sol_path, usuario="tester")

    with SessionLocal() as session:
        with pytest.raises(ValueError, match="Justificativa obrigatoria para CANCELAR"):
            decidir_solicitacao(
                session,
                numero_solicitacao="E4A2.2026.SC.04000",
                acao="CANCELAR",
                justificativa="",
                usuario="aprovador",
            )


def test_cancelar_lote_exige_justificativa(SessionLocal, tmp_path):
    bd_path = make_bd_file(tmp_path / "BD_cancel_lote.xlsx", [_sample_bd_record()])
    sol_path = make_solcred_file(
        tmp_path / "Sol_cancel_lote.xlsx",
        [
            _solcred_row("E4A2.2026.SC.05000"),
            _solcred_row("E4A2.2026.SC.05001"),
        ],
    )

    with SessionLocal() as session:
        import_bd(session, bd_path, usuario="tester")
    with SessionLocal() as session:
        import_solcred(session, sol_path, usuario="tester")

    with SessionLocal() as session:
        with pytest.raises(ValueError, match="Justificativa obrigatoria para CANCELAR"):
            decidir_em_lote(
                session,
                numeros=["E4A2.2026.SC.05000", "E4A2.2026.SC.05001"],
                acao="CANCELAR",
                justificativa="",
                usuario="aprovador",
            )
