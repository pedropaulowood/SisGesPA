from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.constants import (
    ACAO_APROVAR,
    ACAO_CANCELAR,
    ACAO_PARCIAL,
    ACOES_HABILITADAS,
    DEFAULT_SALDO_FORMULA,
    STATUS_APROVADA,
    STATUS_CANCELADA,
)
from src.models import AuditoriaEvento, Saldos, Solicitacao
from src.utils_money import to_decimal


def _decimal_to_str(value: Decimal | Any) -> str:
    return format(to_decimal(value), "f")


def _solicitacao_snapshot(sol: Solicitacao) -> dict[str, Any]:
    return {
        "numero_solicitacao": sol.numero_solicitacao,
        "id": sol.id,
        "pendente_cadastro": sol.pendente_cadastro,
        "sol_situacao": sol.sol_situacao,
        "solicitado": _decimal_to_str(sol.solicitado),
        "atendido": _decimal_to_str(sol.atendido),
        "em_atendimento": _decimal_to_str(sol.em_atendimento),
        "devolvido": _decimal_to_str(sol.devolvido),
        "saldo_a_atender": _decimal_to_str(sol.saldo_a_atender),
        "sol_data_situacao": sol.sol_data_situacao.isoformat() if sol.sol_data_situacao else None,
    }


def _registrar_auditoria(
    session: Session,
    usuario: str,
    acao: str,
    entidade: str,
    chave: str,
    antes: dict[str, Any],
    depois: dict[str, Any],
    justificativa: str,
) -> None:
    session.add(
        AuditoriaEvento(
            timestamp=datetime.now(),
            usuario=usuario,
            acao=acao,
            entidade=entidade,
            chave=chave,
            antes_json=json.dumps(antes, ensure_ascii=True),
            depois_json=json.dumps(depois, ensure_ascii=True),
            justificativa=justificativa,
        )
    )


def get_formula_config(session: Session) -> dict[str, Any]:
    # Regras fixas de negocio nesta versao:
    # Sol.Lib.Cred. = Liberado + Bandeja DGOM
    # Valor do PA Aju = Liberado + A Atender
    # Valor do PA Aju = Valor do PA Ini + Dif. Planejamento(Real)
    # Saldo = Valor do PA Aju - Sol.Lib.Cred.
    _ = session
    return dict(DEFAULT_SALDO_FORMULA)


def calculate_saldo_disponivel(saldo: Saldos, formula: dict[str, Any] | None = None) -> Decimal:
    # O parametro formula existe apenas por compatibilidade de assinatura.
    _ = formula
    valor_pa_aju = to_decimal(saldo.valor_pa_ini) + to_decimal(saldo.dif_planejamento_real)
    sol_lib_cred = to_decimal(saldo.liberado) + to_decimal(saldo.bandeja_dgom)
    return valor_pa_aju - sol_lib_cred


def _apply_decision(sol: Solicitacao, acao: str) -> None:
    acao_norm = acao.upper()
    now = datetime.now()
    solicitado = to_decimal(sol.solicitado)

    if acao_norm == ACAO_APROVAR:
        sol.sol_situacao = STATUS_APROVADA
        sol.atendido = solicitado
        sol.em_atendimento = Decimal("0")
        sol.saldo_a_atender = Decimal("0")
    elif acao_norm == ACAO_CANCELAR:
        sol.sol_situacao = STATUS_CANCELADA
        sol.atendido = Decimal("0")
        sol.em_atendimento = Decimal("0")
        sol.devolvido = solicitado
        sol.saldo_a_atender = Decimal("0")
    else:
        raise ValueError(f"Ação não suportada: {acao_norm}")

    sol.sol_data_situacao = now
    sol.updated_at = now


def decidir_solicitacao(
    session: Session,
    numero_solicitacao: str,
    acao: str,
    justificativa: str,
    usuario: str,
) -> dict[str, Any]:
    numero = (numero_solicitacao or "").strip()
    acao_norm = (acao or "").strip().upper()
    just = (justificativa or "").strip()

    if acao_norm == ACAO_PARCIAL:
        raise ValueError("Ação PARCIAL está indisponível nesta versão.")
    if acao_norm not in ACOES_HABILITADAS:
        raise ValueError(f"Ação inválida: {acao_norm}")
    if not numero:
        raise ValueError("Número de solicitação obrigatório.")
    if acao_norm == ACAO_CANCELAR and not just:
        raise ValueError("Justificativa obrigatoria para CANCELAR.")

    with session.begin():
        sol = session.execute(
            select(Solicitacao).where(Solicitacao.numero_solicitacao == numero)
        ).scalar_one_or_none()
        if sol is None:
            raise ValueError(f"Solicitação não encontrada: {numero}")
        if sol.pendente_cadastro:
            raise ValueError("Solicitação pendente de cadastro não pode ser decidida.")

        before = _solicitacao_snapshot(sol)
        _apply_decision(sol, acao_norm)
        after = _solicitacao_snapshot(sol)
        _registrar_auditoria(
            session=session,
            usuario=usuario,
            acao=acao_norm,
            entidade="solicitacao",
            chave=numero,
            antes=before,
            depois=after,
            justificativa=just,
        )

    return {"ok": True, "numero_solicitacao": numero, "acao": acao_norm}


def decidir_em_lote(
    session: Session,
    numeros: list[str],
    acao: str,
    justificativa: str,
    usuario: str,
) -> dict[str, Any]:
    acao_norm = (acao or "").strip().upper()
    just = (justificativa or "").strip()
    numeros_norm = [n.strip() for n in numeros if n and n.strip()]

    if acao_norm == ACAO_PARCIAL:
        raise ValueError("Ação PARCIAL está indisponível nesta versão.")
    if acao_norm not in ACOES_HABILITADAS:
        raise ValueError(f"Ação inválida: {acao_norm}")
    if not numeros_norm:
        raise ValueError("Nenhuma solicitação informada.")
    if acao_norm == ACAO_CANCELAR and not just:
        raise ValueError("Justificativa obrigatoria para CANCELAR.")

    decided: list[str] = []
    with session.begin():
        solicitacoes = session.execute(
            select(Solicitacao).where(Solicitacao.numero_solicitacao.in_(numeros_norm))
        ).scalars()
        found = {sol.numero_solicitacao: sol for sol in solicitacoes}

        missing = [num for num in numeros_norm if num not in found]
        if missing:
            raise ValueError(f"Solicitações não encontradas: {', '.join(missing)}")

        for numero in numeros_norm:
            sol = found[numero]
            if sol.pendente_cadastro:
                raise ValueError(f"Solicitação pendente de cadastro: {numero}")
            before = _solicitacao_snapshot(sol)
            _apply_decision(sol, acao_norm)
            after = _solicitacao_snapshot(sol)
            _registrar_auditoria(
                session=session,
                usuario=usuario,
                acao=acao_norm,
                entidade="solicitacao",
                chave=numero,
                antes=before,
                depois=after,
                justificativa=just,
            )
            decided.append(numero)

    return {"ok": True, "acao": acao_norm, "total": len(decided), "numeros": decided}

