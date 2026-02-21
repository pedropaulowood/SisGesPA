from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from src.models import IdDim, Saldos
from src.utils_money import normalize_code, normalize_header, to_decimal


_BD_COLUMN_MAP = {
    "id": "bd_id_origem",
    "grupo": "grupo",
    "ai": "ai",
    "titulo_da_ai": "titulo_ai",
    "ao_da_ai": "ao_ai",
    "po_da_ai": "po_ai",
    "ao_do_pa": "ao_pa",
    "po_do_pa": "po_pa",
    "fr": "fr",
    "nd": "nd",
    "ugr_codigo": "ugr",
    "ugr_sigla": "ugr_sigla",
    "uge_codigo": "uge",
    "uge_sigla": "uge_sigla",
    "moeda": "moeda",
    "ug_exterior": "ug_exterior",
    "valor_do_pa_ini": "valor_pa_ini",
    "valor_do_pa_aju": "valor_pa_aju",
    "dif_planejamento_real": "dif_planejamento_real",
    "sol_lib_cred": "sol_lib_cred",
    "sol_bloq": "sol_bloq",
    "sol_desbloq": "sol_desbloq",
    "aprovado": "aprovado",
    "liberado": "liberado",
    "bloqueado": "bloqueado",
    "corte": "corte",
    "devolvido": "devolvido",
    "saldo": "saldo",
    "pedidos_em_tramite": "pedidos_em_tramite",
    "bandeja_dgom": "bandeja_dgom",
    "a_atender": "a_atender",
    "gerente": "gerente",
    "ods": "ods",
    "aprovador": "aprovador",
    "irp_pa": "irp_pa",
    "gerente_de_meta_codigo": "gerente_meta_codigo",
    "gerente_de_meta_sigla": "gerente_meta_sigla",
    "ods_da_meta_codigo": "ods_meta_codigo",
    "ods_da_meta_sigla": "ods_meta_sigla",
}

_ID_FIELDS = ["grupo", "ai", "ao_ai", "po_ai", "ao_pa", "po_pa", "fr", "nd", "ugr", "uge", "moeda", "ug_exterior"]
_SALDO_NUMERIC_FIELDS = [
    "valor_pa_ini",
    "valor_pa_aju",
    "dif_planejamento_real",
    "sol_lib_cred",
    "sol_bloq",
    "sol_desbloq",
    "aprovado",
    "liberado",
    "bloqueado",
    "corte",
    "devolvido",
    "saldo",
    "pedidos_em_tramite",
    "bandeja_dgom",
    "a_atender",
]
_SALDO_TEXT_FIELDS = [
    "bd_id_origem",
    "titulo_ai",
    "ugr_sigla",
    "uge_sigla",
    "gerente",
    "ods",
    "aprovador",
    "irp_pa",
    "gerente_meta_codigo",
    "gerente_meta_sigla",
    "ods_meta_codigo",
    "ods_meta_sigla",
]


def _convert_xls_to_xlsx(xls_path: Path) -> Path:
    soffice = shutil.which("soffice")
    if not soffice:
        raise RuntimeError(
            "Falha ao abrir .xls. Instale o LibreOffice (comando soffice) ou converta o arquivo para .xlsx."
        )
    temp_dir = Path(tempfile.mkdtemp(prefix="sisgespa_xls_"))
    cmd = [soffice, "--headless", "--convert-to", "xlsx", "--outdir", str(temp_dir), str(xls_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RuntimeError(
            "Não foi possível converter .xls para .xlsx via LibreOffice. "
            f"Saída: {proc.stderr or proc.stdout}"
        )
    converted = temp_dir / f"{xls_path.stem}.xlsx"
    if not converted.exists():
        files = list(temp_dir.glob("*.xlsx"))
        if not files:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise RuntimeError("Conversão .xls executada, mas nenhum arquivo .xlsx foi gerado.")
        converted = files[0]
    return converted


def load_excel_with_fallback(
    file_path: str | Path,
    sheet_name: int | str = 0,
    header: int | None = 0,
) -> pd.DataFrame:
    path = Path(file_path)
    try:
        return pd.read_excel(path, sheet_name=sheet_name, header=header)
    except Exception as exc:
        if path.suffix.lower() != ".xls":
            raise
        converted: Path | None = None
        try:
            converted = _convert_xls_to_xlsx(path)
            return pd.read_excel(converted, sheet_name=sheet_name, header=header)
        except Exception as convert_exc:
            raise RuntimeError(
                f"Falha ao ler arquivo {path}. "
                "Se for .xls, instale xlrd (`pip install xlrd`) ou converta para .xlsx."
            ) from convert_exc
        finally:
            if converted is not None:
                shutil.rmtree(converted.parent, ignore_errors=True)


def find_header_row_by_token(df_raw: pd.DataFrame, token: str = "#Id") -> int:
    token_norm = normalize_code(token).lower().replace("#", "")
    for idx, row in df_raw.iterrows():
        for value in row.tolist():
            value_norm = normalize_code(value).lower().replace("#", "")
            if value_norm == token_norm:
                return int(idx)
    raise ValueError(f"Cabeçalho não encontrado: token {token!r}")


def _canonicalize_bd_df(df: pd.DataFrame) -> pd.DataFrame:
    renamed: dict[Any, str] = {}
    for col in df.columns:
        normalized = normalize_header(col)
        if normalized in _BD_COLUMN_MAP:
            renamed[col] = _BD_COLUMN_MAP[normalized]
    output = df.rename(columns=renamed).copy()
    for needed in _ID_FIELDS:
        if needed not in output.columns:
            output[needed] = ""
    return output


def _id_payload_from_row(row: pd.Series) -> dict[str, str]:
    payload = {field: normalize_code(row.get(field, "")) for field in _ID_FIELDS}
    for field in ("ao_ai", "po_ai", "ao_pa", "po_pa"):
        value = payload.get(field, "")
        if value.isdigit() and len(value) <= 4:
            payload[field] = value.zfill(4)
    return payload


def _id_key(payload: dict[str, str]) -> tuple[str, ...]:
    return tuple(payload[field] for field in _ID_FIELDS)


def _get_or_create_id_dim(session: Session, payload: dict[str, str], cache: dict[tuple[str, ...], IdDim]) -> tuple[IdDim, bool]:
    key = _id_key(payload)
    cached = cache.get(key)
    if cached:
        return cached, False

    filters = [getattr(IdDim, field) == payload[field] for field in _ID_FIELDS]
    existing = session.execute(select(IdDim).where(and_(*filters))).scalar_one_or_none()
    if existing is not None:
        cache[key] = existing
        return existing, False

    obj = IdDim(**payload)
    session.add(obj)
    session.flush()
    cache[key] = obj
    return obj, True


def import_bd(session: Session, file_path: str | Path, usuario: str) -> dict[str, Any]:
    df_raw = load_excel_with_fallback(file_path, sheet_name=0, header=None)
    header_idx = find_header_row_by_token(df_raw, "#Id")
    df = load_excel_with_fallback(file_path, sheet_name=0, header=header_idx)
    df = df.dropna(how="all")
    df = _canonicalize_bd_df(df)

    inserted_id = 0
    inserted_saldo = 0
    updated_saldo = 0
    skipped = 0
    cache: dict[tuple[str, ...], IdDim] = {}

    with session.begin():
        for _, row in df.iterrows():
            id_payload = _id_payload_from_row(row)
            if not any(id_payload.values()):
                skipped += 1
                continue

            id_dim, is_new = _get_or_create_id_dim(session, id_payload, cache)
            if is_new:
                inserted_id += 1

            saldo = session.get(Saldos, id_dim.id)
            if saldo is None:
                saldo = Saldos(id=id_dim.id)
                session.add(saldo)
                inserted_saldo += 1
            else:
                updated_saldo += 1

            for field in _SALDO_TEXT_FIELDS:
                setattr(saldo, field, normalize_code(row.get(field, "")))
            for field in _SALDO_NUMERIC_FIELDS:
                setattr(saldo, field, to_decimal(row.get(field, 0)))

        from src.etl_solcred import reconcile_pending_after_bd_import

        reconcile = reconcile_pending_after_bd_import(session, usuario=usuario or "system_import_bd")

    return {
        "file_path": str(file_path),
        "header_row_index": header_idx,
        "rows_processed": int(len(df)),
        "id_dim_inserted": inserted_id,
        "saldos_inserted": inserted_saldo,
        "saldos_updated": updated_saldo,
        "rows_skipped": skipped,
        "pending_reconciled": reconcile.get("reconciled", 0),
        "pending_remaining": reconcile.get("remaining", 0),
    }
