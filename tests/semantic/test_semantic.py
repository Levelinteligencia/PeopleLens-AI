"""F7 — Semantic Layer, KPI Catalog e Trust Layer.

Dois blocos, como a Parte XI da SPEC pede:

    AC-01..AC-18    o que deve passar
    FC-01..FC-12    os doze casos de falha, cada um como teste
    FCx-13..FCx-17  o que deve falhar, e falha aqui de proposito

A suite nao escreve na camada de verdade nem no RAW (guarda de sessao em
`tests/conftest.py`), e as consultas rodam com `registrar=False` exceto no
teste do log, que usa uma raiz temporaria.
"""
from __future__ import annotations

import dataclasses
import re
import sqlite3
from pathlib import Path

import pytest
import yaml

from analytics import contracts
from analytics.semantic import (ask as A, catalog as C, certify, executor,
                                plans, response, trace)
from analytics.semantic.query import (QueryShapeError, SemanticQuery,
                                      load_vocabulary, validate)
from analytics.trust import BANDS, PISO_PENDENCIA
from generator import config

ROOT = Path(__file__).resolve().parents[2]

CERTIFICADOS = ("headcount", "turnover_rate", "women_in_leadership",
                "hiring_volume", "time_to_fill")
BLOQUEADOS = ("internal_mobility_rate", "promotion_rate", "compa_ratio",
              "pay_gap", "black_representation")


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def cfg():
    return config.load(ROOT)


@pytest.fixture(scope="module")
def cat(cfg):
    return C.load(cfg)


@pytest.fixture(scope="module")
def eng(cfg):
    e = A.engine(cfg)
    yield e
    e.close()


@pytest.fixture(scope="module")
def vocab(eng):
    return eng.vocab


@pytest.fixture
def cfg_tmp(cfg, tmp_path):
    """Raiz temporaria: config e data apontam para os reais, governance e nova.

    O log de consultas escreve em SQLite, e escrever no banco do projeto durante
    a suite contaminaria a contagem de recusas que a F7 usa para descobrir que a
    mesma pergunta e recusada toda semana.
    """
    (tmp_path / "data").mkdir()
    (tmp_path / "config").symlink_to(ROOT / "config")
    (tmp_path / "data" / "processed").symlink_to(ROOT / "data" / "processed")
    (tmp_path / "data" / "governance").mkdir()
    return dataclasses.replace(cfg, root=tmp_path)


def _q(**kw):
    kw.setdefault("period", {"grain": "mes", "from": "2026-06", "to": "2026-06"})
    return SemanticQuery.parse(kw)


# ========================================================================== #
# AC — devem passar
# ========================================================================== #
def test_ac01_todo_kpi_tem_os_campos_obrigatorios(cfg, cat):
    faltando = [p for p in C.verify(cfg)
                if "campo obrigatorio ausente" in p]
    assert not faltando, faltando
    assert len(cat.ids) == 18


def test_ac02_depends_on_checks_continua_derivado(cfg):
    """A extensao da F7 nao pode ter digitado dependencia nenhuma.

    `depends_on_checks` e derivado de `consumed_by_kpis`; duas listas que
    descrevem a mesma relacao em lugares diferentes divergem em silencio.
    """
    derivado = contracts.derive_checks(cfg)
    for kpi, doc in contracts.load(cfg).items():
        assert sorted(doc["depends_on_checks"]) == derivado.get(kpi, []), kpi
    assert contracts.verify(cfg) == []


def test_ac03_certified_tem_dono_versao_data_e_zero_bloqueadores(cat):
    for kpi in cat.por_status("CERTIFIED"):
        cert = kpi.doc["certification"]
        assert kpi.owner == "people-analytics"
        assert re.fullmatch(r"\d+\.\d+\.\d+", kpi.version)
        assert cert["approved_by"] and cert["approved_at"]
        assert not cert["blockers"]
        assert kpi.period_coverage is not None
    assert {k.kpi_id for k in cat.por_status("CERTIFIED")} == set(CERTIFICADOS)


def test_ac04_source_tables_so_aponta_para_a_l3(cat):
    for kpi in cat.kpis.values():
        for t in kpi.source_tables:
            assert t.startswith(("fact_", "dim_")), (kpi.kpi_id, t)
        p = plans.plano(kpi.kpi_id)
        if p:
            # o plano nao pode ler tabela que o contrato nao declarou
            assert set(p.tabelas) <= set(kpi.source_tables), kpi.kpi_id


def test_ac05_nenhuma_consulta_toca_raw_verdade_ou_camada_intermediaria(eng):
    """Duas garantias, e a segunda e a que vale.

    A primeira le o SQL dos planos e exige o prefixo `analytical.`. A segunda e
    estrutural: os schemas de verdade, raw e conformed **nao estao registrados**
    na conexao da camada semantica. Nao e um acordo de nao usar; e um nome que
    nao resolve.
    """
    assert plans.tabelas_fora_da_l3() == {}
    registrados = executor.schemas(eng.con)
    assert "truth" not in registrados
    assert registrados >= {"analytical", "semantic"}
    for proibido in ("truth", "raw", "standardized", "conformed"):
        with pytest.raises(Exception):
            eng.con.execute(f"SELECT 1 FROM {proibido}.dim_employee LIMIT 1")


def test_ac06_consulta_resolvivel_sem_nomear_tabela_join_ou_coluna(eng):
    ans = A.ask(eng, {"kpi": "headcount",
                      "period": {"grain": "mes", "from": "2026-06", "to": "2026-06"},
                      "filters": [{"dimension": "pais", "in": ["Brasil"]}]},
                registrar=False)
    assert ans.respondeu and ans.value == 1324
    texto = str(ans.to_dict())
    for fisico in ("fact_headcount_snapshot", "dim_organization", "JOIN",
                   "is_system_of_record", "org_sk"):
        assert fisico not in texto, fisico


def test_ac07_dimensao_fora_do_permitido_e_recusa_nao_erro(eng):
    ans = A.ask(eng, {"kpi": "headcount",
                      "period": {"grain": "mes", "from": "2025-06", "to": "2025-06"},
                      "dimensions": ["centro_custo"]}, registrar=False)
    assert ans.refusal["classe"] == "DIMENSAO_NAO_PERMITIDA"
    assert "pais" in ans.refusal["o_que_resolveria"]


def test_ac08_termo_fora_do_vocabulario_nunca_vira_aproximacao(eng, vocab):
    ans = A.ask(eng, {"kpi": "headcount",
                      "period": {"grain": "mes", "from": "2025-06", "to": "2025-06"},
                      "filters": [{"dimension": "pais", "in": ["Portugal"]}]},
                registrar=False)
    assert ans.refusal["classe"] == "TERMO_DESCONHECIDO"
    # "Brasilia" NAO pode casar com "Brasil" por prefixo nem por similaridade
    membro, pred, erro = vocab.resolve("pais", "Brasilia")
    assert membro is None and pred is None and erro


def test_ac09_trust_resposta_e_o_minimo_entre_dado_e_teto(cfg, cat, eng):
    # verificacao da funcao, em todas as combinacoes
    assert C.trust_resposta("CERTIFIED", "LIMITED") == "LIMITED"
    assert C.trust_resposta("LIMITED", "CERTIFIED") == "LIMITED"
    assert C.trust_resposta("CERTIFIED", "CERTIFIED") == "CERTIFIED"
    assert C.trust_resposta("BLOCKED", "CERTIFIED") == "BLOCKED"
    assert C.trust_resposta("CERTIFIED", None) == "BLOCKED"

    # e na resposta real: fte tem trust de dado 1,0 e status DECLARED
    ans = A.ask(eng, {"kpi": "fte",
                      "period": {"grain": "mes", "from": "2026-06", "to": "2026-06"}},
                registrar=False)
    assert ans.trust["trust_dado"] == "CERTIFIED"
    assert ans.trust["trust_governanca"] == "LIMITED"
    assert ans.trust["status"] == "LIMITED"
    assert ans.trust["limitado_por"] == "GOVERNANCA"


def test_ac10_as_bandas_da_f5_permanecem_inalteradas():
    """ADR-0023, decisao DQ-04: a F7 calibra por recorte fino e NAO move banda.

    Se este teste reprovar, alguem editou o limiar para fechar uma distribuicao,
    que e exatamente o que o ADR proibe.
    """
    assert BANDS == {"CERTIFIED": 0.95, "LIMITED": 0.70}
    assert PISO_PENDENCIA == 0.40


def test_ac11_recorte_pequeno_e_suprimido_por_privacidade(eng, cat):
    ans = A.ask(eng, {"kpi": "women_in_leadership",
                      "period": {"grain": "mes", "from": "2022-06", "to": "2022-06"},
                      "filters": [{"dimension": "pais", "in": ["Chile"]}]},
                registrar=False)
    assert ans.suppressed, ans.to_dict()
    assert ans.suppressed["motivo"] == "PRIVACIDADE"
    assert ans.suppressed["populacao"] < cat["women_in_leadership"].minimum_n
    assert ans.value is None
    assert "privacidade" in ans.explanation.lower()
    assert "qualidade" not in (ans.trust.get("motivo") or "").lower()


def test_ac12_toda_resposta_declara_nivel_trust_cobertura_e_caveats(eng):
    ans = A.ask(eng, {"kpi": "headcount",
                      "period": {"grain": "mes", "from": "2026-06", "to": "2026-06"}},
                registrar=False)
    d = ans.to_dict()
    for campo in response.CAMPOS_OBRIGATORIOS_DA_RESPOSTA:
        assert campo in d, campo
    assert d["trust"]["status"] and d["coverage"]["population"] > 0
    assert d["caveats"]


def test_ac13_interpretation_so_sai_com_regra_registrada(cat, eng):
    # nenhum KPI tem regra hoje; portanto INTERPRETATION nao sai de nenhum
    for kpi in cat.kpis.values():
        assert not kpi.doc["interpretation_rules"]
        if kpi.responde:
            assert kpi.teto_nivel == "CONTEXT"
    ans = A.ask(eng, {"kpi": "headcount",
                      "period": {"grain": "mes", "from": "2026-06", "to": "2026-06"},
                      "requested_level": "INTERPRETATION"}, registrar=False)
    assert ans.refusal["classe"] == "NIVEL_SEM_EVIDENCIA"
    assert "interpretation_rules" in ans.refusal["o_que_resolveria"]


def test_ac14_causality_negada_diz_o_que_faltaria(cat, eng):
    ans = A.ask(eng, {"kpi": "headcount",
                      "period": {"grain": "mes", "from": "2026-06", "to": "2026-06"},
                      "requested_level": "CAUSALITY"}, registrar=False)
    assert ans.refusal["classe"] == "NIVEL_SEM_EVIDENCIA"
    falta = ans.refusal["o_que_resolveria"]
    assert "causal_studies" in falta and "controle" in falta
    neg = response.negacao_causal(cat["headcount"])
    assert neg["negado"] and "controle" in neg["o_que_responderia"]


def test_ac15_trace_navega_da_resposta_ate_o_row_id_da_fonte(cfg, cat, eng):
    ans = A.ask(eng, {"kpi": "headcount",
                      "period": {"grain": "mes", "from": "2026-06", "to": "2026-06"}},
                registrar=False)
    t = trace.trace(cfg, ans, cat["headcount"])
    assert list(t) == ["resposta", "kpi", "definicao", "regra",
                       "tabela_analitica", "fonte"]
    assert t["kpi"]["version"] == "1.0.0"
    assert t["definicao"]["business_definition"]
    assert t["regra"]["checks"] and t["regra"]["mappings"]
    assert t["tabela_analitica"]["layer"] == "analytical"
    assert "is_system_of_record = true" in t["tabela_analitica"]["filtros_fixos"]
    assert "source_row_id" in t["fonte"]["por_onde"]
    assert "transformation_log" in t["fonte"]["depois"]


def test_ac16_resposta_e_recusa_ficam_no_log(cfg_tmp):
    eng = A.engine(cfg_tmp)
    try:
        ok = A.ask(eng, {"kpi": "headcount", "pergunta": "quantas pessoas?",
                         "period": {"grain": "mes", "from": "2026-06", "to": "2026-06"}})
        neg = A.ask(eng, {"kpi": "internal_mobility_rate",
                          "pergunta": "qual a mobilidade interna?",
                          "period": {"grain": "ano", "from": "2025", "to": "2025"}})
    finally:
        eng.close()

    a = trace.ler(cfg_tmp, ok.trace_id)
    b = trace.ler(cfg_tmp, neg.trace_id)
    assert a["respondeu"] == 1 and a["valor"] == 1942 and a["kpi_version"] == "1.0.0"
    assert a["pergunta"] == "quantas pessoas?" and a["l3_run_id"]
    assert b["respondeu"] == 0 and b["refusal_class"] == "KPI_BLOQUEADO"
    assert b["valor"] is None
    c = trace.contagem(cfg_tmp)
    assert c["consultas"] == 2 and c["recusas"] == 1


def test_ac17_mudar_formula_gera_versao_maior_e_a_anterior_continua_consultavel(cat):
    """ADR-0030: a serie historica nao e reescrita por mudanca de definicao."""
    from analytics.semantic import versioning as V
    antes = cat["headcount"].doc
    depois = dict(antes, formula="outra coisa")
    assert V.tipo_de_mudanca(antes, depois) == "maior"
    assert V.proxima_versao("1.0.0", "maior") == "2.0.0"
    assert V.tipo_de_mudanca(antes, dict(antes, exclusions=[])) == "menor"
    assert V.proxima_versao("1.0.0", "menor") == "1.1.0"
    assert V.tipo_de_mudanca(antes, dict(antes, description="texto novo")) == "correcao"
    assert V.tipo_de_mudanca(antes, antes) is None
    # mudar o id NAO e versao nova: e outro KPI
    with pytest.raises(V.VersionError):
        V.tipo_de_mudanca(antes, dict(antes, kpi_id="headcount_v2"))
    # a versao anterior continua endereçavel
    assert V.versoes_consultaveis(cat["headcount"]) == ["1.0.0"]


def test_ac18_nenhuma_regra_de_negocio_nova_sem_sinalizacao(cfg, cat):
    """Toda regra que decide quem entra na conta esta declarada no contrato.

    O teste e sobre onde a regra mora: se um filtro fixo do plano nao estiver
    escrito no contrato, ele e uma regra de negocio que entrou pelo codigo.
    """
    for kpi in cat.kpis.values():
        p = plans.plano(kpi.kpi_id)
        if p is None:
            continue
        declarados = " ".join(f["regra"] for f in kpi.doc.get("filters") or [])
        if "is_system_of_record" in p.sql:
            assert "is_system_of_record" in declarados, kpi.kpi_id
        if re.search(r"WHERE\s+g\.is_hire", p.sql):
            assert "is_hire" in declarados, kpi.kpi_id
        if "j.is_leadership" in p.sql and kpi.kpi_id == "women_in_leadership":
            assert "is_leadership" in declarados, kpi.kpi_id
    assert C.verify(cfg) == []


# ========================================================================== #
# FC — os doze casos de falha da Parte IX
# ========================================================================== #
def test_fc01_kpi_nao_certificado_responde_no_maximo_em_context(eng, cat):
    kpi = cat["fte"]
    assert kpi.status == "DECLARED" and kpi.teto_nivel == "CONTEXT"
    ans = A.ask(eng, {"kpi": "fte",
                      "period": {"grain": "mes", "from": "2026-06", "to": "2026-06"},
                      "requested_level": "CONTEXT", "compare": "periodo_anterior"},
                registrar=False)
    assert ans.level in ("FACT", "CONTEXT")
    assert ans.trust["status"] == "LIMITED"
    assert any("DECLARED" in c for c in ans.caveats)


def test_fc02_kpi_blocked_recusa_nomeando_bloqueador_e_solucao(eng, cat):
    ans = A.ask(eng, {"kpi": "internal_mobility_rate",
                      "period": {"grain": "ano", "from": "2025", "to": "2025"}},
                registrar=False)
    assert ans.refusal["classe"] == "KPI_BLOQUEADO"
    assert "movement_type" in ans.refusal["mensagem"]
    assert "DE/PARA" in ans.refusal["o_que_resolveria"]
    assert ans.value is None


def test_fc03_populacao_incompleta_responde_limited_com_cobertura(eng):
    ans = A.ask(eng, {"kpi": "hiring_volume",
                      "period": {"grain": "ano", "from": "2025", "to": "2025"}},
                registrar=False)
    assert ans.respondeu and ans.value == 334
    assert ans.trust["status"] == "LIMITED"
    assert ans.trust["limitado_por"] == "COBERTURA"
    assert ans.coverage["population_covered"] == pytest.approx(0.298)
    assert "1.499" in (ans.coverage.get("nota") or "")


def test_fc04_mapeamento_pendente_bloqueante_recusa_nomeando_a_excecao(cfg):
    eng = A.engine(cfg, mapeamentos_pendentes={
        "ref_job_level_mapping": "N4 e N5 da VIVAMARKET_LEGACY sem mapeamento aprovado"})
    try:
        ans = A.ask(eng, {"kpi": "women_in_leadership",
                          "period": {"grain": "mes", "from": "2026-06", "to": "2026-06"}},
                    registrar=False)
    finally:
        eng.close()
    assert ans.refusal["classe"] == "MAPEAMENTO_PENDENTE"
    assert "ref_job_level_mapping" in ans.refusal["mensagem"]
    assert "N4 e N5" in ans.refusal["mensagem"]


def test_fc05_identidade_nao_resolvida_aparece_na_resposta(eng):
    """Pessoa provisoria nunca vira consolidada em silencio.

    A perda por identidade nao resolvida entra na atribuicao por classe e sai
    na resposta; e `is_system_of_record` impede a dupla contagem sem fundir
    ninguem.
    """
    ans = A.ask(eng, {"kpi": "headcount",
                      "period": {"grain": "mes", "from": "2026-06", "to": "2026-06"}},
                registrar=False)
    assert "IDENTIDADE_NAO_RESOLVIDA" in ans.trust["perda_por_classe"]
    assert any("pendencia" in c for c in ans.caveats)


def test_fc06_definicao_ambigua_recusa_porque_dois_vocabularios_nao_dao_um_numero(cat):
    kpi = cat["internal_mobility_rate"]
    assert kpi.status == "BLOCKED"
    b = kpi.bloqueadores[0]["motivo"]
    assert "Promotion" in b and "PROMOCAO" in b
    assert "491" in b and "601" in b
    assert plans.plano("internal_mobility_rate") is None


def test_fc07_dimensao_nao_permitida_diz_o_que_responde_no_lugar(eng):
    ans = A.ask(eng, {"kpi": "time_to_fill",
                      "period": {"grain": "trimestre", "from": "2025-Q2", "to": "2025-Q2"},
                      "dimensions": ["genero"]}, registrar=False)
    assert ans.refusal["classe"] == "DIMENSAO_NAO_PERMITIDA"
    assert "business_unit" in ans.refusal["o_que_resolveria"]


def test_fc08_periodo_fora_da_cobertura_informa_a_janela(eng):
    ans = A.ask(eng, {"kpi": "headcount",
                      "period": {"grain": "mes", "from": "2014-06", "to": "2014-06"}},
                registrar=False)
    assert ans.refusal["classe"] == "PERIODO_FORA_DE_COBERTURA"
    assert ans.refusal["detalhe"]["cobertura"] == ["2016-01", "2026-06"]

    # hiring_volume so tem ATS a partir de 2021-03: antes disso a resposta
    # correta NAO e zero (risco R-08)
    ans2 = A.ask(eng, {"kpi": "hiring_volume",
                       "period": {"grain": "ano", "from": "2018", "to": "2018"}},
                 registrar=False)
    assert ans2.refusal["classe"] == "PERIODO_FORA_DE_COBERTURA"
    assert ans2.value is None


def test_fc09_indeterminada_e_aquisicao_nunca_contam_como_contratacao(eng, cfg):
    """O criterio e `is_hire`, e so ele.

    Prova numerica: o total de entradas com origem determinada como contratacao
    e 1.499. Somar INDETERMINADA daria 4.910, e a diferenca e o tamanho da
    mentira que o KPI evitaria contar.
    """
    ans = A.ask(eng, {"kpi": "hiring_volume",
                      "period": {"grain": "ano", "from": "2021", "to": "2026"}},
                registrar=False)
    total = sum(int(l["valor"]) for l in ans.rows)
    assert total == 1499

    por_origem = A.ask(eng, {"kpi": "hiring_volume",
                             "period": {"grain": "ano", "from": "2021", "to": "2026"},
                             "dimensions": ["origem"]}, registrar=False)
    origens = {l["origem"] for l in por_origem.rows}
    assert origens == {"CONTRATACAO"}
    assert "INDETERMINADA" not in origens
    assert not any(o.startswith("AQUISICAO") for o in origens)


def test_fc10_evidencia_insuficiente_para_causalidade(cat):
    neg = response.negacao_causal(cat["turnover_rate"])
    assert neg["negado"]
    assert "estudo" in neg["motivo"]
    assert "intervalo de confianca" in neg["o_que_responderia"]
    assert "associacao" in neg["motivo"]


def test_fc11_supressao_usa_a_palavra_privacidade_e_nao_qualidade(eng):
    ans = A.ask(eng, {"kpi": "women_in_leadership",
                      "period": {"grain": "mes", "from": "2022-06", "to": "2022-06"},
                      "filters": [{"dimension": "pais", "in": ["Chile"]}]},
                registrar=False)
    assert ans.suppressed["motivo"] == "PRIVACIDADE"
    assert "nao por qualidade" in ans.suppressed["nota"]
    # o trust do dado segue disponivel e NAO e o motivo da recusa
    assert ans.trust["status"] in ("CERTIFIED", "LIMITED")


def test_fc12_comparar_versoes_diferentes_e_recusado(eng, cat):
    from analytics.semantic import versioning as V
    assert V.comparavel(cat["headcount"], "1.0.0", "1.0.0")
    assert not V.comparavel(cat["headcount"], "1.0.0", "2.0.0")
    ans = A.ask(eng, {"kpi": "headcount", "kpi_version": "2.0.0",
                      "period": {"grain": "mes", "from": "2026-06", "to": "2026-06"}},
                registrar=False)
    assert ans.refusal["classe"] == "VERSAO_INEXISTENTE"


# ========================================================================== #
# FCx — devem falhar
# ========================================================================== #
def test_fcx13_certified_com_trust_de_dado_blocked_nao_responde_em_fact(cfg, cat):
    """Um KPI certificado cujo dado desabou nao responde como fato.

    A certificacao continua valida; o numero e que nao esta bom. E a direcao
    contraria do ADR-0029, e ela tambem precisa valer.
    """
    kpi = cat["headcount"]
    t = certify.TrustResposta(status="BLOCKED", score=0.2, limitado_por="DADO",
                              motivo="ERRO", trust_dado="BLOCKED",
                              trust_governanca="CERTIFIED")
    nivel, motivo = response.nivel_efetivo("FACT", kpi, t)
    assert nivel is None
    assert "trust" in motivo


def test_fcx14_nao_da_para_somar_headcount_sem_o_sistema_de_registro(eng):
    """Nem consultando o DuckDB direto.

    A view `semantic.kpi_headcount` ja nasce com o filtro fixo aplicado, entao
    quem somar a view inteira nao consegue produzir o numero inflado da
    sobreposicao de 2016-2019. O numero da view e o numero certo.
    """
    ate2019 = eng.con.execute("""
        SELECT COUNT(DISTINCT party_key) FROM semantic.kpi_headcount
        WHERE periodo_mes = '2019-01'""").fetchone()[0]
    bruto = eng.con.execute("""
        SELECT COUNT(DISTINCT h.party_key)
        FROM analytical.fact_headcount_snapshot h
        JOIN analytical.dim_calendar c ON c.date_sk = h.date_sk
        WHERE c.mes = '2019-01'""").fetchone()[0]
    # o bruto, sem o filtro, observa a mesma pessoa por dois sistemas
    assert bruto >= ate2019
    linhas_view = eng.con.execute(
        "SELECT COUNT(*) FROM semantic.kpi_headcount WHERE periodo_mes='2019-01'"
    ).fetchone()[0]
    assert linhas_view == ate2019      # uma linha por pessoa, ja desduplicada
    assert "is_system_of_record" in plans.PLANS["headcount"].sql


def test_fcx15_a_ia_nao_pode_emitir_sql_nem_numero(eng):
    """O objeto de consulta nao tem onde por SQL, e campo desconhecido reprova.

    Ignorar o campo extra seria a porta por onde `{"sql": ...}` entraria sem
    ninguem notar, e o objeto deixaria de ser a fronteira do ADR-0028.
    """
    for veneno in (
        {"kpi": "headcount", "sql": "SELECT 1",
         "period": {"grain": "mes", "from": "2026-06", "to": "2026-06"}},
        {"kpi": "headcount", "table": "fact_headcount_snapshot",
         "period": {"grain": "mes", "from": "2026-06", "to": "2026-06"}},
        {"kpi": "headcount", "value": 1942,
         "period": {"grain": "mes", "from": "2026-06", "to": "2026-06"}},
        {"kpi": "headcount",
         "period": {"grain": "mes", "from": "2026-06", "to": "2026-06",
                    "where": "1=1"}},
        {"kpi": "headcount",
         "period": {"grain": "mes", "from": "2026-06", "to": "2026-06"},
         "filters": [{"dimension": "pais", "expression": "country = 'BR'"}]},
    ):
        with pytest.raises(QueryShapeError):
            SemanticQuery.parse(veneno)

    # e um valor injetado num termo nao vira SQL: vira recusa de vocabulario
    ans = A.ask(eng, {"kpi": "headcount",
                      "period": {"grain": "mes", "from": "2026-06", "to": "2026-06"},
                      "filters": [{"dimension": "pais", "in": ["BR' OR '1'='1"]}]},
                registrar=False)
    assert ans.refusal["classe"] == "TERMO_DESCONHECIDO"


def test_fcx16_nenhuma_resposta_sai_sem_trace_id(eng):
    consultas = [
        {"kpi": "headcount", "period": {"grain": "mes", "from": "2026-06", "to": "2026-06"}},
        {"kpi": "internal_mobility_rate", "period": {"grain": "ano", "from": "2025", "to": "2025"}},
        {"kpi": "nao_existe", "period": {"grain": "mes", "from": "2026-06", "to": "2026-06"}},
        {"kpi": "women_in_leadership",
         "period": {"grain": "mes", "from": "2022-06", "to": "2022-06"},
         "filters": [{"dimension": "pais", "in": ["Chile"]}]},
    ]
    vistos = set()
    for c in consultas:
        ans = A.ask(eng, c, registrar=False)
        assert ans.trace_id and len(ans.trace_id) == 16
        vistos.add(ans.trace_id)
    assert len(vistos) == len(consultas)


def test_fcx17_kpi_blocked_nao_produz_valor_de_natureza_nenhuma(eng, cat):
    for kpi_id in BLOQUEADOS:
        assert cat[kpi_id].status == "BLOCKED"
        assert plans.plano(kpi_id) is None, f"{kpi_id} nao pode ter plano"
        assert f"kpi_{kpi_id}" not in [
            r[0] for r in eng.con.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'semantic'").fetchall()]
    for kpi_id, periodo in (("internal_mobility_rate", {"grain": "ano", "from": "2025", "to": "2025"}),
                            ("compa_ratio", {"grain": "mes", "from": "2025-06", "to": "2025-06"}),
                            ("black_representation", {"grain": "mes", "from": "2025-06", "to": "2025-06"})):
        ans = A.ask(eng, {"kpi": kpi_id, "period": periodo}, registrar=False)
        assert ans.value is None and ans.level is None
        assert not ans.rows


# ========================================================================== #
# Verificacoes de apoio
# ========================================================================== #
def test_numeros_batem_com_calculo_independente(eng):
    """Conferencia do executor contra Polars, fora do DuckDB.

    Um executor que erra em silencio produz respostas com trace, trust e
    certificacao, e todas erradas. A conferencia e o unico jeito de saber.
    """
    import polars as pl
    A3 = ROOT / "data" / "processed" / "analytical"
    h = pl.read_parquet(A3 / "fact_headcount_snapshot.parquet").filter(
        pl.col("is_system_of_record"))
    jun = h.filter(pl.col("obs_date").str.starts_with("2026-06"))
    esperado = jun["party_key"].n_unique()

    ans = A.ask(eng, {"kpi": "headcount",
                      "period": {"grain": "mes", "from": "2026-06", "to": "2026-06"}},
                registrar=False)
    assert ans.value == esperado == 1942

    # rollup de estoque pega o ULTIMO mes, nao a soma dos doze
    ano = A.ask(eng, {"kpi": "headcount",
                      "period": {"grain": "ano", "from": "2025", "to": "2025"}},
                registrar=False)
    dez = h.filter(pl.col("obs_date").str.starts_with("2025-12"))["party_key"].n_unique()
    assert ano.value == dez == 2038

    # turnover: media das pontas no denominador, nao a soma dos meses
    t = A.ask(eng, {"kpi": "turnover_rate",
                    "period": {"grain": "ano", "from": "2024", "to": "2024"}},
              registrar=False)
    assert t.value == pytest.approx(0.253766, abs=1e-6)


def test_vocabulario_nao_expoe_membro_reservado(vocab):
    """Membro reservado e pendencia de governanca, nao valor de negocio."""
    for termo in ("UNMAPPED", "DECISAO_PENDENTE"):
        membro, pred, erro = vocab.resolve("nivel", termo)
        assert membro is None and erro and "reservado" in erro
    membro, _, erro = vocab.resolve("departamento", "UNMAPPED")
    assert membro is None and erro


def test_vocabulario_resolve_termo_de_negocio_para_membro(vocab):
    assert vocab.resolve("pais", "Brasil")[0] == "BR"
    assert vocab.resolve("pais", "brazil")[0] == "BR"
    assert vocab.resolve("genero", "mulheres")[0] == "Female"
    assert vocab.resolve("origem", "gente que veio da VivaMarket")[0] == "AQUISICAO_VIVAMARKET"
    _, pred, _ = vocab.resolve("nivel", "liderança")
    assert pred["column"] == "is_leadership" and pred["equals"] is True


def test_o_teto_de_nivel_cai_quando_falta_evidencia(cat):
    kpi = cat["headcount"]
    assert kpi.teto_nivel == "CONTEXT"          # sem regra registrada
    com_regra = C.Kpi("x", dict(kpi.doc, interpretation_rules=[
        {"regra": "acima de 40% e bom", "owner": "people-analytics",
         "approved_at": "2026-09-12"}]))
    assert com_regra.teto_nivel == "INTERPRETATION"
    com_estudo = C.Kpi("x", dict(com_regra.doc, causal_studies=[
        {"design": "dif-em-dif", "treatment": "a", "control": "b", "effect": "0.1",
         "interval": "[0,0.2]", "limitations": "amostra pequena"}]))
    assert com_estudo.teto_nivel == "CAUSALITY"


def test_regra_de_redacao_recusa_verbo_causal_em_context():
    assert response.viola_regra_de_redacao(
        "CONTEXT", "o turnover subiu porque houve reorganizacao") == ["porque"]
    assert response.viola_regra_de_redacao(
        "CONTEXT", "o turnover subiu 3 p.p. no mesmo periodo") == []


def test_certificacao_nao_e_calculavel_a_partir_do_trust(cat):
    """Nao existe funcao que promova KPI por limiar, e nao pode existir.

    `internal_mobility_rate` tem trust de dado alto e continua BLOCKED. O
    inverso do ADR-0029, e o motivo dele.
    """
    fontes = Path(__file__).resolve().parents[2] / "src" / "analytics" / "semantic"
    for p in fontes.glob("*.py"):
        texto = p.read_text(encoding="utf-8")
        assert not re.search(r"status\s*=\s*[\"']CERTIFIED[\"']", texto), p.name
    assert cat["internal_mobility_rate"].status == "BLOCKED"


def test_a_camada_semantica_nunca_liga_a_camada_de_verdade():
    """Nenhuma chamada da camada semantica pede `with_truth`.

    O parametro existe para auditoria; o caminho da resposta nao o usa, e a
    verificacao e no codigo e nao na revisao — continuidade do teste F-13 da F6.
    """
    fontes = Path(__file__).resolve().parents[2] / "src" / "analytics" / "semantic"
    for p in fontes.glob("*.py"):
        if p.name == "executor.py":
            continue
        texto = p.read_text(encoding="utf-8")
        assert "with_truth" not in texto or "sem camada de verdade" in texto, p.name


def test_contratos_e_catalogo_sem_problema_de_governanca(cfg):
    assert C.verify(cfg) == []
    assert contracts.verify(cfg) == []


def test_yaml_dos_contratos_continua_legivel(cfg):
    for p in sorted((ROOT / "config" / "kpis").glob("*.yaml")):
        doc = yaml.safe_load(p.read_text(encoding="utf-8"))
        assert doc["owner"] == "people-analytics"
        assert doc["status"] in C.STATUSES
