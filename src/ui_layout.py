from __future__ import annotations

import html
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import streamlit as st


@dataclass(frozen=True)
class MenuItem:
    id: str
    label: str
    icon: str
    roles_allowed: tuple[str, ...] | None = None


def _user_display(user: dict[str, Any] | None) -> tuple[str, str, str]:
    if not user:
        return ("Local", "", "L")
    username = str(user.get("username") or "Local")
    perfil = str(user.get("perfil") or "")
    parts = [part for part in username.strip().split() if part]
    if len(parts) >= 2:
        initials = (parts[0][0] + parts[-1][0]).upper()
    elif parts:
        initials = parts[0][:2].upper()
    else:
        initials = "L"
    return (username, perfil, initials)


def _render_layout_state(drawer_open: bool, authenticated: bool) -> None:
    drawer_class = "drawer-open" if drawer_open else "drawer-closed"
    auth_class = "auth-on" if authenticated else "auth-off"
    st.markdown(
        (
            '<div id="sis-layout-state" '
            f'class="sis-layout-state {drawer_class} {auth_class}" '
            'aria-hidden="true"></div>'
        ),
        unsafe_allow_html=True,
    )


def inject_css_theme(drawer_open: bool, authenticated: bool) -> None:
    # Always render current runtime state; CSS uses this marker for drawer/auth behavior.
    _render_layout_state(drawer_open=drawer_open, authenticated=authenticated)

    # Idempotent injection by version: reinjeta somente quando a versao do tema muda.
    css_version = "2026-02-20-sidebar-navy-v2"
    if st.session_state.get("_sis_css_theme_version") == css_version:
        return
    st.session_state["_sis_css_theme_version"] = css_version

    st.markdown(
        """
        <style>
            :root {
                --bg: #dfe7f1;
                --card-bg: #f8fbff;
                --sidebar-bg: #001a45;
                --topbar-bg: #f9fcff;
                --text-primary: #112a45;
                --text-muted: #4b6178;
                --accent: #1f5f96;
                --border: #d2ddea;
                --shadow: 0 4px 12px rgba(11, 36, 64, 0.05);
                --sidebar-bg-gradient: linear-gradient(180deg, var(--sidebar-bg) 0%, #00265f 100%);
            }

            .sis-layout-state {
                display: none !important;
            }

            header[data-testid="stHeader"] {
                background: transparent !important;
                border: 0 !important;
            }

            #MainMenu {
                visibility: hidden !important;
            }

            div[data-testid="stToolbar"] {
                visibility: hidden !important;
                height: 0 !important;
                position: fixed !important;
            }

            [data-testid="stAppViewContainer"] {
                background: linear-gradient(180deg, var(--bg) 0%, #ebf1f7 100%) !important;
            }

            [data-testid="stMainBlockContainer"] {
                max-width: none !important;
                padding-top: 0.6rem !important;
                padding-left: 1.15rem !important;
                padding-right: 1.15rem !important;
                padding-bottom: 1rem !important;
            }

            body:has(#sis-layout-state.auth-off) [data-testid="stMainBlockContainer"] {
                padding-top: 1.8rem !important;
            }

            body:has(#sis-layout-state.auth-on) [data-testid="stSidebar"] {
                display: block !important;
                visibility: visible !important;
                opacity: 1 !important;
                background: var(--sidebar-bg-gradient) !important;
                border-right: 1px solid rgba(196, 210, 226, 0.24) !important;
                min-width: 286px !important;
                max-width: 286px !important;
                width: 286px !important;
            }

            /* Streamlit muda a estrutura interna da sidebar entre versoes.
               Forcamos o tema marinho em todos os contêineres possiveis. */
            [data-testid="stSidebar"],
            section[data-testid="stSidebar"],
            aside[data-testid="stSidebar"],
            section[aria-label="Sidebar"],
            [data-testid="stSidebar"] > div,
            section[data-testid="stSidebar"] > div,
            [data-testid="stSidebar"] > div > div,
            [data-testid="stSidebarUserContent"],
            [data-testid="stSidebarContent"] > div,
            div[data-testid="stSidebarContent"] {
                background: var(--sidebar-bg-gradient) !important;
                background-color: var(--sidebar-bg) !important;
                background-image: var(--sidebar-bg-gradient) !important;
            }

            [data-testid="stSidebar"],
            section[data-testid="stSidebar"],
            div[data-testid="stSidebarContent"] {
                --background-color: var(--sidebar-bg) !important;
                --secondary-background-color: var(--sidebar-bg) !important;
                --text-color: #eaf2fb !important;
            }

            body:has(#sis-layout-state.auth-off) [data-testid="stSidebar"] {
                display: none !important;
            }

            [data-testid="collapsedControl"] {
                display: block !important;
                position: fixed !important;
                top: 0.58rem !important;
                left: 0.6rem !important;
                z-index: 1002 !important;
            }

            body:has(#sis-layout-state.auth-off) [data-testid="collapsedControl"] {
                display: none !important;
            }

            [data-testid="collapsedControl"] button {
                border: 1px solid var(--border) !important;
                background: var(--topbar-bg) !important;
                color: var(--text-primary) !important;
                border-radius: 10px !important;
                box-shadow: 0 2px 8px rgba(11, 36, 64, 0.08) !important;
            }

            [data-testid="stSidebar"] *,
            section[data-testid="stSidebar"] *,
            div[data-testid="stSidebarContent"] * {
                color: #eaf2fb !important;
            }

            [data-testid="stSidebar"] .stImage {
                display: flex !important;
                justify-content: center !important;
            }

            [data-testid="stSidebar"] [role="radiogroup"] > label {
                border-radius: 14px !important;
                border: 1px solid transparent !important;
                margin-bottom: 0.35rem !important;
                padding: 0.62rem 0.82rem !important;
                transition: all 120ms ease !important;
                font-weight: 600 !important;
            }

            [data-testid="stSidebar"] [role="radiogroup"] > label:hover {
                background: rgba(213, 226, 240, 0.16) !important;
                border-color: rgba(201, 216, 232, 0.26) !important;
            }

            [data-testid="stSidebar"] [role="radiogroup"] > label:has(input:checked) {
                background: #e8eff7 !important;
                border-color: #c2d0e0 !important;
            }

            [data-testid="stSidebar"] [role="radiogroup"] > label:has(input:checked) * {
                color: var(--text-primary) !important;
                font-weight: 700 !important;
            }

            .sis-topbar {
                display: block;
                height: 0;
                margin: 0;
                padding: 0;
            }

            .sis-topbar + div[data-testid="stHorizontalBlock"] {
                position: sticky !important;
                top: 0.25rem !important;
                z-index: 90 !important;
                margin-bottom: 0.9rem !important;
                padding: 0.52rem 0.9rem !important;
                background: var(--topbar-bg) !important;
                border: 1px solid var(--border) !important;
                border-radius: 14px !important;
                box-shadow: 0 6px 18px rgba(11, 36, 64, 0.08) !important;
            }

            div[data-testid="column"]:has(.sis-logout-marker) .stButton > button {
                width: 100% !important;
                border-radius: 10px !important;
                border: 1px solid #adc2d9 !important;
                background: var(--accent) !important;
                color: #ffffff !important;
                min-height: 2.3rem !important;
            }

            div[data-testid="column"]:has(.sis-logout-marker) .stButton > button:hover {
                background: #174c7b !important;
                border-color: #8eabc8 !important;
            }

            .sis-topbar-title {
                color: var(--text-primary);
                font-size: 1.18rem;
                font-weight: 700;
                letter-spacing: 0.2px;
            }

            .sis-user-wrap {
                display: flex;
                justify-content: flex-end;
                align-items: center;
                gap: 0.58rem;
            }

            .sis-avatar {
                width: 2.05rem;
                height: 2.05rem;
                border-radius: 50%;
                background: #174c7b;
                color: #ffffff;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                font-size: 0.82rem;
                font-weight: 700;
                border: 2px solid #d5e2ef;
            }

            .sis-user-name {
                color: var(--text-primary);
                font-size: 0.91rem;
                font-weight: 700;
                line-height: 1.15;
            }

            .sis-user-role {
                color: var(--text-muted);
                font-size: 0.76rem;
                font-weight: 600;
                line-height: 1.1;
            }

            [data-testid="stMetric"] {
                background: var(--topbar-bg) !important;
                border: 1px solid var(--border) !important;
                border-radius: 14px !important;
                padding: 0.6rem 0.7rem !important;
                box-shadow: 0 3px 10px rgba(11, 36, 64, 0.05) !important;
            }

            [data-testid="stDataFrame"],
            [data-testid="stForm"] {
                border-radius: 14px !important;
                border: 1px solid var(--border) !important;
                box-shadow: 0 3px 10px rgba(11, 36, 64, 0.05) !important;
            }

            /* MOVIDO DO LEGADO: estilo do titulo "Lista de pedidos" no painel de solicitacoes */
            .sis-aprov-panel-title {
                color: var(--text-primary);
                font-size: 1.02rem;
                line-height: 1.35;
                font-weight: 700;
                margin-bottom: 0.25rem;
            }

            [data-testid="stContainer"]:has(.sis-card-anchor),
            [data-testid="stVerticalBlockBorderWrapper"]:has(.sis-card-anchor) {
                background: var(--card-bg) !important;
                border: 1px solid var(--border) !important;
                border-radius: 16px !important;
                box-shadow: var(--shadow) !important;
                padding: 0.15rem 0.35rem 0.45rem 0.35rem !important;
            }

            @media (max-width: 768px) {
                [data-testid="stMainBlockContainer"] {
                    padding-left: 0.78rem !important;
                    padding-right: 0.78rem !important;
                }

                body:has(#sis-layout-state.auth-on) [data-testid="stSidebar"] {
                    position: fixed !important;
                    top: 0 !important;
                    left: 0 !important;
                    height: 100dvh !important;
                    z-index: 1001 !important;
                    box-shadow: 14px 0 30px rgba(2, 12, 30, 0.36) !important;
                    transition: transform 170ms ease !important;
                }

                body:has(#sis-layout-state.drawer-open.auth-on) [data-testid="stSidebar"] {
                    transform: translateX(0) !important;
                }

                body:has(#sis-layout-state.drawer-closed.auth-on) [data-testid="stSidebar"] {
                    transform: translateX(-110%) !important;
                }
            }

            @media (min-width: 769px) {
                body:has(#sis-layout-state.auth-on) [data-testid="stSidebar"] {
                    transform: translateX(0) !important;
                    position: relative !important;
                    left: 0 !important;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_mobile_backdrop(drawer_open: bool) -> None:
    _ = drawer_open


def render_topbar(user: dict[str, Any] | None, app_name: str = "SisGesPA") -> dict[str, bool]:
    username, perfil, initials = _user_display(user)
    events = {"logout": False}

    st.markdown('<div class="sis-topbar">', unsafe_allow_html=True)
    col_title, col_user, col_logout = st.columns([4.9, 2.3, 0.9], vertical_alignment="center")

    with col_title:
        st.markdown(f'<div class="sis-topbar-title">{html.escape(app_name)}</div>', unsafe_allow_html=True)

    with col_user:
        st.markdown(
            (
                '<div class="sis-user-wrap">'
                f'<span class="sis-avatar">{html.escape(initials)}</span>'
                "<div>"
                f'<div class="sis-user-name">{html.escape(username)}</div>'
                f'<div class="sis-user-role">{html.escape(perfil)}</div>'
                "</div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )

    with col_logout:
        st.markdown('<span class="sis-logout-marker"></span>', unsafe_allow_html=True)
        if st.button("Sair", key="sis_topbar_logout", help="Encerrar sessao"):
            events["logout"] = True
    st.markdown("</div>", unsafe_allow_html=True)

    return events


def render_sidebar(
    menu_items: list[MenuItem],
    selected_id: str,
    user: dict[str, Any] | None,
    logo_path: Path | None,
    app_title: str,
    app_subtitle: str,
    db_path: str,
) -> str:
    options = [item.id for item in menu_items]
    selected = selected_id if selected_id in options else options[0]
    label_map = {item.id: f"{item.icon}  {item.label}" for item in menu_items}
    username, perfil, _ = _user_display(user)

    if st.session_state.get("sis_nav_radio") not in options:
        st.session_state["sis_nav_radio"] = selected

    with st.sidebar:
        if logo_path is not None and logo_path.exists():
            st.image(str(logo_path), width=74)
        st.markdown(f"### {app_title}")
        st.caption(app_subtitle)
        st.markdown("---")
        chosen = st.radio(
            "Navegacao",
            options,
            format_func=lambda item_id: label_map[item_id],
            key="sis_nav_radio",
            label_visibility="collapsed",
        )
        st.markdown("---")
        st.caption(f"Banco: {db_path}")
        st.caption(f"Usuario: {username}")
        if perfil:
            st.caption(f"Perfil: {perfil}")

    return str(chosen)


@contextmanager
def card(title: str | None = None) -> Iterator[None]:
    with st.container(border=True):
        st.markdown('<span class="sis-card-anchor"></span>', unsafe_allow_html=True)
        if title:
            st.markdown(f"### {title}")
        yield
