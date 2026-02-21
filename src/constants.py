from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "sisgespa.db"
DEFAULT_EXPORT_DIR = PROJECT_ROOT / "data" / "exports"


ROLE_ADMIN = "ADMIN"
ROLE_AVALIADOR = "AVALIADOR"
ROLE_APROVADOR = "APROVADOR"
ROLE_CONSULTA = "CONSULTA"
ALL_ROLES = {ROLE_ADMIN, ROLE_AVALIADOR, ROLE_APROVADOR, ROLE_CONSULTA}


STATUS_EM_ANALISE = "EM_ANALISE"
STATUS_APROVADA = "APROVADA"
STATUS_CANCELADA = "CANCELADA"


ACAO_APROVAR = "APROVAR"
ACAO_CANCELAR = "CANCELAR"
ACAO_PARCIAL = "PARCIAL"
ACOES_HABILITADAS = {ACAO_APROVAR, ACAO_CANCELAR}


CONFIG_KEY_SALDO_FORMULA = "saldo_formula"
DEFAULT_SALDO_FORMULA = {
    "sol_lib_cred_formula": "liberado + bandeja_dgom",
    "valor_pa_aju_formula_1": "liberado + a_atender",
    "valor_pa_aju_formula_2": "valor_pa_ini + dif_planejamento_real",
    "saldo_formula": "(valor_pa_ini + dif_planejamento_real) - (liberado + bandeja_dgom)",
}


SOLCRED_COLUMN_BY_INDEX = {
    0: "pa_exercicio",
    1: "pa_grupo",
    2: "pa_ai",
    3: "pa_aoxpo_ai",
    4: "pa_aoxpo_pa",
    5: "pa_fr",
    6: "pa_nd",
    7: "pa_ugr",
    8: "pa_uge",
    9: "pa_moeda",
    10: "pa_ug_exterior",
    11: "sol_origem",
    12: "sol_numero_solicitacao",
    13: "sol_tipo",
    14: "sol_data_criacao",
    15: "sol_prioridade",
    16: "sol_situacao",
    17: "sol_data_situacao",
    18: "sol_setor_atual",
    19: "sol_perfil_atual",
    20: "sol_grupo",
    21: "sol_ai",
    22: "sol_aoxpo_pa",
    23: "sol_fr",
    24: "sol_nd",
    25: "sol_ugr",
    26: "sol_uge",
    27: "solicitado",
    28: "atendido",
    29: "em_atendimento",
    30: "devolvido",
    31: "saldo_a_atender",
    32: "nc",
}
