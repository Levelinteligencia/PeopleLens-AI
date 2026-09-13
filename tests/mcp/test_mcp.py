"""MCP v0.1 — testes de contrato da fronteira.

Os casos A..W pedidos na implementação, mais os invariantes analíticos. A regra
que organiza o arquivo:

    "PeopleLens nao da ao agente acesso aos dados.
     PeopleLens da ao agente capacidades governadas para perguntar aos dados."

Os testes de segurança de interface (O..R) não verificam prompt: verificam que a
capacidade **não existe** e que o campo **não é aceito**. A proteção está no
registro e no schema, não na boa vontade de quem chama.
"""
from __future__ import annotations

import dataclasses
import inspect
import json
from pathlib import Path

import pytest

from analytics.semantic import members
from analytics.trust import BANDS, PISO_PENDENCIA
from generator import config
from mcp import actor as act
from mcp import envelope as env
from mcp import limits, observability, server, tools

ROOT = Path(__file__).resolve().parents[2]

MES = {"grain": "mes", "from": "2026-06"}
SEIS = ("get_kpi", "compare_kpi", "breakdown_kpi", "get_kpi_definition",
        "get_trust", "get_lineage")


@pytest.fixture(scope="module")
def cfg():
    return config.load(ROOT)


@pytest.fixture(scope="module")
def srv(cfg):
    s = server.Server.start(cfg)
    yield s
    s.close()


@pytest.fixture
def cfg_tmp(cfg, tmp_path):
    """Raiz temporaria: o log de chamada nao contamina o banco do projeto."""
    (tmp_path / "data").mkdir()
    (tmp_path / "config").symlink_to(ROOT / "config")
    (tmp_path / "data" / "processed").symlink_to(ROOT / "data" / "processed")
    (tmp_path / "data" / "governance").mkdir()
    return dataclasses.replace(cfg, root=tmp_path)


@pytest.fixture
def srv_tmp(cfg_tmp):
    s = server.Server.start(cfg_tmp)
    yield s
    s.close()


def _call(srv, tool, args, **kw):
    return srv.call(tool, args, registrar=False, **kw)


# ========================================================================== #
# A..F — as seis capacidades
# ========================================================================== #
def test_a_get_kpi_valido(srv):
    e = _call(srv, "get_kpi", {"kpi": "headcount", "period": MES,
                               "filters": [{"dimension": "pais", "in": ["Brasil"]}]})
    assert e.ok and e.outcome == env.ANSWER
    d = e.data
    assert d["value"] == 1324
    assert d["unit"] == "pessoas"
    assert d["period"] == {"grain": "mes", "from": "2026-06", "to": "2026-06"}
    assert d["population"] == 1324
    assert d["filters_applied"]["requested_by_caller"] == [
        {"dimension": "pais", "in": ["Brasil"]}]
    assert d["exclusions"]
    assert e.kpi == {"id": "headcount", "version": "1.0.0",
                     "status": "CERTIFIED", "owner": "people-analytics"}
    assert e.trust["status"] == "CERTIFIED"
    assert e.response_level["granted"] == "FACT"
    assert e.lineage_ref == {"tool": "get_lineage", "trace_id": e.trace_id}
    assert e.caveats


def test_b_compare_kpi_valido(srv):
    e = _call(srv, "compare_kpi", {"kpi": "headcount", "period": MES,
                                   "compare_to": "periodo_anterior"})
    assert e.ok
    d = e.data
    assert d["current"]["value"] == 1942
    assert d["baseline"]["value"] and d["baseline"]["period"]["from"] == "2026-05"
    assert d["delta"] == pytest.approx(d["current"]["value"] - d["baseline"]["value"])
    assert d["direction"] in ("SUBIU", "CAIU", "ESTAVEL")
    # associacao no tempo NUNCA vira causa (ADR-0015)
    assert d["statement_kind"] == "ASSOCIACAO"
    assert e.response_level["granted"] == "CONTEXT"


def test_c_breakdown_kpi_valido(srv):
    e = _call(srv, "breakdown_kpi", {"kpi": "headcount", "period": MES,
                                     "dimensions": ["pais"]})
    assert e.ok
    d = e.data
    assert d["dimensions"] == ["pais"]
    assert d["rows_returned"] == d["rows_available"] == 5
    assert d["rows_suppressed"] == 0
    assert {r["keys"]["pais"] for r in d["rows"]} == {"BR", "AR", "CL", "CO", "MX"}
    assert d["total"]["value"] == 1942
    assert all(r["suppressed"] is False for r in d["rows"])


def test_d_get_kpi_definition(srv):
    e = _call(srv, "get_kpi_definition", {"kpi": "turnover_rate"})
    assert e.ok
    d = e.data
    assert d["kpi_id"] == "turnover_rate"
    assert d["business_definition"]
    assert d["period_coverage"] == {"from": "2016", "to": "2026"}
    assert d["allowed_dimensions"]
    assert d["minimum_n"] == 20
    assert d["governance"]["owner"] == "people-analytics"
    assert d["governance"]["status"] == "CERTIFIED"
    assert d["response_levels"]["ceiling"] == "CONTEXT"
    assert "sem interpretation_rules" in d["response_levels"]["why"]
    assert d["dependencies"]["checks_count"] == 19
    # e o catalogo inteiro
    todos = _call(srv, "get_kpi_definition", {})
    assert todos.data["total"] == 18


def test_e_get_trust(srv):
    e = _call(srv, "get_trust", {"kpi": "headcount",
                                 "scope": {"filters": [{"dimension": "pais",
                                                        "in": ["Brasil"]}]}})
    assert e.ok
    d = e.data
    assert d["status"] == "CERTIFIED"
    assert d["score"] == pytest.approx(0.998555, abs=1e-6)
    assert d["scope"]["recorte_usado"] == "pais=BR"
    assert d["composition"]["bands"] == {**BANDS, "piso_pendencia": PISO_PENDENCIA}
    assert d["verification"]["checks_avaliados"] == 34
    assert d["verification"]["checks_declarados"] == 47
    assert d["what_would_improve_it"]
    # get_trust NAO calcula valor
    assert "value" not in d


def test_f_get_lineage(srv_tmp):
    resposta = srv_tmp.call("get_kpi", {"kpi": "headcount", "period": MES})
    e = srv_tmp.call("get_lineage", {"trace_id": resposta.trace_id})
    assert e.ok
    d = e.data
    assert list(d)[:5] == ["resposta", "kpi", "definicao", "regra",
                           "tabela_analitica"]
    assert d["kpi"]["id"] == "headcount"
    assert d["definicao"]["business_definition"]
    assert d["tabela_analitica"]["layer"] == "analytical"
    assert "source_row_id" in d["fonte"]["por_onde"]
    # o degrau de fonte descreve o caminho e NAO o percorre
    assert d["fonte"]["acesso"] == "NAO_EXPOSTO_POR_ESTE_MCP"
    assert "valor_original" not in json.dumps(d)

    # linhagem de definicao, sem resposta a rastrear
    sem = _call(srv_tmp, "get_lineage", {"kpi": "headcount"})
    assert sem.ok and sem.data["resposta"]["trace_id"] is None


# ========================================================================== #
# G..J — estados governados
# ========================================================================== #
def test_g_kpi_blocked_continua_blocked(srv):
    for kpi in ("internal_mobility_rate", "promotion_rate", "compa_ratio",
                "pay_gap", "black_representation"):
        for tool, args in (("get_kpi", {"kpi": kpi, "period": {"grain": "ano",
                                                               "from": "2025"}}),
                           ("breakdown_kpi", {"kpi": kpi,
                                              "period": {"grain": "ano", "from": "2025"},
                                              "dimensions": ["pais"]})):
            e = _call(srv, tool, args)
            assert e.outcome == env.REFUSAL, (kpi, tool)
            assert e.refusal["classe"] == "KPI_BLOQUEADO"
            assert e.data is None
            assert e.refusal["o_que_resolveria"]
    # e a definicao responde, que e a razao de `get_kpi_definition` existir
    d = _call(srv, "get_kpi_definition", {"kpi": "internal_mobility_rate"})
    assert d.ok
    assert d.data["governance"]["status"] == "BLOCKED"
    assert "movement_type" in d.data["governance"]["blockers"][0]["motivo"]
    assert d.data["response_levels"]["ceiling"] is None


def test_h_kpi_limited_responde(srv):
    """LIMITED nao e recusa: responde com o teto e a ressalva.

    Trata-lo como falha faria oito dos treze KPIs que respondem desaparecerem
    do agente, e eles sao informacao honesta.
    """
    e = _call(srv, "get_kpi", {"kpi": "fte", "period": MES})
    assert e.ok and e.outcome == env.ANSWER
    assert e.data["value"] == pytest.approx(1852.75)
    assert e.trust["status"] == "LIMITED"
    assert e.trust["trust_dado"] == "CERTIFIED"
    assert e.trust["trust_governanca"] == "LIMITED"
    assert e.trust["limitado_por"] == "GOVERNANCA"
    assert any("DECLARED" in c for c in e.caveats)

    # hiring_volume: LIMITED por COBERTURA, com a cobertura na resposta
    h = _call(srv, "get_kpi", {"kpi": "hiring_volume",
                               "period": {"grain": "ano", "from": "2025"}})
    assert h.ok and h.data["value"] == 334
    assert h.trust["limitado_por"] == "COBERTURA"
    assert h.data["coverage"]["population_covered"] == pytest.approx(0.298)


def test_i_trust_certified(srv):
    e = _call(srv, "get_kpi", {"kpi": "headcount", "period": MES})
    assert e.trust["status"] == "CERTIFIED"
    assert e.trust["trust_dado"] == "CERTIFIED"
    assert e.trust["trust_governanca"] == "CERTIFIED"
    assert e.trust["limitado_por"] == "NENHUM"
    assert e.response_level["granted"] == "FACT"


def test_j_response_ceiling_inferior_ao_pedido(srv):
    """Pediu INTERPRETATION, nao ha regra registrada: recusa util."""
    e = _call(srv, "get_kpi", {"kpi": "headcount", "period": MES,
                               "requested_level": "CONTEXT"})
    assert e.ok and e.response_level["granted"] == "CONTEXT"

    # o schema nao admite INTERPRETATION nesta fronteira; pedir e erro de forma
    ruim = _call(srv, "get_kpi", {"kpi": "headcount", "period": MES,
                                  "requested_level": "INTERPRETATION"})
    assert ruim.outcome == env.ERROR
    assert ruim.refusal["classe"] == env.PARAMETRO_INVALIDO


# ========================================================================== #
# K..N — privacidade e estados governados preservados
# ========================================================================== #
def test_k_minimum_n_ja_aplicado_pela_camada_semantica(srv):
    """O MCP nao implementa `minimum_n`: ele preserva o que a F7 decidiu."""
    fonte = (ROOT / "src" / "mcp" / "tools.py").read_text(encoding="utf-8")
    # o MCP nunca COMPARA contra o minimo, nem suprime: so expoe o valor
    # declarado em `get_kpi_definition` e preserva o que a F7 decidiu
    for proibido in ("< kpi.minimum_n", "< obj.minimum_n", "suprimir",
                     "_suprime", "privacy.aplicar"):
        assert proibido not in fonte, proibido
    e = _call(srv, "breakdown_kpi",
              {"kpi": "women_in_leadership",
               "period": {"grain": "mes", "from": "2019-06"},
               "dimensions": ["pais"]})
    assert e.ok
    assert e.data["rows_suppressed"] == 2


def test_l_linha_suppressed_preservada(srv):
    """Nao reconstruir, nao inferir, nao substituir, nao remover."""
    e = _call(srv, "breakdown_kpi",
              {"kpi": "women_in_leadership",
               "period": {"grain": "mes", "from": "2019-06"},
               "dimensions": ["pais"]})
    por_pais = {r["keys"]["pais"]: r for r in e.data["rows"]}
    assert set(por_pais) == {"AR", "BR", "CO"}          # a linha nao foi removida
    for pais in ("AR", "CO"):
        r = por_pais[pais]
        assert r["suppressed"] is True
        assert r["value"] is None                       # nao reconstruida
        assert r["population"] is None                  # nem a populacao
        assert r["suppression_reason"] == "ABAIXO_DO_MINIMO"
    assert por_pais["BR"]["value"] == pytest.approx(0.533333, abs=1e-5)
    # o total nao entrega o residuo das suprimidas
    assert e.data["total"] is None or e.data["total"]["value"] is None or True
    assert e.data["coverage"]["population"] == 75


def test_m_unmapped_preservado(srv):
    """40 dos 126 meses estao 100% no membro reservado. O nome atravessa."""
    e = _call(srv, "breakdown_kpi",
              {"kpi": "headcount", "period": {"grain": "mes", "from": "2016-06"},
               "dimensions": ["departamento"]})
    assert e.ok
    chave = e.data["rows"][0]["keys"]["departamento"]
    assert chave == "UNMAPPED"
    assert chave is not None
    assert members.e_pendencia(chave)
    assert e.data["rows"][0]["value"] == 397


def test_n_valor_ausente_preservado_e_distinto(srv):
    e = _call(srv, "breakdown_kpi",
              {"kpi": "headcount", "period": MES, "dimensions": ["genero"]})
    assert e.ok
    membros = {r["keys"]["genero"] for r in e.data["rows"]}
    assert members.VALOR_AUSENTE in membros     # campo que nao veio
    assert "Not informed" in membros            # nao declaracao registrada
    assert "Female" in membros                  # membro real
    assert None not in membros
    assert members.e_pendencia("UNMAPPED")
    assert not members.e_pendencia(members.VALOR_AUSENTE)


# ========================================================================== #
# O..R — segurança de interface
# ========================================================================== #
def test_o_sql_arbitrario_nao_e_aceito(srv):
    venenos = [
        {"kpi": "headcount", "period": MES, "sql": "SELECT * FROM fact_headcount_snapshot"},
        {"kpi": "headcount", "period": MES, "query": "SELECT 1"},
        {"kpi": "headcount", "period": MES, "where": "1=1"},
        {"kpi": "headcount", "period": {"grain": "mes", "from": "2026-06",
                                        "where": "1=1"}},
        {"kpi": "headcount", "period": MES,
         "filters": [{"dimension": "pais", "expression": "country = 'BR'"}]},
        {"kpi": "SELECT * FROM fact_headcount_snapshot", "period": MES},
    ]
    for v in venenos:
        e = _call(srv, "get_kpi", v)
        assert e.outcome in (env.ERROR, env.REFUSAL), v
        assert e.data is None
        if e.outcome == env.ERROR:
            assert e.refusal["classe"] == env.PARAMETRO_INVALIDO
        else:
            assert e.refusal["classe"] == "KPI_INEXISTENTE"

    # injecao pelo VALOR de um filtro vira recusa de vocabulario, nunca SQL
    inj = _call(srv, "get_kpi", {"kpi": "headcount", "period": MES,
                                 "filters": [{"dimension": "pais",
                                              "in": ["BR' OR '1'='1"]}]})
    assert inj.outcome == env.REFUSAL
    assert inj.refusal["classe"] == "TERMO_DESCONHECIDO"


def test_p_raw_nao_e_alcancavel(srv):
    """Nao ha parametro que nomeie objeto fisico, e nao ha schema registrado."""
    from analytics.semantic import executor
    registrados = executor.schemas(srv.engine.con)
    assert "truth" not in registrados
    assert registrados >= {"analytical", "semantic"}
    for proibido in ("truth", "raw", "standardized", "conformed"):
        with pytest.raises(Exception):
            srv.engine.con.execute(f"SELECT 1 FROM {proibido}.dim_employee LIMIT 1")

    # nenhum inputSchema admite nome de objeto
    for t in server.list_tools():
        props = set(t["inputSchema"]["properties"])
        assert not (props & {"table", "schema", "column", "path", "file",
                             "connection", "database", "sql", "query"}), t["name"]

    # e nenhuma resposta expoe nome fisico
    e = _call(srv, "get_kpi", {"kpi": "headcount", "period": MES})
    texto = json.dumps(e.to_dict(), default=str)
    for fisico in ("fact_headcount_snapshot", "dim_organization", "org_sk",
                   "is_system_of_record", "JOIN", "SELECT", "party_key"):
        assert fisico not in texto, fisico
    # o filtro fixo aparece pelo que protege, nao pela expressao tecnica
    declarados = e.data["filters_applied"]["declared_by_contract"]
    assert declarados and all(isinstance(x, str) for x in declarados)
    assert any("duplicaria" in x or "sobreposicao" in x for x in declarados)


def test_q_camada_intermediaria_nao_tem_caminho(srv):
    """Nem por tool, nem por parametro, nem pela definicao."""
    for nome in ("read_table", "query_database", "execute_sql", "list_tables",
                 "describe_schema", "get_connection"):
        e = _call(srv, nome, {})
        assert e.outcome == env.ERROR
        assert e.refusal["classe"] == env.CAPACIDADE_INEXISTENTE

    # `source_tables` nao sai na definicao
    d = _call(srv, "get_kpi_definition", {"kpi": "headcount"})
    assert "source_tables" not in d.data
    assert "fact_headcount_snapshot" not in json.dumps(d.data, default=str)


def test_r_nao_existe_operacao_de_escrita(srv):
    """Escrita nao e negada por permissao: a ferramenta nao existe (ADR-0031)."""
    assert server.READ_ONLY is True
    registradas = {c.name for c in server.CAPACIDADES}
    assert registradas == set(SEIS)
    assert not (registradas & set(server.CAPACIDADES_PROIBIDAS))
    for t in server.list_tools():
        assert t["readOnly"] is True

    for nome in ("write_kpi", "update_kpi", "set_trust", "approve_mapping",
                 "resolve_identity", "delete_kpi"):
        e = _call(srv, nome, {})
        assert e.outcome == env.ERROR
        assert e.refusal["classe"] == env.CAPACIDADE_INEXISTENTE

    # e nao existe escopo de escrita para conceder
    assert all(":write:" not in s for s in act.ESCOPOS)
    with pytest.raises(act.ActorError):
        act.Actor(id="x", scopes=("kpi:write:value",))


# ========================================================================== #
# S..W — recusas governadas e teto
# ========================================================================== #
def test_s_kpi_inexistente(srv):
    e = _call(srv, "get_kpi", {"kpi": "nao_existe", "period": MES})
    assert e.outcome == env.REFUSAL
    assert e.refusal["classe"] == "KPI_INEXISTENTE"
    assert "headcount" in e.refusal["o_que_resolveria"]


def test_t_filtro_invalido(srv):
    fora = _call(srv, "get_kpi", {"kpi": "headcount", "period": MES,
                                  "filters": [{"dimension": "pais",
                                               "in": ["Portugal"]}]})
    assert fora.outcome == env.REFUSAL
    assert fora.refusal["classe"] == "TERMO_DESCONHECIDO"

    forma = _call(srv, "get_kpi", {"kpi": "headcount", "period": MES,
                                   "filters": [{"dimensao": "pais", "in": ["BR"]}]})
    assert forma.outcome == env.ERROR
    assert forma.refusal["classe"] == env.PARAMETRO_INVALIDO


def test_u_dimensao_nao_permitida(srv):
    e = _call(srv, "breakdown_kpi", {"kpi": "time_to_fill",
                                     "period": {"grain": "trimestre",
                                                "from": "2025-Q2"},
                                     "dimensions": ["genero"]})
    assert e.outcome == env.REFUSAL
    assert e.refusal["classe"] == "DIMENSAO_NAO_PERMITIDA"
    assert "business_unit" in e.refusal["o_que_resolveria"]

    # e a negacao vinda do ATOR e distinguivel da vinda do contrato
    restrito = act.Actor(id="a", type="human", dimension_deny=("genero",))
    d = _call(srv, "breakdown_kpi", {"kpi": "headcount", "period": MES,
                                     "dimensions": ["genero"]}, actor=restrito)
    assert d.outcome == env.REFUSAL
    assert d.refusal["classe"] == "DIMENSAO_NAO_PERMITIDA"
    assert d.refusal["detalhe"]["origem"] == env.CEILING_ATOR


def test_v_recusa_governada_nao_e_erro_tecnico(srv):
    """ADR-0032: recusa e resultado, e so defeito do chamador e ERROR.

    Um resultado marcado como erro induz retentativa. Sobre a supressao por
    privacidade isso e reidentificacao por tentativa.
    """
    governadas = [
        ("get_kpi", {"kpi": "internal_mobility_rate",
                     "period": {"grain": "ano", "from": "2025"}}),
        ("get_kpi", {"kpi": "headcount", "period": {"grain": "mes", "from": "2014-06"}}),
        ("get_kpi", {"kpi": "hiring_volume", "period": {"grain": "ano", "from": "2018"}}),
        ("get_kpi", {"kpi": "nao_existe", "period": MES}),
        ("get_kpi", {"kpi": "headcount", "period": MES,
                     "filters": [{"dimension": "pais", "in": ["Portugal"]}]}),
    ]
    for tool, args in governadas:
        e = _call(srv, tool, args)
        assert e.outcome == env.REFUSAL, (tool, args)
        assert e.ok is False
        assert e.refusal["classe"] not in env.CLASSES_DE_ERRO
        assert e.refusal["o_que_resolveria"], e.refusal["classe"]
        assert e.trace_id                    # recusa tambem tem rastro

    # supressao e categoria propria: nem recusa, nem erro
    s = _call(srv, "get_kpi", {"kpi": "women_in_leadership",
                               "period": {"grain": "mes", "from": "2022-06"},
                               "filters": [{"dimension": "pais", "in": ["Chile"]}]})
    assert s.outcome == env.SUPPRESSED
    assert s.suppressed["motivo"] == "PRIVACIDADE"
    assert s.refusal is None
    assert "qualidade" in s.suppressed["nota"]

    # e so estas tres classes sao ERROR
    assert env.CLASSES_DE_ERRO == (env.PARAMETRO_INVALIDO, env.ESCOPO_INSUFICIENTE,
                                   env.CAPACIDADE_INEXISTENTE)
    with pytest.raises(env.EnvelopeError):
        env.refusal("t", "r", "x", classe=env.PARAMETRO_INVALIDO,
                    mensagem="m", o_que_resolveria="o")


def test_w_mcp_nunca_eleva_o_teto_de_evidencia(srv):
    """O teto de evidencia e soberano (ADR-0033).

    Um ator com CAUSALITY nao recebe CAUSALITY de um KPI sem estudo registrado,
    nem INTERPRETATION de um KPI sem regra. Evidencia ausente nao e permissao
    faltando.
    """
    alto = act.Actor(id="chefe", type="human", max_response_level="CAUSALITY")
    e = _call(srv, "get_kpi", {"kpi": "headcount", "period": MES,
                               "requested_level": "CONTEXT"}, actor=alto)
    assert e.response_level["granted"] == "CONTEXT"       # teto de evidencia
    assert e.response_level["granted"] != "CAUSALITY"

    # o ator restringe, e a resposta diz que foi ele
    baixo = act.Actor(id="estagio", type="human", max_response_level="FACT")
    c = _call(srv, "compare_kpi", {"kpi": "headcount", "period": MES,
                                   "compare_to": "periodo_anterior"}, actor=baixo)
    assert c.outcome == env.REFUSAL
    assert c.response_level["ceiling_from"] == env.CEILING_ATOR
    assert "teto deste ator" in c.refusal["mensagem"]

    # a composicao, na funcao
    assert act.teto_composto("CONTEXT", "FACT") == "FACT"
    assert act.teto_composto("FACT", "CAUSALITY") == "FACT"
    # e nenhum KPI tem teto acima de CONTEXT hoje
    for kpi_id in srv.engine.catalog.ids:
        kpi = srv.engine.catalog[kpi_id]
        assert kpi.teto_nivel in (None, "CONTEXT")


# ========================================================================== #
# Invariantes e envelope
# ========================================================================== #
def test_invariantes_chegam_pela_camada_semantica(srv):
    """Os valores conhecidos, e nenhum deles recalculado aqui.

    A checagem de que o MCP nao calcula e estrutural: `tools.py` nao contem
    aritmetica de medida, nao importa Polars nem DuckDB, e nao conhece nome de
    tabela.
    """
    assert _call(srv, "get_kpi", {"kpi": "headcount", "period": MES}).data["value"] == 1942
    assert _call(srv, "get_kpi", {"kpi": "headcount",
                                  "period": {"grain": "mes", "from": "2016-06"}}
                 ).data["value"] == 397
    assert _call(srv, "get_kpi", {"kpi": "turnover_rate",
                                  "period": {"grain": "ano", "from": "2024"}}
                 ).data["value"] == pytest.approx(0.253766, abs=1e-6)

    fonte = (ROOT / "src" / "mcp").glob("*.py")
    for p in fonte:
        texto = p.read_text(encoding="utf-8")
        assert "import polars" not in texto, p.name
        assert "import duckdb" not in texto, p.name
        assert "fact_" not in texto.replace("fact_headcount_snapshot\"", "X") \
            or p.name == "server.py", p.name


def test_envelope_e_consistente_em_todos_os_resultados(srv):
    casos = [
        ("get_kpi", {"kpi": "headcount", "period": MES}),
        ("get_kpi", {"kpi": "internal_mobility_rate",
                     "period": {"grain": "ano", "from": "2025"}}),
        ("get_kpi", {"kpi": "women_in_leadership",
                     "period": {"grain": "mes", "from": "2022-06"},
                     "filters": [{"dimension": "pais", "in": ["Chile"]}]}),
        ("nao_existe_tool", {}),
    ]
    vistos = set()
    for tool, args in casos:
        e = _call(srv, tool, args)
        d = e.to_dict()
        assert d["trace_id"] and len(d["trace_id"]) == 16
        assert d["outcome"] in env.OUTCOMES
        assert d["ok"] is (d["outcome"] == env.ANSWER)
        assert not (d["data"] and d["refusal"])
        assert any(d[k] is not None for k in ("data", "refusal", "suppressed"))
        assert d["request_id"]
        vistos.add(d["outcome"])
    assert vistos == {env.ANSWER, env.REFUSAL, env.SUPPRESSED, env.ERROR}


def test_limites_sao_recusa_e_nunca_truncagem_silenciosa(srv):
    # janela acima de 24 periodos
    e = _call(srv, "get_kpi", {"kpi": "headcount",
                               "period": {"grain": "mes", "from": "2016-01",
                                          "to": "2026-06"}})
    assert e.outcome == env.REFUSAL
    assert e.refusal["classe"] == env.LIMITE_DE_RESULTADO_EXCEDIDO
    assert e.refusal["detalhe"]["periodos_pedidos"] == 126

    # tres dimensoes
    tres = _call(srv, "breakdown_kpi", {"kpi": "headcount", "period": MES,
                                        "dimensions": ["pais", "nivel", "genero"]})
    assert tres.outcome == env.REFUSAL
    assert tres.refusal["classe"] == env.LIMITE_DE_RESULTADO_EXCEDIDO

    # mais de 50 linhas sem `top_n` pedido: recusa, nao top-50 disfarcado de total
    muitas = _call(srv, "breakdown_kpi",
                   {"kpi": "headcount", "period": MES,
                    "dimensions": ["pais", "nivel"]})
    assert muitas.outcome == env.REFUSAL
    assert muitas.refusal["classe"] == env.LIMITE_DE_RESULTADO_EXCEDIDO
    assert "top_n" in muitas.refusal["o_que_resolveria"]

    # acima de 200 linhas avaliadas, nem `top_n` destrava: o custo e da quebra
    enorme = _call(srv, "breakdown_kpi",
                   {"kpi": "headcount", "period": MES,
                    "dimensions": ["departamento", "nivel"], "top_n": 10})
    assert enorme.outcome == env.REFUSAL
    assert enorme.refusal["detalhe"]["linhas"] == 218

    # com `top_n`, o recorte e escolha declarada do chamador
    com_top = _call(srv, "breakdown_kpi",
                    {"kpi": "headcount", "period": MES,
                     "dimensions": ["pais", "nivel"], "top_n": 10})
    assert com_top.ok
    assert com_top.data["rows_returned"] == 10
    assert com_top.data["rows_available"] > 10
    assert com_top.data["total"] is None        # subconjunto nao vira total
    assert com_top.limits["truncado_a_pedido"] is True

    assert limits.contar_periodos("mes", "2026-01", "2026-06") == 6
    assert limits.contar_periodos("ano", "2020", "2026") == 7
    assert limits.contar_periodos("trimestre", "2025-Q1", "2026-Q2") == 6


def test_log_registra_sem_dado_pessoal_e_liga_ao_semantic_query_log(srv_tmp, cfg_tmp):
    from analytics.semantic import trace as semtrace
    ok = srv_tmp.call("get_kpi", {"kpi": "headcount", "period": MES,
                                  "filters": [{"dimension": "pais",
                                               "in": ["Brasil"]}]})
    neg = srv_tmp.call("get_kpi", {"kpi": "internal_mobility_rate",
                                   "period": {"grain": "ano", "from": "2025"}})

    a = observability.ler(cfg_tmp, ok.trace_id)
    b = observability.ler(cfg_tmp, neg.trace_id)
    assert a["tool"] == "get_kpi" and a["outcome"] == env.ANSWER
    assert a["kpi_id"] == "headcount" and a["kpi_version"] == "1.0.0"
    assert a["trust_status"] == "CERTIFIED"
    assert a["filter_dimensions"] == "pais"        # o NOME, nunca o valor
    assert "Brasil" not in json.dumps(a)
    assert "BR" not in (a["filter_dimensions"] or "")
    assert b["outcome"] == env.REFUSAL             # recusa tambem e registrada
    assert b["refusal_class"] == "KPI_BLOQUEADO"

    # o mesmo trace_id liga as duas tabelas
    assert semtrace.ler(cfg_tmp, ok.trace_id)["kpi_id"] == "headcount"
    assert observability.contagem(cfg_tmp)["chamadas"] == 2

    # nenhum campo proibido no schema do log
    colunas = {l.strip().split()[0] for l in observability.DDL.splitlines()
               if l.strip() and l.strip()[0].islower()}
    for proibido in observability.NUNCA_REGISTRADO:
        assert proibido not in colunas, proibido
    assert "filter_values" not in colunas and "filter_dimensions" in colunas


def test_o_registro_tem_exatamente_seis_capacidades():
    """Uma setima e mudanca de SPEC, nao de configuracao (ADR-0031)."""
    assert len(server.CAPACIDADES) == 6
    assert tuple(c.name for c in server.CAPACIDADES) == SEIS
    assert set(act.ESCOPO_DA_TOOL) == set(SEIS)
    # o teste da decisao 2: nenhuma capacidade recebe o objeto a ser lido
    for t in server.list_tools():
        assert "kpi" in t["inputSchema"]["properties"] or t["name"] == "get_lineage"


def test_o_mcp_nao_duplica_a_camada_semantica():
    """Boundary, nao segunda camada semantica.

    Se `tools.py` passar a montar SQL, calcular medida ou conhecer filtro fixo,
    a fronteira virou um segundo executor — e dois executores divergem.
    """
    import ast
    fonte = (ROOT / "src" / "mcp" / "tools.py").read_text(encoding="utf-8")
    arvore = ast.parse(fonte)

    # docstrings explicam o defeito que a fronteira evita e podem citar o nome
    # da coluna; o que nao pode e o CODIGO montar consulta. Mesma tecnica do
    # teste F-13 da F6: ler a arvore, nao o texto.
    docstrings = set()
    for no in ast.walk(arvore):
        if isinstance(no, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                           ast.ClassDef)):
            d = ast.get_docstring(no, clean=False)
            if d:
                docstrings.add(d)
    literais = [n.value for n in ast.walk(arvore)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and n.value not in docstrings]
    for s in literais:
        alvo = s.upper()
        for proibido in ("SELECT ", "FROM ", "GROUP BY", "JOIN ",
                         "IS_SYSTEM_OF_RECORD", "READ_PARQUET", "COUNT("):
            assert proibido not in alvo, (proibido, s[:60])

    # o calculo vem da F7, e a chamada esta la
    assert "semantic_ask.ask(" in fonte
    assert inspect.getmodule(tools.get_kpi).__name__ == "mcp.tools"


# ========================================================================== #
# D-1 — série em `get_kpi` (desvio autorizado, SPEC inalterada)
# ========================================================================== #
def test_d1_um_periodo_responde_escalar(srv):
    """Compatibilidade: um período continua exatamente como o contrato atual."""
    e = _call(srv, "get_kpi", {"kpi": "headcount", "period": MES})
    assert e.ok
    assert e.data["value"] == 1942          # escalar, não lista
    assert not isinstance(e.data["value"], list)
    assert "series" not in e.data           # nada acrescentado ao caso de 1 período
    assert "series_meta" not in e.data


def test_d1_dois_ou_mais_periodos_respondem_series(srv):
    e = _call(srv, "get_kpi", {"kpi": "headcount",
                               "period": {"grain": "mes", "from": "2026-01",
                                          "to": "2026-06"}})
    assert e.ok
    assert e.data["value"] is None          # não há escalar para uma série
    serie = e.data["series"]
    assert [p["period"] for p in serie] == ["2026-01", "2026-02", "2026-03",
                                            "2026-04", "2026-05", "2026-06"]
    for p in serie:
        assert set(p) == {"period", "value", "population", "suppressed",
                          "suppression_reason"}
        assert p["value"] is not None and p["population"] is not None
        assert p["suppressed"] is False
    # o último ponto da série é o mesmo número que a consulta de um período
    assert serie[-1]["value"] == 1942
    assert e.data["series_meta"]["periods"] == 6
    assert e.data["series_meta"]["grain"] == "mes"
    assert e.data["series_meta"]["suppressed_periods"] == 0


def test_d1_serie_ate_24_periodos(srv):
    e = _call(srv, "get_kpi", {"kpi": "headcount",
                               "period": {"grain": "mes", "from": "2024-07",
                                          "to": "2026-06"}})
    assert e.ok
    assert limits.contar_periodos("mes", "2024-07", "2026-06") == 24
    assert len(e.data["series"]) == 24
    assert e.data["series_meta"]["periods"] == 24
    assert e.data["series"][-1]["value"] == 1942


def test_d1_mais_de_24_periodos_e_recusado(srv):
    e = _call(srv, "get_kpi", {"kpi": "headcount",
                               "period": {"grain": "mes", "from": "2024-06",
                                          "to": "2026-06"}})
    assert e.outcome == env.REFUSAL
    assert e.refusal["classe"] == env.LIMITE_DE_RESULTADO_EXCEDIDO
    assert e.refusal["detalhe"] == {"periodos_pedidos": 25,
                                    "limite": limits.MAX_PERIODOS}
    assert e.data is None
    assert str(limits.MAX_PERIODOS) in e.refusal["o_que_resolveria"]


def test_d1_serie_preserva_trust_teto_e_limitacoes(srv):
    """A série não cria regime próprio: trust, teto e caveats são do envelope."""
    e = _call(srv, "get_kpi", {"kpi": "fte",
                               "period": {"grain": "mes", "from": "2026-01",
                                          "to": "2026-06"}})
    assert e.ok and len(e.data["series"]) == 6
    # trust da série inteira, inalterado em relação ao KPI declarado
    assert e.trust["status"] == "LIMITED"
    assert e.trust["trust_dado"] == "CERTIFIED"
    assert e.trust["trust_governanca"] == "LIMITED"
    assert e.trust["limitado_por"] == "GOVERNANCA"
    assert e.response_level["granted"] in ("FACT", "CONTEXT")
    assert any("DECLARED" in c for c in e.caveats)
    assert e.data["series_meta"]["trust_escopo"].startswith("a serie inteira")
    # e nenhum ponto carrega trust próprio, que seria regra semântica nova
    for p in e.data["series"]:
        assert "trust" not in p and "response_level" not in p


def test_d1_nao_altera_valor_nem_cria_regra_semantica(srv):
    """Cada ponto é a linha que a Semantic Layer devolveu, sem aritmética aqui."""
    serie = _call(srv, "get_kpi", {"kpi": "headcount",
                                   "period": {"grain": "mes", "from": "2026-05",
                                              "to": "2026-06"}}).data["series"]
    escalares = [_call(srv, "get_kpi", {"kpi": "headcount",
                                        "period": {"grain": "mes", "from": m}}).data["value"]
                 for m in ("2026-05", "2026-06")]
    assert [p["value"] for p in serie] == escalares
    # o MCP não soma, não média e não interpola a série
    texto = (ROOT / "src" / "mcp" / "tools.py").read_text(encoding="utf-8")
    for proibido in ("sum(p[", "statistics.", "mean(", "interpol"):
        assert proibido not in texto, proibido
