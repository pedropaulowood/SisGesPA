from __future__ import annotations

import json
import os
import shutil
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from sqlalchemy import select
try:
    import plotly.graph_objects as go
except Exception:
    go = None

from src.constants import (
    ACAO_APROVAR,
    ACAO_CANCELAR,
    DEFAULT_DB_PATH,
    PROJECT_ROOT,
    ROLE_ADMIN,
    ROLE_APROVADOR,
)
from src.db import create_engine_sqlite, get_session_factory, init_db
from src.etl_bd import import_bd
from src.etl_solcred import import_solcred
from src.models import AuthLog, AuditoriaEvento, IdDim, Saldos, Solicitacao, User
from src.services_aprovacao import calculate_saldo_disponivel, decidir_em_lote, get_formula_config
from src.services_auth import authenticate_user, change_password, create_user, set_user_active
from src.services_dashboard import calcular_kpis_dashboard, get_dashboard_agregado
from src.services_relatorios import default_output_report_path, exportar_relatorio_excel
from src.ui_layout import MenuItem, card, inject_css_theme, render_mobile_backdrop, render_sidebar, render_topbar


st.set_page_config(
    page_title="SisGesPA",
    page_icon=":bar_chart:",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _get_logo_path() -> Path | None:
    candidates = [
        PROJECT_ROOT / "assets" / "logo_subchefia.png",
        Path(r"C:\Users\bk_fa\python\Controle_PA - Codex\logo_setor.png"),
    ]
    for path in candidates:
        if path.exists():
            return path
    return None



def _resolve_db_path() -> Path:
    env_path = os.getenv("SISGESPA_DB_PATH")
    return Path(env_path) if env_path else DEFAULT_DB_PATH


@st.cache_resource
def _get_session_factory():
    db_path = _resolve_db_path()
    engine = create_engine_sqlite(db_path)
    init_db(engine)
    return get_session_factory(engine), db_path


@st.cache_data(ttl=120, show_spinner=False)
def _load_dashboard_dataframe_cached(db_path_str: str, cache_buster: int) -> pd.DataFrame:
    _ = cache_buster
    engine = create_engine_sqlite(Path(db_path_str))
    SessionTmp = get_session_factory(engine)
    try:
        with SessionTmp() as session:
            return get_dashboard_agregado(session)
    finally:
        engine.dispose()


def _bump_dashboard_cache() -> None:
    st.session_state["dashboard_cache_buster"] = int(st.session_state.get("dashboard_cache_buster", 0)) + 1


def _save_uploaded_file(uploaded_file) -> Path:
    if uploaded_file is None:
        raise ValueError("Nenhum arquivo enviado.")
    suffix = Path(uploaded_file.name).suffix or ".xlsx"
    temp_dir = Path(tempfile.mkdtemp(prefix="sisgespa_upload_"))
    target = temp_dir / f"upload{suffix}"
    target.write_bytes(uploaded_file.getvalue())
    return target


def _resolve_import_file(manual_path: str, uploaded_file, source_name: str) -> tuple[Path, bool]:
    manual_path_norm = (manual_path or "").strip()
    if manual_path_norm:
        path = Path(manual_path_norm)
        if not path.exists() or not path.is_file():
            raise ValueError(f"Caminho inválido para {source_name}: {path}")
        return path, False
    if uploaded_file is None:
        raise ValueError(f"Selecione um arquivo de {source_name} ou informe um caminho local.")
    return _save_uploaded_file(uploaded_file), True


def _cleanup_temp_upload(file_path: Path, should_cleanup: bool) -> None:
    if should_cleanup:
        shutil.rmtree(file_path.parent, ignore_errors=True)


def _current_user() -> dict[str, Any] | None:
    return st.session_state.get("auth_user")


def _is_logged_in() -> bool:
    return bool(_current_user())


def _has_role(*roles: str) -> bool:
    user = _current_user()
    if not user:
        return False
    return user.get("perfil") in set(roles)


def _logout() -> None:
    st.session_state.pop("auth_user", None)
    st.session_state.pop("must_change_password", None)
    st.rerun()


def _render_login(SessionLocal) -> None:
    st.title("SisGesPA - Login")
    st.caption("Sistema local para controle de creditos e saldos.")
    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Usuario")
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar")
    if submitted:
        with SessionLocal() as session:
            result = authenticate_user(session, username=username, password=password)
            if not result.ok or result.user is None:
                st.error(result.message)
                return
            st.session_state["auth_user"] = {
                "username": result.user.username,
                "perfil": result.user.perfil,
                "must_change_password": result.user.must_change_password,
            }
            st.success("Login efetuado.")
            st.rerun()


def _render_force_password_change(SessionLocal) -> None:
    user = _current_user()
    if not user:
        return
    st.warning("Troca de senha obrigatoria no primeiro login.")
    with st.form("force_change_password"):
        old_password = st.text_input("Senha atual", type="password")
        new_password = st.text_input("Nova senha", type="password")
        confirm_password = st.text_input("Confirmar nova senha", type="password")
        submit = st.form_submit_button("Atualizar senha")
    if submit:
        if new_password != confirm_password:
            st.error("A confirmacao da nova senha nao confere.")
            return
        try:
            with SessionLocal() as session:
                with session.begin():
                    change_password(
                        session,
                        username=user["username"],
                        old_password=old_password,
                        new_password=new_password,
                        force=False,
                    )
                st.session_state["auth_user"]["must_change_password"] = False
        except ValueError as exc:
            st.error(str(exc))
            return
        except Exception as exc:
            st.error(f"Falha ao atualizar senha: {exc}")
            return
        st.success("Senha alterada com sucesso.")
        st.rerun()


def _load_saldos_dataframe(SessionLocal) -> pd.DataFrame:
    with SessionLocal() as session:
        formula = get_formula_config(session)
        rows: list[dict[str, Any]] = []
        for saldo, dim in session.execute(select(Saldos, IdDim).join(IdDim, Saldos.id == IdDim.id)).all():
            saldo_disp = calculate_saldo_disponivel(saldo, formula)
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
                    "aprovado": float(saldo.aprovado),
                    "saldo_disponivel": float(saldo_disp),
                }
            )
        return pd.DataFrame(rows)


def _load_solicitacoes_dataframe(SessionLocal) -> pd.DataFrame:
    with SessionLocal() as session:
        formula = get_formula_config(session)
        saldos_map: dict[int, dict[str, float]] = {}
        for saldo in session.execute(select(Saldos)).scalars():
            saldos_map[saldo.id] = {
                "saldo_atual": float(calculate_saldo_disponivel(saldo, formula)),
                "valor_pa_aju_tabela": float(saldo.valor_pa_aju),
                "aprovado_tabela": float(saldo.aprovado),
            }

        rows: list[dict[str, Any]] = []
        for sol in session.execute(select(Solicitacao).order_by(Solicitacao.sol_id.desc())).scalars():
            saldo_info = saldos_map.get(int(sol.id)) if sol.id is not None else None
            saldo_atual = saldo_info["saldo_atual"] if saldo_info is not None else None
            rows.append(
                {
                    "sol_id": sol.sol_id,
                    "numero_solicitacao": sol.numero_solicitacao,
                    "id": sol.id,
                    "pendente_cadastro": sol.pendente_cadastro,
                    "pendencia_motivo": sol.pendencia_motivo,
                    "sol_situacao": sol.sol_situacao,
                    "sol_tipo": sol.sol_tipo,
                    "sol_prioridade": sol.sol_prioridade,
                    "sol_origem": sol.sol_origem,
                    "sol_data_criacao": sol.sol_data_criacao,
                    "sol_data_situacao": sol.sol_data_situacao,
                    "pa_grupo": sol.pa_grupo,
                    "pa_ai": sol.pa_ai,
                    "pa_fr": sol.pa_fr,
                    "pa_nd": sol.pa_nd,
                    "pa_ugr": sol.pa_ugr,
                    "pa_uge": sol.pa_uge,
                    "sol_ao_pa": sol.sol_ao_pa,
                    "sol_po_pa": sol.sol_po_pa,
                    "saldo_atual": saldo_atual,
                    "valor_pa_aju_tabela": saldo_info["valor_pa_aju_tabela"] if saldo_info is not None else None,
                    "aprovado_tabela": saldo_info["aprovado_tabela"] if saldo_info is not None else None,
                    "solicitado": float(sol.solicitado),
                    "atendido": float(sol.atendido),
                    "devolvido": float(sol.devolvido),
                    "saldo_a_atender": float(sol.saldo_a_atender),
                }
            )
        return pd.DataFrame(rows)


def _format_money_ptbr(value: Any) -> str:
    try:
        num = float(value)
    except Exception:
        num = 0.0
    return f"{num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _format_money_ptbr_optional(value: Any) -> str:
    if value is None:
        return "-"
    try:
        if pd.isna(value):
            return "-"
    except Exception:
        pass
    return _format_money_ptbr(value)


def _build_dashboard_gauge(percentual: float):
    if go is None:
        return None
    pct = max(0.0, min(float(percentual), 100.0))
    restante = max(0.0, 100.0 - pct)

    fig = go.Figure(
        data=[
            go.Pie(
                values=[pct, restante],
                hole=0.68,
                sort=False,
                direction="clockwise",
                marker={
                    "colors": ["#0b4f8a", "#a5b6c9"],
                    "line": {"color": "#f8fbff", "width": 3},
                },
                textinfo="none",
                hovertemplate="%{value:.2f}%<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        margin={"l": 12, "r": 12, "t": 12, "b": 12},
        showlegend=False,
        paper_bgcolor="#ffffff",
        annotations=[
            {
                "text": f"<b>{pct:.2f}%</b><br><span style='font-size:13px;color:#2f4f6b;'>Aprovado</span>",
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
                "font": {"size": 32, "color": "#0b2745"},
            }
        ],
    )
    return fig


def _page_dashboard(SessionLocal, db_path: Path) -> None:
    _ = SessionLocal
    st.subheader("Dashboard")
    st.caption("Visao do PA AJU com filtros por ODS Meta Sigla, IRP PA, AO do PA e Grupo.")

    cache_buster = int(st.session_state.get("dashboard_cache_buster", 0))
    try:
        df = _load_dashboard_dataframe_cached(str(db_path), cache_buster)
    except Exception as exc:
        st.error(f"Falha ao carregar dashboard: {exc}")
        return

    if df.empty:
        st.info("Sem dados para o dashboard. Importe BD e SolCred para visualizar.")
        return

    col_f_ods, col_f_irp, col_f_ao, col_f_grupo = st.columns(4)
    ods_options = sorted([x for x in df["ods_meta_sigla"].dropna().unique().tolist() if str(x).strip() != ""])
    irp_options = sorted([x for x in df["irp_pa"].dropna().unique().tolist() if str(x).strip() != ""])
    ao_options = sorted([x for x in df["ao_pa"].dropna().unique().tolist() if str(x).strip() != ""])
    grupo_options = sorted([x for x in df["grupo"].dropna().unique().tolist() if str(x).strip() != ""])
    filtro_ods = col_f_ods.multiselect("Filtro ODS (meta sigla)", options=ods_options, default=[])
    filtro_irp = col_f_irp.multiselect("Filtro IRP PA", options=irp_options, default=[])
    filtro_ao = col_f_ao.multiselect("Filtro AO do PA", options=ao_options, default=[])
    filtro_grupo = col_f_grupo.multiselect("Filtro Grupo", options=grupo_options, default=[])

    filtered = df.copy()
    if filtro_ods:
        filtered = filtered[filtered["ods_meta_sigla"].isin(filtro_ods)]
    if filtro_irp:
        filtered = filtered[filtered["irp_pa"].isin(filtro_irp)]
    if filtro_ao:
        filtered = filtered[filtered["ao_pa"].isin(filtro_ao)]
    if filtro_grupo:
        filtered = filtered[filtered["grupo"].isin(filtro_grupo)]

    if filtered.empty:
        st.warning("Nenhum registro encontrado para os filtros selecionados.")
        return

    kpis = calcular_kpis_dashboard(filtered)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Valor PA AJU (Total)", _format_money_ptbr(kpis["valor_pa_aju_total"]))
    k2.metric("Valor Aprovado", _format_money_ptbr(kpis["valor_aprovado"]))
    k3.metric("Saldo Atual", _format_money_ptbr(kpis["saldo_atual"]))
    k4.metric("% Aprovado", f"{kpis['percentual_aprovado']:.2f}%")

    col_gauge, col_info = st.columns([1.1, 1.0])
    with col_gauge:
        with st.container(border=True):
            st.markdown("#### Gauge de Aprovacao")
            fig = _build_dashboard_gauge(kpis["percentual_aprovado"])
            if fig is None:
                st.warning("Plotly nao instalado. Execute: python -m pip install -r requirements.txt")
                st.progress(min(int(kpis["percentual_aprovado"]), 100))
            else:
                st.plotly_chart(
                    fig,
                    use_container_width=True,
                    config={"displayModeBar": False},
                )
    with col_info:
        with st.container(border=True):
            st.markdown("#### Referencias do Calculo")
            st.markdown("- Sol.Lib.Cred. = Liberado + Bandeja DGOM")
            st.markdown("- Valor do PA Aju = Valor do PA Ini + Dif. Planejamento(Real)")
            st.markdown("- % Aprovado = Valor Aprovado / Valor PA AJU")

    detalhamento = filtered.copy()
    detalhamento["valor_pa_aju"] = detalhamento["valor_pa_aju"].map(_format_money_ptbr)
    detalhamento["valor_aprovado"] = detalhamento["valor_aprovado"].map(_format_money_ptbr)
    detalhamento["saldo_atual"] = detalhamento["saldo_atual"].map(_format_money_ptbr)
    detalhamento["percentual_aprovado"] = detalhamento["percentual_aprovado"].map(lambda x: f"{float(x):.2f}%")
    detalhamento = detalhamento.drop(columns=["valor_solicitado"], errors="ignore")
    detalhamento = detalhamento[
        [
            "ods_meta_sigla",
            "irp_pa",
            "ao_pa",
            "grupo",
            "valor_pa_aju",
            "valor_aprovado",
            "saldo_atual",
            "percentual_aprovado",
        ]
    ]
    detalhamento = detalhamento.rename(
        columns={
            "ods_meta_sigla": "ODS",
            "irp_pa": "IRP PA",
            "ao_pa": "AO",
            "grupo": "GRUPO",
            "valor_pa_aju": "Valor_PA_AJU",
            "valor_aprovado": "Valor_Aprovado",
            "saldo_atual": "Saldo_Atual",
            "percentual_aprovado": "Percentual_Aprovado",
        }
    )
    st.markdown("#### Detalhamento por ODS, IRP PA, AO e Grupo")
    st.dataframe(detalhamento, use_container_width=True, hide_index=True)


def _page_importar(SessionLocal) -> None:
    st.subheader("Importar Arquivos")
    st.caption("Importe BD (saldos) e SolCred (solicitacoes).")

    usuario = _current_user()["username"]

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**BD**")
        bd_upload = st.file_uploader("Arquivo BD (.xls/.xlsx)", type=["xls", "xlsx"], key="bd_upload")
        bd_path_manual = st.text_input("Ou caminho local BD", value="", key="bd_path_manual")
        if st.button("Importar BD", key="btn_import_bd"):
            file_path: Path | None = None
            should_cleanup = False
            try:
                file_path, should_cleanup = _resolve_import_file(bd_path_manual, bd_upload, "BD")
                with SessionLocal() as session:
                    summary = import_bd(session, file_path=file_path, usuario=usuario)
                _bump_dashboard_cache()
                st.success("BD importado com sucesso.")
                st.json(summary)
                pending_remaining = int(summary.get("pending_remaining", 0))
                pending_reconciled = int(summary.get("pending_reconciled", 0))
                if pending_remaining > 0:
                    st.warning(
                        f"Pendencias de cadastro apos importacao do BD: {pending_remaining} "
                        f"(reconciliadas: {pending_reconciled})."
                    )
                else:
                    st.info(f"Nenhuma pendencia de cadastro restante (reconciliadas: {pending_reconciled}).")
            except Exception as exc:
                st.error(f"Falha na importacao do BD: {exc}")
            finally:
                if file_path is not None:
                    _cleanup_temp_upload(file_path, should_cleanup)

    with col2:
        st.markdown("**SolCred**")
        sol_upload = st.file_uploader("Arquivo SolCred (.xls/.xlsx)", type=["xls", "xlsx"], key="sol_upload")
        sol_path_manual = st.text_input("Ou caminho local SolCred", value="", key="sol_path_manual")
        if st.button("Importar SolCred", key="btn_import_sol"):
            file_path: Path | None = None
            should_cleanup = False
            try:
                file_path, should_cleanup = _resolve_import_file(sol_path_manual, sol_upload, "SolCred")
                with SessionLocal() as session:
                    summary = import_solcred(session, file_path=file_path, usuario=usuario)
                _bump_dashboard_cache()
                st.success("SolCred importado com sucesso.")
                st.json(summary)
                pendentes = int(summary.get("pendentes", 0))
                if pendentes > 0:
                    st.warning(f"Foram encontradas {pendentes} pendencia(s) de cadastro no SolCred importado.")
                else:
                    st.info("Nenhuma pendencia de cadastro no SolCred importado.")
                if summary.get("warnings"):
                    st.warning("Avisos encontrados durante a importacao.")
                    st.write(summary["warnings"])
            except Exception as exc:
                st.error(f"Falha na importacao do SolCred: {exc}")
            finally:
                if file_path is not None:
                    _cleanup_temp_upload(file_path, should_cleanup)


def _page_saldos(SessionLocal) -> None:
    st.subheader("Painel de Saldos")
    df = _load_saldos_dataframe(SessionLocal)
    if df.empty:
        st.info("Sem registros em saldos.")
        return

    filters = {}
    for col in ["grupo", "ai", "ugr", "uge", "nd", "fr"]:
        opts = sorted([x for x in df[col].dropna().unique().tolist() if x != ""])
        selected = st.multiselect(f"Filtro {col.upper()}", options=opts, default=[])
        if selected:
            filters[col] = selected

    for col, values in filters.items():
        df = df[df[col].isin(values)]

    negativos = int((df["saldo_disponivel"] < 0).sum())
    baixos = int((df["saldo_disponivel"] <= 0).sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("Registros", len(df))
    c2.metric("Saldo <= 0", baixos)
    c3.metric("Saldo negativo", negativos)

    if baixos > 0:
        st.warning("Existem registros com saldo disponivel menor ou igual a zero.")
    display_df = df[
        [
            "id",
            "grupo",
            "ai",
            "ao_pa",
            "po_pa",
            "fr",
            "nd",
            "ugr",
            "uge",
            "moeda",
            "valor_pa_aju",
            "aprovado",
            "saldo_disponivel",
        ]
    ].copy()
    display_df["valor_pa_aju"] = display_df["valor_pa_aju"].map(_format_money_ptbr)
    display_df["aprovado"] = display_df["aprovado"].map(_format_money_ptbr)
    display_df["saldo_disponivel"] = display_df["saldo_disponivel"].map(_format_money_ptbr)
    display_df = display_df.rename(
        columns={
            "id": "ID",
            "grupo": "GRUPO",
            "ai": "AI",
            "ao_pa": "AO PA",
            "po_pa": "PO PA",
            "fr": "FR",
            "nd": "ND",
            "ugr": "UGR",
            "uge": "UGE",
            "moeda": "MOEDA",
            "valor_pa_aju": "VALOR PA AJU",
            "aprovado": "APROVADO",
            "saldo_disponivel": "SALDO DISPONIVEL",
        }
    )
    st.dataframe(display_df, use_container_width=True, hide_index=True)


def _page_solicitacoes(SessionLocal) -> None:
    st.subheader("Painel de Solicitacoes")

    feedback = st.session_state.pop("solicitacoes_feedback", None)
    if feedback:
        level, message = feedback
        if level == "success":
            st.success(message)
        elif level == "error":
            st.error(message)

    df = _load_solicitacoes_dataframe(SessionLocal)
    if df.empty:
        st.info("Sem solicitacoes carregadas.")
        return

    def _normalizar_situacao(value: Any) -> str:
        txt = unicodedata.normalize("NFKD", str(value or ""))
        txt = txt.encode("ascii", "ignore").decode("ascii")
        txt = txt.strip().upper()
        txt = txt.replace("-", " ").replace("_", " ")
        txt = " ".join(txt.split())
        return txt

    def _is_em_analise(value: Any) -> bool:
        return _normalizar_situacao(value) == "EM ANALISE"

    filtered_df = df[df["sol_situacao"].map(_is_em_analise)].copy()
    filtered_df = filtered_df.sort_values("sol_id", ascending=False).reset_index(drop=True)

    if filtered_df.empty:
        st.info("Nenhuma solicitacao em analise.")
        return

    saldo_atual_num = pd.to_numeric(filtered_df["saldo_atual"], errors="coerce")
    valor_pa_aju_tabela_num = pd.to_numeric(filtered_df["valor_pa_aju_tabela"], errors="coerce")
    aprovado_tabela_num = pd.to_numeric(filtered_df["aprovado_tabela"], errors="coerce")
    valor_solicitado_num = pd.to_numeric(filtered_df["solicitado"], errors="coerce")
    saldo_3_15 = (valor_pa_aju_tabela_num * (3.0 / 15.0)) - aprovado_tabela_num
    sinal = saldo_3_15 >= valor_solicitado_num
    tabela_df = pd.DataFrame(
        {
            "Numero": filtered_df["numero_solicitacao"],
            "Grupo": filtered_df["pa_grupo"],
            "AI": filtered_df["pa_ai"],
            "AO PA": filtered_df["sol_ao_pa"],
            "PO PA": filtered_df["sol_po_pa"],
            "FR": filtered_df["pa_fr"],
            "ND": filtered_df["pa_nd"],
            "UGR": filtered_df["pa_ugr"],
            "UGE": filtered_df["pa_uge"],
            "Saldo Atual": saldo_atual_num.map(_format_money_ptbr_optional),
            "Saldo 3/15": saldo_3_15.map(_format_money_ptbr_optional),
            "Valor Solicitado": filtered_df["solicitado"].map(_format_money_ptbr),
            "Sinal": sinal.map(lambda ok: "🟢" if bool(ok) else "🔴"),
        }
    )
    can_decide = _has_role(ROLE_ADMIN, ROLE_APROVADOR)

    st.markdown('<div class="sis-aprov-panel-title">Lista de pedidos</div>', unsafe_allow_html=True)
    st.caption("Saldo 3/15 = (Valor PA AJU da tabela saldos * 3) / 15 - Aprovado.")
    st.caption("Sinal: 🟢 quando Saldo 3/15 >= Valor Solicitado; 🔴 caso contrario.")
    if can_decide:
        st.caption("Marque as linhas e use os botoes para aprovar/cancelar.")
        editor_df = tabela_df.copy()
        editor_df.insert(0, "Aprovar", False)
        editor_version = int(st.session_state.get("sol_aprov_editor_version", 0))
        editor_key = f"sol_aprov_editor_{editor_version}"
        edited_df = st.data_editor(
            editor_df,
            key=editor_key,
            hide_index=True,
            use_container_width=True,
            height=700,
            disabled=[col for col in editor_df.columns if col != "Aprovar"],
            column_config={
                "Aprovar": st.column_config.CheckboxColumn(
                    "Aprovar",
                    help="Marque para aprovar automaticamente esta solicitacao.",
                )
            },
        )

        checked_numbers = edited_df[edited_df["Aprovar"] == True]["Numero"].astype(str).tolist()
        st.caption(f"Marcadas: {len(checked_numbers)}")
        just_cancel = st.text_area(
            "Justificativa para cancelar marcadas (obrigatoria)",
            key="lote_cancel_just_checked",
            height=80,
        )
        act_col1, act_col2 = st.columns(2)
        click_aprovar = act_col1.button(
            "Aprovar marcadas",
            key="btn_aprovar_marcadas",
            type="primary",
            use_container_width=True,
        )
        click_cancelar = act_col2.button(
            "Cancelar marcadas",
            key="btn_cancelar_marcadas",
            use_container_width=True,
        )

        if click_aprovar or click_cancelar:
            if not checked_numbers:
                st.session_state["solicitacoes_feedback"] = ("error", "Nenhuma solicitacao marcada.")
                st.rerun()

            aptas = filtered_df[
                (filtered_df["numero_solicitacao"].astype(str).isin(checked_numbers))
                & (filtered_df["pendente_cadastro"] == False)
            ]["numero_solicitacao"].astype(str).tolist()
            skipped = [num for num in checked_numbers if num not in set(aptas)]

            if not aptas:
                st.session_state["solicitacoes_feedback"] = (
                    "error",
                    "As solicitacoes marcadas nao estao aptas para decisao.",
                )
                st.session_state["sol_aprov_editor_version"] = editor_version + 1
                st.rerun()

            acao_lote = ACAO_APROVAR if click_aprovar else ACAO_CANCELAR
            justificativa_lote = ""
            if acao_lote == ACAO_CANCELAR:
                justificativa_lote = (just_cancel or "").strip()
                if not justificativa_lote:
                    st.session_state["solicitacoes_feedback"] = (
                        "error",
                        "Justificativa obrigatoria para CANCELAR.",
                    )
                    st.rerun()

            try:
                with SessionLocal() as session:
                    decidir_em_lote(
                        session=session,
                        numeros=aptas,
                        acao=acao_lote,
                        justificativa=justificativa_lote,
                        usuario=_current_user()["username"],
                    )
                _bump_dashboard_cache()
                acao_label = "aprovada(s)" if acao_lote == ACAO_APROVAR else "cancelada(s)"
                msg = f"{len(aptas)} solicitacao(oes) {acao_label}."
                if skipped:
                    msg = f"{msg} Ignoradas (nao aptas): {', '.join(skipped)}."
                st.session_state["solicitacoes_feedback"] = ("success", msg)
            except Exception as exc:
                st.session_state["solicitacoes_feedback"] = (
                    "error",
                    f"Falha ao aplicar acao em lote: {exc}",
                )
            st.session_state["sol_aprov_editor_version"] = editor_version + 1
            st.rerun()
    else:
        st.dataframe(tabela_df, use_container_width=True, height=700)


def _page_relatorios(SessionLocal) -> None:
    st.subheader("Relatorios")
    st.caption("Exportacao inicial em Excel.")
    default_path = str(default_output_report_path())
    output_path = st.text_input("Arquivo de saida (.xlsx)", value=default_path)

    filtros: dict[str, Any] = {}
    grupo = st.text_input("Filtro grupo (opcional)", value="")
    situacao = st.text_input("Filtro situacao (opcional)", value="")
    numero = st.text_input("Filtro numero solicitacao (opcional)", value="")
    if grupo:
        filtros["grupo"] = grupo
        filtros["pa_grupo"] = grupo
    if situacao:
        filtros["sol_situacao"] = situacao
    if numero:
        filtros["numero_solicitacao"] = numero
        filtros["chave"] = numero

    if st.button("Gerar relatorio Excel", key="btn_export_excel"):
        try:
            with SessionLocal() as session:
                path = exportar_relatorio_excel(session, filtros=filtros, output_path=output_path)
            st.success(f"Relatorio gerado: {path}")
            file_bytes = Path(path).read_bytes()
            st.download_button("Baixar relatorio", file_bytes, file_name=Path(path).name)
        except Exception as exc:
            st.error(f"Falha ao exportar relatorio: {exc}")


def _auditoria_event_matches_id(event: AuditoriaEvento, id_filter: str) -> bool:
    id_norm = (id_filter or "").strip()
    if not id_norm:
        return True
    if id_norm in str(event.chave or ""):
        return True
    for payload_raw in (event.antes_json, event.depois_json):
        if not payload_raw:
            continue
        try:
            payload = json.loads(payload_raw)
        except Exception:
            continue
        if str(payload.get("id") or "").strip() == id_norm:
            return True
    return False


def _page_auditoria(SessionLocal) -> None:
    st.subheader("Auditoria")
    numero = st.text_input("Buscar por numero da solicitacao")
    id_dim = st.text_input("Buscar por ID (id_dim)")

    with SessionLocal() as session:
        stmt = select(AuditoriaEvento).order_by(AuditoriaEvento.timestamp.desc())
        events = session.execute(stmt).scalars().all()
    rows = []
    for event in events:
        if numero and numero not in str(event.chave or ""):
            continue
        if id_dim and not _auditoria_event_matches_id(event, id_dim):
            continue
        rows.append(
            {
                "timestamp": event.timestamp,
                "usuario": event.usuario,
                "acao": event.acao,
                "entidade": event.entidade,
                "chave": event.chave,
                "justificativa": event.justificativa,
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        st.info("Nenhum evento encontrado para os filtros.")
    else:
        st.dataframe(df, use_container_width=True)
    st.caption("Eventos sao append-only; nao existe tela de edicao/exclusao.")


def _page_admin(SessionLocal) -> None:
    st.subheader("Administracao")
    if not _has_role(ROLE_ADMIN):
        st.error("Acesso restrito ao perfil ADMIN.")
        return

    st.markdown("### Usuarios")
    with st.form("form_create_user"):
        username = st.text_input("Novo username")
        password = st.text_input("Senha inicial", type="password")
        perfil = st.selectbox("Perfil", ["ADMIN", "AVALIADOR", "APROVADOR", "CONSULTA"])
        must_change = st.checkbox("Exigir troca de senha no primeiro login", value=True)
        submit_create = st.form_submit_button("Criar usuario")
    if submit_create:
        try:
            with SessionLocal() as session:
                with session.begin():
                    create_user(
                        session=session,
                        username=username,
                        password=password,
                        perfil=perfil,
                        must_change_password=must_change,
                    )
            st.success("Usuario criado com sucesso.")
        except Exception as exc:
            st.error(f"Erro ao criar usuario: {exc}")

    with SessionLocal() as session:
        users = session.execute(select(User).order_by(User.username.asc())).scalars().all()
    users_df = pd.DataFrame(
        [
            {
                "username": u.username,
                "perfil": u.perfil,
                "is_active": u.is_active,
                "must_change_password": u.must_change_password,
                "updated_at": u.updated_at,
            }
            for u in users
        ]
    )
    st.dataframe(users_df, use_container_width=True)

    st.markdown("### Ativar/Desativar Usuario")
    user_names = [u.username for u in users]
    if user_names:
        selected_user = st.selectbox("Usuario", options=user_names, key="admin_user_status")
        status_action = st.radio("Acao", options=["Ativar", "Desativar"], horizontal=True, key="admin_status_action")
        if st.button("Aplicar status", key="btn_apply_user_status"):
            try:
                with SessionLocal() as session:
                    with session.begin():
                        set_user_active(session, selected_user, is_active=(status_action == "Ativar"))
                st.success("Status atualizado.")
            except Exception as exc:
                st.error(f"Erro ao atualizar status: {exc}")

    st.markdown("### Reset de Senha")
    if user_names:
        reset_user = st.selectbox("Usuario para reset", options=user_names, key="admin_reset_user")
        reset_pwd = st.text_input("Nova senha temporaria", type="password", key="admin_reset_pwd")
        if st.button("Resetar senha", key="btn_reset_pwd"):
            try:
                with SessionLocal() as session:
                    with session.begin():
                        change_password(
                            session,
                            username=reset_user,
                            old_password="",
                            new_password=reset_pwd,
                            force=True,
                        )
                        target = session.execute(select(User).where(User.username == reset_user)).scalar_one()
                        target.must_change_password = True
                st.success("Senha resetada com troca obrigatoria habilitada.")
            except Exception as exc:
                st.error(f"Erro no reset de senha: {exc}")

    st.markdown("### Regra de Saldo")
    st.info(
        "Regras vigentes: Sol.Lib.Cred. = Liberado + Bandeja DGOM | "
        "Valor do PA Aju = Liberado + A Atender | "
        "Valor do PA Aju = Valor do PA Ini + Dif. Planejamento(Real)."
    )
    st.markdown("### Logs de Autenticacao")
    with SessionLocal() as session:
        logs = session.execute(select(AuthLog).order_by(AuthLog.timestamp.desc()).limit(200)).scalars().all()
    log_df = pd.DataFrame(
        [
            {
                "timestamp": log.timestamp,
                "username": log.username,
                "sucesso": log.sucesso,
                "motivo": log.motivo,
                "ip_origem": log.ip_origem,
            }
            for log in logs
        ]
    )
    st.dataframe(log_df, use_container_width=True)


def main() -> None:
    SessionLocal, db_path = _get_session_factory()
    st.session_state.setdefault("drawer_open", True)

    if not _is_logged_in():
        inject_css_theme(drawer_open=False, authenticated=False)
        with card("Login"):
            _render_login(SessionLocal)
        return

    st.session_state["drawer_open"] = True
    inject_css_theme(drawer_open=bool(st.session_state.get("drawer_open", False)), authenticated=True)
    render_mobile_backdrop(bool(st.session_state.get("drawer_open", False)))

    topbar_events = render_topbar(_current_user(), app_name="SisGesPA")
    if topbar_events.get("logout"):
        _logout()
        return

    menu_items = [
        MenuItem(id="dashboard", label="Dashboard", icon="\U0001F3E0"),
        MenuItem(id="importar", label="Importar Arquivos", icon="\U0001F4E5"),
        MenuItem(id="saldos", label="Painel de Saldos", icon="\U0001F4B0"),
        MenuItem(id="solicitacoes", label="Painel de Solicitacoes", icon="\U0001F9FE"),
        MenuItem(id="relatorios", label="Relatorios", icon="\U0001F4CA"),
        MenuItem(id="auditoria", label="Auditoria", icon="\U0001F553"),
        MenuItem(id="admin", label="Admin", icon="\u2699"),
    ]
    selected_id = st.session_state.get("sis_nav_radio", menu_items[0].id)
    selected_id = render_sidebar(
        menu_items=menu_items,
        selected_id=selected_id,
        user=_current_user(),
        logo_path=_get_logo_path(),
        app_title="EMA-20",
        app_subtitle="Subchefia de Orcamento e Plano Diretor",
        db_path=str(db_path),
    )

    if _current_user().get("must_change_password", False):
        with card("Troca de Senha"):
            _render_force_password_change(SessionLocal)
        return

    with card():
        if selected_id == "dashboard":
            _page_dashboard(SessionLocal, db_path)
        elif selected_id == "importar":
            if not _has_role(ROLE_ADMIN):
                st.error("Somente ADMIN pode importar arquivos.")
                return
            _page_importar(SessionLocal)
        elif selected_id == "saldos":
            _page_saldos(SessionLocal)
        elif selected_id == "solicitacoes":
            _page_solicitacoes(SessionLocal)
        elif selected_id == "relatorios":
            _page_relatorios(SessionLocal)
        elif selected_id == "auditoria":
            _page_auditoria(SessionLocal)
        elif selected_id == "admin":
            _page_admin(SessionLocal)


if __name__ == "__main__":
    main()


