from __future__ import annotations

from src.etl_bd import import_bd
from src.models import Saldos
from src.services_aprovacao import calculate_saldo_disponivel, get_formula_config
from tests.conftest import make_bd_file
from tests.test_etl_bd import _sample_bd_record


def test_saldo_formula_por_relacoes_de_negocio(SessionLocal, tmp_path):
    record = _sample_bd_record()
    # Regras vigentes:
    # Sol.Lib.Cred. = Liberado + Bandeja DGOM
    # Valor do PA Aju = Valor do PA Ini + Dif. Planejamento(Real)
    record["Valor do PA Ini"] = 1000
    record["Dif. Planejamento(Real)"] = 200
    record["Liberado"] = 300
    record["Bandeja DGOM"] = 50

    # Valores conflitantes nao devem definir o saldo calculado.
    record["Valor do PA Aju"] = 9999
    record["Sol.Lib.Cred."] = 9999

    file_path = make_bd_file(tmp_path / "BD_formula.xlsx", [record])

    with SessionLocal() as session:
        import_bd(session, file_path=file_path, usuario="tester")

    with SessionLocal() as session:
        saldo = session.query(Saldos).one()
        formula = get_formula_config(session)
        assert formula["sol_lib_cred_formula"] == "liberado + bandeja_dgom"
        assert formula["valor_pa_aju_formula_1"] == "liberado + a_atender"
        assert formula["valor_pa_aju_formula_2"] == "valor_pa_ini + dif_planejamento_real"
        assert formula["saldo_formula"] == "(valor_pa_ini + dif_planejamento_real) - (liberado + bandeja_dgom)"
        assert float(calculate_saldo_disponivel(saldo, formula)) == 850.0
