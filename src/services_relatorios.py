from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.constants import DEFAULT_EXPORT_DIR
from src.models import AuditoriaEvento, IdDim, Saldos, Solicitacao
from src.services_aprovacao import calculate_saldo_disponivel, get_formula_config


def _apply_filters(df: pd.DataFrame, filtros: dict[str, Any] | None) -> pd.DataFrame:
    if df.empty or not filtros:
        return df
    filtered = df
    for key, value in filtros.items():
        if key not in filtered.columns:
            continue
        if value is None or value == "" or value == []:
            continue
        if isinstance(value, (list, tuple, set)):
            filtered = filtered[filtered[key].isin(value)]
        else:
            filtered = filtered[filtered[key] == value]
    return filtered


def _build_saldos_df(session: Session) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    formula = get_formula_config(session)
    query = session.execute(select(Saldos, IdDim).join(IdDim, Saldos.id == IdDim.id)).all()
    for saldo, dim in query:
        rows.append(
            {
                "id": dim.id,
                "grupo": dim.grupo,
                "ai": dim.ai,
                "ao_pa": dim.ao_pa,
                "po_pa": dim.po_pa,
                "fr": dim.fr,
                "nd": dim.nd,
                "ugr": dim.ugr,
                "uge": dim.uge,
                "moeda": dim.moeda,
                "valor_pa_aju": float(saldo.valor_pa_aju),
                "liberado": float(saldo.liberado),
                "bloqueado": float(saldo.bloqueado),
                "pedidos_em_tramite": float(saldo.pedidos_em_tramite),
                "a_atender": float(saldo.a_atender),
                "saldo_disponivel": float(calculate_saldo_disponivel(saldo, formula)),
                "saldo_registrado": float(saldo.saldo),
            }
        )
    return pd.DataFrame(rows)


def _build_solicitacoes_df(session: Session) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for sol in session.execute(select(Solicitacao)).scalars():
        rows.append(
            {
                "sol_id": sol.sol_id,
                "numero_solicitacao": sol.numero_solicitacao,
                "id": sol.id,
                "pendente_cadastro": sol.pendente_cadastro,
                "pendencia_motivo": sol.pendencia_motivo,
                "sol_situacao": sol.sol_situacao,
                "sol_prioridade": sol.sol_prioridade,
                "sol_origem": sol.sol_origem,
                "sol_tipo": sol.sol_tipo,
                "sol_data_criacao": sol.sol_data_criacao,
                "sol_data_situacao": sol.sol_data_situacao,
                "sol_setor_atual": sol.sol_setor_atual,
                "sol_perfil_atual": sol.sol_perfil_atual,
                "pa_grupo": sol.pa_grupo,
                "pa_ai": sol.pa_ai,
                "pa_ao_pa": sol.pa_ao_pa,
                "pa_po_pa": sol.pa_po_pa,
                "pa_fr": sol.pa_fr,
                "pa_nd": sol.pa_nd,
                "pa_ugr": sol.pa_ugr,
                "pa_uge": sol.pa_uge,
                "solicitado": float(sol.solicitado),
                "atendido": float(sol.atendido),
                "em_atendimento": float(sol.em_atendimento),
                "devolvido": float(sol.devolvido),
                "saldo_a_atender": float(sol.saldo_a_atender),
                "nc": sol.nc,
            }
        )
    return pd.DataFrame(rows)


def _build_auditoria_df(session: Session) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for event in session.execute(select(AuditoriaEvento).order_by(AuditoriaEvento.timestamp.asc())).scalars():
        rows.append(
            {
                "event_id": event.event_id,
                "timestamp": event.timestamp,
                "usuario": event.usuario,
                "acao": event.acao,
                "entidade": event.entidade,
                "chave": event.chave,
                "justificativa": event.justificativa,
                "antes_json": event.antes_json,
                "depois_json": event.depois_json,
            }
        )
    return pd.DataFrame(rows)


def exportar_relatorio_excel(session: Session, filtros: dict[str, Any], output_path: str | Path) -> str:
    output = Path(output_path)
    if not output.suffix:
        output = output.with_suffix(".xlsx")
    output.parent.mkdir(parents=True, exist_ok=True)

    saldos_df = _apply_filters(_build_saldos_df(session), filtros)
    solicitacoes_df = _apply_filters(_build_solicitacoes_df(session), filtros)
    pendencias_df = solicitacoes_df[solicitacoes_df["pendente_cadastro"] == True] if not solicitacoes_df.empty else pd.DataFrame()
    auditoria_df = _apply_filters(_build_auditoria_df(session), filtros)

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        saldos_df.to_excel(writer, sheet_name="saldos", index=False)
        solicitacoes_df.to_excel(writer, sheet_name="solicitacoes", index=False)
        pendencias_df.to_excel(writer, sheet_name="pendencias", index=False)
        auditoria_df.to_excel(writer, sheet_name="auditoria", index=False)

    return str(output)


def default_output_report_path() -> Path:
    DEFAULT_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return DEFAULT_EXPORT_DIR / f"relatorio_sisgespa_{ts}.xlsx"

