from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import IdDim, Saldos, Solicitacao
from src.utils_money import normalize_code, to_decimal


def _normalize_status(value: Any) -> str:
    txt = normalize_code(value)
    txt = txt.upper().replace("_", " ").replace("-", " ")
    return " ".join(txt.split())


def _is_aprovado(sol_situacao: Any) -> bool:
    normalized = _normalize_status(sol_situacao)
    return normalized in {"APROVADA", "APROVADO", "APROVAR"}


def _resolve_ods_meta_sigla(saldo: Saldos | None) -> str:
    if saldo is None:
        return ""
    # ODS do dashboard deve vir estritamente da ultima coluna persistida em `saldos`:
    # `ods_meta_sigla` (sem fallback para `ods`).
    return normalize_code(saldo.ods_meta_sigla)


def _resolve_ao_pa(id_dim: IdDim | None, sol: Solicitacao | None = None) -> str:
    if id_dim is not None:
        ao = normalize_code(id_dim.ao_pa)
        if ao:
            return ao
    if sol is not None:
        fallback = normalize_code(sol.pa_ao_pa or sol.sol_ao_pa)
        if fallback:
            return fallback
    return ""


def _resolve_irp_pa(saldo: Saldos | None) -> str:
    if saldo is None:
        return ""
    return normalize_code(saldo.irp_pa)


def _resolve_grupo(id_dim: IdDim | None, sol: Solicitacao | None = None) -> str:
    if id_dim is not None:
        grupo = normalize_code(id_dim.grupo)
        if grupo:
            return grupo
    if sol is not None:
        fallback = normalize_code(sol.pa_grupo or sol.sol_grupo)
        if fallback:
            return fallback
    return ""


def get_dashboard_agregado(session: Session) -> pd.DataFrame:
    """
    Retorna agregacao por ODS (meta sigla), IRP PA, AO do PA e Grupo.

    Observacao de negocio:
    - Nao existe um flag explicito de "tipo PA AJU" no schema.
    - Portanto, o universo de PA AJU e considerado como os registros ligados
      a `saldos`, e o valor e calculado pela regra vigente:
      valor_pa_aju = valor_pa_ini + dif_planejamento_real.
    """

    grouped: dict[tuple[str, str, str, str], dict[str, Decimal]] = defaultdict(
        lambda: {
            "valor_pa_aju": Decimal("0"),
            "valor_solicitado": Decimal("0"),
            "valor_aprovado_saldos": Decimal("0"),
            "valor_aprovado_solicitacoes": Decimal("0"),
        }
    )

    saldos_rows = session.execute(select(Saldos, IdDim).join(IdDim, Saldos.id == IdDim.id)).all()
    for saldo, id_dim in saldos_rows:
        ods = _resolve_ods_meta_sigla(saldo) or "SEM_ODS"
        irp = _resolve_irp_pa(saldo) or "SEM_IRP"
        ao = _resolve_ao_pa(id_dim) or "SEM_AO"
        grupo = _resolve_grupo(id_dim) or "SEM_GRUPO"
        key = (ods, irp, ao, grupo)
        valor_pa_aju = to_decimal(saldo.valor_pa_ini) + to_decimal(saldo.dif_planejamento_real)
        grouped[key]["valor_pa_aju"] += valor_pa_aju
        grouped[key]["valor_aprovado_saldos"] += to_decimal(saldo.aprovado)

    solicitacoes_stmt = (
        select(Solicitacao, IdDim, Saldos)
        .join(IdDim, Solicitacao.id == IdDim.id, isouter=True)
        .join(Saldos, Solicitacao.id == Saldos.id, isouter=True)
    )
    for sol, id_dim, saldo in session.execute(solicitacoes_stmt).all():
        if sol.id is None:
            continue
        if saldo is None:
            # Sem saldo correspondente, nao ha como afirmar que pertence ao
            # universo de PA AJU nesta visao.
            continue

        ods = _resolve_ods_meta_sigla(saldo) or "SEM_ODS"
        irp = _resolve_irp_pa(saldo) or "SEM_IRP"
        ao = _resolve_ao_pa(id_dim, sol=sol) or "SEM_AO"
        grupo = _resolve_grupo(id_dim, sol=sol) or "SEM_GRUPO"
        key = (ods, irp, ao, grupo)

        solicitado = to_decimal(sol.solicitado)
        grouped[key]["valor_solicitado"] += solicitado

        if _is_aprovado(sol.sol_situacao):
            aprovado = to_decimal(sol.atendido)
            if aprovado <= 0:
                aprovado = solicitado
            grouped[key]["valor_aprovado_solicitacoes"] += aprovado

    rows: list[dict[str, float | str]] = []
    for (ods, irp, ao, grupo), payload in grouped.items():
        valor_pa_aju = payload["valor_pa_aju"]
        solicitado = payload["valor_solicitado"]
        aprovado = max(payload["valor_aprovado_saldos"], payload["valor_aprovado_solicitacoes"])
        percentual = (aprovado / valor_pa_aju * Decimal("100")) if valor_pa_aju > 0 else Decimal("0")
        rows.append(
            {
                "ods_meta_sigla": ods,
                "irp_pa": irp,
                "ao_pa": ao,
                "grupo": grupo,
                "valor_pa_aju": float(valor_pa_aju),
                "valor_solicitado": float(solicitado),
                "valor_aprovado": float(aprovado),
                "saldo_atual": float(valor_pa_aju - aprovado),
                "percentual_aprovado": float(percentual),
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "ods_meta_sigla",
                "irp_pa",
                "ao_pa",
                "grupo",
                "valor_pa_aju",
                "valor_solicitado",
                "valor_aprovado",
                "saldo_atual",
                "percentual_aprovado",
            ]
        )

    output = pd.DataFrame(rows)
    return output.sort_values(
        ["ods_meta_sigla", "irp_pa", "ao_pa", "grupo"],
        ascending=[True, True, True, True],
    ).reset_index(drop=True)


def calcular_kpis_dashboard(df: pd.DataFrame) -> dict[str, float]:
    if df.empty:
        return {
            "valor_pa_aju_total": 0.0,
            "valor_solicitado": 0.0,
            "valor_aprovado": 0.0,
            "saldo_atual": 0.0,
            "percentual_aprovado": 0.0,
        }

    valor_pa_aju_total = float(pd.to_numeric(df["valor_pa_aju"], errors="coerce").fillna(0).sum())
    valor_solicitado = float(pd.to_numeric(df["valor_solicitado"], errors="coerce").fillna(0).sum())
    valor_aprovado = float(pd.to_numeric(df["valor_aprovado"], errors="coerce").fillna(0).sum())
    saldo_atual = valor_pa_aju_total - valor_aprovado
    percentual = (valor_aprovado / valor_pa_aju_total * 100.0) if valor_pa_aju_total > 0 else 0.0
    return {
        "valor_pa_aju_total": valor_pa_aju_total,
        "valor_solicitado": valor_solicitado,
        "valor_aprovado": valor_aprovado,
        "saldo_atual": saldo_atual,
        "percentual_aprovado": percentual,
    }
