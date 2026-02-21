from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from src.constants import SOLCRED_COLUMN_BY_INDEX
from src.etl_bd import load_excel_with_fallback
from src.models import AuditoriaEvento, IdDim, Solicitacao
from src.utils_money import normalize_code, parse_aoxpo, to_decimal, to_local_datetime


_ID_MATCH_FIELDS = ["grupo", "ai", "ao_ai", "po_ai", "ao_pa", "po_pa", "fr", "nd", "ugr", "uge", "moeda", "ug_exterior"]


def rename_solcred_columns(df_raw: pd.DataFrame) -> pd.DataFrame:
    renamed = {}
    for idx, col in enumerate(df_raw.columns):
        renamed[col] = SOLCRED_COLUMN_BY_INDEX.get(idx, f"extra_{idx}")
    return df_raw.rename(columns=renamed).copy()


def _build_match_payload_from_row(row: pd.Series) -> dict[str, str]:
    ao_ai, po_ai = parse_aoxpo(row.get("pa_aoxpo_ai", ""))
    ao_pa, po_pa = parse_aoxpo(row.get("pa_aoxpo_pa", ""))
    return {
        "grupo": normalize_code(row.get("pa_grupo", "")),
        "ai": normalize_code(row.get("pa_ai", "")),
        "ao_ai": ao_ai,
        "po_ai": po_ai,
        "ao_pa": ao_pa,
        "po_pa": po_pa,
        "fr": normalize_code(row.get("pa_fr", "")),
        "nd": normalize_code(row.get("pa_nd", "")),
        "ugr": normalize_code(row.get("pa_ugr", "")),
        "uge": normalize_code(row.get("pa_uge", "")),
        "moeda": normalize_code(row.get("pa_moeda", "")),
        "ug_exterior": normalize_code(row.get("pa_ug_exterior", "")),
    }


def _build_match_payload_from_solicitacao(sol: Solicitacao) -> dict[str, str]:
    return {
        "grupo": normalize_code(sol.pa_grupo),
        "ai": normalize_code(sol.pa_ai),
        "ao_ai": normalize_code(sol.pa_ao_ai),
        "po_ai": normalize_code(sol.pa_po_ai),
        "ao_pa": normalize_code(sol.pa_ao_pa),
        "po_pa": normalize_code(sol.pa_po_pa),
        "fr": normalize_code(sol.pa_fr),
        "nd": normalize_code(sol.pa_nd),
        "ugr": normalize_code(sol.pa_ugr),
        "uge": normalize_code(sol.pa_uge),
        "moeda": normalize_code(sol.pa_moeda),
        "ug_exterior": normalize_code(sol.pa_ug_exterior),
    }


def match_id_dim(session: Session, pa_key: dict[str, str]) -> int | None:
    filters = [getattr(IdDim, field) == pa_key.get(field, "") for field in _ID_MATCH_FIELDS]
    found = session.execute(select(IdDim).where(and_(*filters))).scalar_one_or_none()
    return found.id if found else None


def _solicitacao_snapshot(sol: Solicitacao) -> dict[str, Any]:
    return {
        "numero_solicitacao": sol.numero_solicitacao,
        "id": sol.id,
        "pendente_cadastro": sol.pendente_cadastro,
        "pendencia_motivo": sol.pendencia_motivo,
        "sol_situacao": sol.sol_situacao,
        "solicitado": str(sol.solicitado),
        "atendido": str(sol.atendido),
        "devolvido": str(sol.devolvido),
        "saldo_a_atender": str(sol.saldo_a_atender),
    }


def import_solcred(session: Session, file_path: str | Path, usuario: str) -> dict[str, Any]:
    df = load_excel_with_fallback(file_path, sheet_name=0, header=1)
    df = df.dropna(how="all")
    df = rename_solcred_columns(df)

    inserted = 0
    updated = 0
    pendentes = 0
    skipped = 0
    warnings: list[str] = []
    # Evita violação de UNIQUE quando o mesmo número aparece repetido no mesmo arquivo.
    seen_in_batch: dict[str, Solicitacao] = {}

    with session.begin():
        for idx, row in df.iterrows():
            numero = normalize_code(row.get("sol_numero_solicitacao", ""))
            if not numero:
                skipped += 1
                warnings.append(f"Linha {idx}: sem número de solicitação.")
                continue

            try:
                pa_payload = _build_match_payload_from_row(row)
            except ValueError as exc:
                skipped += 1
                warnings.append(f"Linha {idx} ({numero}): AOxPO inválido ({exc}).")
                continue

            id_match = match_id_dim(session, pa_payload)
            pendente = id_match is None
            if pendente:
                pendentes += 1

            sol_aoxpo_val = normalize_code(row.get("sol_aoxpo_pa", ""))
            sol_ao_pa, sol_po_pa = ("", "")
            if sol_aoxpo_val:
                try:
                    sol_ao_pa, sol_po_pa = parse_aoxpo(sol_aoxpo_val)
                except ValueError:
                    # Não impede carga; mantém vazio.
                    pass

            sol = seen_in_batch.get(numero)
            if sol is None:
                existing = session.execute(
                    select(Solicitacao).where(Solicitacao.numero_solicitacao == numero)
                ).scalar_one_or_none()

                if existing is None:
                    sol = Solicitacao(numero_solicitacao=numero)
                    session.add(sol)
                    inserted += 1
                else:
                    sol = existing
                    updated += 1
                seen_in_batch[numero] = sol
            else:
                updated += 1

            sol.id = id_match
            sol.pendente_cadastro = pendente
            sol.pendencia_motivo = "ID_DIM_NAO_ENCONTRADO" if pendente else None

            sol.sol_data_criacao = to_local_datetime(row.get("sol_data_criacao"))
            sol.sol_prioridade = normalize_code(row.get("sol_prioridade", ""))
            sol.sol_origem = normalize_code(row.get("sol_origem", ""))
            sol.sol_situacao = normalize_code(row.get("sol_situacao", ""))
            sol.sol_tipo = normalize_code(row.get("sol_tipo", ""))
            sol.sol_data_situacao = to_local_datetime(row.get("sol_data_situacao"))
            sol.sol_setor_atual = normalize_code(row.get("sol_setor_atual", ""))
            sol.sol_perfil_atual = normalize_code(row.get("sol_perfil_atual", ""))

            sol.pa_grupo = pa_payload["grupo"]
            sol.pa_ai = pa_payload["ai"]
            sol.pa_ao_ai = pa_payload["ao_ai"]
            sol.pa_po_ai = pa_payload["po_ai"]
            sol.pa_ao_pa = pa_payload["ao_pa"]
            sol.pa_po_pa = pa_payload["po_pa"]
            sol.pa_fr = pa_payload["fr"]
            sol.pa_nd = pa_payload["nd"]
            sol.pa_ugr = pa_payload["ugr"]
            sol.pa_uge = pa_payload["uge"]
            sol.pa_moeda = pa_payload["moeda"]
            sol.pa_ug_exterior = pa_payload["ug_exterior"]

            sol.sol_grupo = normalize_code(row.get("sol_grupo", ""))
            sol.sol_ai = normalize_code(row.get("sol_ai", ""))
            sol.sol_ao_pa = sol_ao_pa
            sol.sol_po_pa = sol_po_pa
            sol.sol_fr = normalize_code(row.get("sol_fr", ""))
            sol.sol_nd = normalize_code(row.get("sol_nd", ""))
            sol.sol_ugr = normalize_code(row.get("sol_ugr", ""))
            sol.sol_uge = normalize_code(row.get("sol_uge", ""))

            sol.solicitado = to_decimal(row.get("solicitado", 0))
            sol.atendido = to_decimal(row.get("atendido", 0))
            sol.em_atendimento = to_decimal(row.get("em_atendimento", 0))
            sol.devolvido = to_decimal(row.get("devolvido", 0))
            sol.saldo_a_atender = to_decimal(row.get("saldo_a_atender", 0))
            sol.nc = normalize_code(row.get("nc", ""))
            sol.updated_at = datetime.now()

    return {
        "file_path": str(file_path),
        "rows_processed": int(len(df)),
        "inserted": inserted,
        "updated": updated,
        "pendentes": pendentes,
        "skipped": skipped,
        "warnings": warnings,
        "usuario": usuario,
    }


def reconcile_pending_after_bd_import(session: Session, usuario: str) -> dict[str, int]:
    pendentes = session.execute(
        select(Solicitacao).where(Solicitacao.pendente_cadastro.is_(True))
    ).scalars()

    reconciled = 0
    total = 0

    for sol in pendentes:
        total += 1
        before = _solicitacao_snapshot(sol)
        id_match = match_id_dim(session, _build_match_payload_from_solicitacao(sol))
        if id_match is None:
            continue
        sol.id = id_match
        sol.pendente_cadastro = False
        sol.pendencia_motivo = None
        sol.updated_at = datetime.now()
        after = _solicitacao_snapshot(sol)
        session.add(
            AuditoriaEvento(
                timestamp=datetime.now(),
                usuario=usuario,
                acao="RECONCILIAR_PENDENCIA",
                entidade="solicitacao",
                chave=sol.numero_solicitacao,
                antes_json=json.dumps(before, ensure_ascii=True),
                depois_json=json.dumps(after, ensure_ascii=True),
                justificativa="Reconciliação automática após importação do BD.",
            )
        )
        reconciled += 1

    remaining = total - reconciled
    return {"checked": total, "reconciled": reconciled, "remaining": remaining}
