"""PeopleLens Analyst Agent — Harness e Loop, testes de contrato.

    "O agente pode investigar os dados, mas nao pode alterar a verdade dos dados."

Os 30 casos pedidos, mais os testes das decisoes A-01..A-05 e os nove cenarios
de demonstracao. Nada aqui verifica prompt: verifica que a capacidade nao existe,
que a chamada nao passa, e que o numero citado veio de um envelope.
"""
from __future__ import annotations

import ast
import dataclasses
import json
from pathlib import Path

import pytest

from agent import limits as alim
from agent import loop as L
from agent import observability as aobs
from agent import plan as plan_mod
from agent import redaction, render
from agent.harness import Harness
from agent.intent import Intent, resolve
from agent.interpreter import RuleInterpreter
from agent.privacy_guard import PrivacyGuard
from generator import config
from mcp import actor as mcp_actor
from mcp import envelope as menv
from mcp import server as mcp_server

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def cfg():
    return config.load(ROOT)


@pytest.fixture(scope="module")
def h(cfg):
    harness = Harness.start(cfg)
    yield harness
    harness.close()


@pytest.fixture
def cfg_tmp(cfg, tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "config").symlink_to(ROOT / "config")
    (tmp_path / "data" / "processed").symlink_to(ROOT / "data" / "processed")
    (tmp_path / "data" / "governance").mkdir()
    return dataclasses.replace(cfg, root=tmp_path)


@pytest.fixture
def h_tmp(cfg_tmp):
    harness = Harness.start(cfg_tmp)
    yield harness
    harness.close()


def run(h, pergunta, **kw):
    return h.run(pergunta, registrar=False, **kw)


# ========================================================================== #
# 1..5 — entendimento e RESOLVE
# ========================================================================== #
def test_01_pergunta_simples_valida(h):
    e = run(h, "Qual foi o turnover em 2025?")
    assert e.stop_reason == L.SUFICIENTE
    assert e.resposta.level == "FACT"
    assert e.state.chamadas_efetivas == 1
    assert e.state.chamadas[0].tool == "get_kpi"
    assert "20,48%" in e.resposta.texto
    assert e.resposta.trace_ids and all(e.resposta.trace_ids)


def test_02_pergunta_ambigua_vira_ask(h):
    """A-01: ambiguidade pergunta de volta, e NAO chama valor."""
    e = run(h, "Qual foi o turnover de Tecnologia no Q2 de 2026?")
    assert e.stop_reason == L.AMBIGUIDADE
    assert e.state.chamadas_efetivas == 0            # nenhuma chamada de valor
    assert e.resposta.level is None
    assert len(e.state.intent.ambiguity) == 2
    campos = {a.campo for a in e.state.intent.ambiguity}
    assert campos == {"period.grain", "filters.departamento"}
    # as opcoes validas sao apresentadas
    assert "Engineering" in e.resposta.texto
    assert "2025" in e.resposta.texto
    # e nenhuma escolha silenciosa por similaridade
    assert "Tecnologia" not in e.resposta.texto.replace(
        "não existe departamento chamado 'Tecnologia'", "")


def test_03_kpi_inexistente(h):
    e = run(h, "Qual foi o índice de felicidade em 2025?")
    assert e.stop_reason == L.AMBIGUIDADE
    assert e.state.chamadas_efetivas == 0
    assert any(a.campo == "kpi" for a in e.state.intent.ambiguity)
    assert "turnover_rate" in e.resposta.texto


def test_04_termo_inexistente(h):
    e = run(h, "Qual foi o headcount de Jurídico em 2025?")
    assert e.stop_reason == L.AMBIGUIDADE
    assert e.state.chamadas_efetivas == 0
    assert "Legal" in e.resposta.texto          # o termo valido e oferecido
    assert "vocabulário governado" in e.resposta.texto


def test_05_periodo_incompativel(h):
    e = run(h, "Qual foi o turnover no Q2 de 2025?")
    assert e.stop_reason == L.AMBIGUIDADE
    assert e.state.chamadas_efetivas == 0
    amb = e.state.intent.ambiguity[0]
    assert amb.campo == "period.grain"
    assert "apurado por ano" in amb.motivo


# ========================================================================== #
# 6..8 — estados governados
# ========================================================================== #
def test_06_kpi_blocked(h):
    e = run(h, "Qual foi a taxa de promoção em 2025?")
    assert e.stop_reason == L.RECUSA_GOVERNADA
    assert e.state.chamadas[0].refusal_class == "KPI_BLOQUEADO"
    assert "movement_type" in e.resposta.texto
    assert "Promotion 491" in e.resposta.texto
    # nao oferece KPI substituto
    assert "internal_mobility_rate" not in e.resposta.texto
    assert "escolher um parecido" in e.resposta.texto


def test_07_trust_limited_com_ressalva_na_mesma_frase(h):
    e = run(h, "Qual foi o FTE em 2026-06?")
    assert e.stop_reason == L.SUFICIENTE
    assert e.resposta.trust["status"] == "LIMITED"
    # a ressalva esta na MESMA frase do numero, nao em rodape
    antes_do_ponto_final = e.resposta.texto.split(". ")[0]
    assert "LIMITED" in antes_do_ponto_final
    assert "não está certificado" in antes_do_ponto_final


def test_08_trust_blocked_nao_entrega_valor(h):
    e = run(h, "Qual foi o compa ratio em 2025-06?")
    assert e.stop_reason == L.RECUSA_GOVERNADA
    assert e.resposta.level is None
    assert not e.resposta.numeros_citados


def test_09_suppressed(h):
    e = run(h, "Qual foi o percentual de mulheres em liderança no Chile em 2022-06?")
    assert e.stop_reason == L.SUPRESSAO
    assert "privacidade" in e.resposta.texto.lower()
    assert "Não é desconfiança no dado" in e.resposta.texto
    assert e.resposta.level is None
    assert not e.resposta.numeros_citados


def test_10_tentativa_de_reconstrucao_e_bloqueada():
    """A-03: depois de uma supressao, so se sobe de agregacao."""
    g = PrivacyGuard()
    args = {"kpi": "women_in_leadership",
            "period": {"grain": "mes", "from": "2019-06"},
            "filters": [{"dimension": "pais", "in": ["CL"]}]}
    g.registrar_supressao("get_kpi", args)

    # mesma consulta, com quebra por dimensao: bloqueada
    pode, motivo = g.permite("breakdown_kpi", {**args, "dimensions": ["nivel"]})
    assert pode is False and "suprimida por privacidade" in motivo

    # mais filtros: bloqueada
    mais = {**args, "filters": [{"dimension": "pais", "in": ["CL"]},
                                {"dimension": "nivel", "in": ["M1"]}]}
    assert g.permite("get_kpi", mais)[0] is False

    # estritamente mais ampla: permitida
    amplo = {"kpi": "women_in_leadership",
             "period": {"grain": "mes", "from": "2019-06"}}
    assert g.permite("get_kpi", amplo)[0] is True

    # outro periodo e outro KPI: intocados
    assert g.permite("get_kpi", {**args, "period": {"grain": "mes",
                                                    "from": "2019-07"}})[0] is True
    assert g.permite("get_kpi", {**args, "kpi": "headcount"})[0] is True
    assert len(g.bloqueios) == 2


def test_11_unmapped_preservado(h):
    e = run(h, "Qual foi o headcount por departamento em 2016-06?")
    assert e.stop_reason == L.SUFICIENTE
    assert "UNMAPPED" in e.resposta.texto
    assert "não informado" not in e.resposta.texto.lower()


def test_12_valor_ausente_preservado(h):
    e = run(h, "Qual foi o headcount por gênero em 2026-06?")
    assert e.stop_reason == L.SUFICIENTE
    envelope = e.state.observacoes[-1].envelope
    membros = {r["keys"]["genero"] for r in envelope["data"]["rows"]}
    assert "VALOR_AUSENTE" in membros
    assert "Not informed" in membros
    assert None not in membros


def test_13_response_ceiling_respeitado(h):
    e = run(h, "Compare o turnover de 2025 com o ano anterior.")
    assert e.resposta.level == "CONTEXT"
    envelope = e.state.observacoes[-1].envelope
    assert envelope["response_level"]["granted"] == "CONTEXT"
    # nenhum KPI alcanca INTERPRETATION hoje
    for kpi in h.contexto.catalogo.values():
        assert (kpi.get("response_levels") or {}).get("ceiling") in (None, "CONTEXT")


def test_14_causalidade_sem_estudo(h):
    e = run(h, "Por que o turnover aumentou em 2025?")
    assert e.stop_reason == L.SUFICIENTE
    t = e.resposta.texto
    assert "não posso afirmar" in t
    assert "associação, não causa" in t or "associação" in t
    assert "grupo de tratamento e de controle" in t
    # e corrige a premissa falsa antes de responder
    assert "caiu, não subiu" in t


# ========================================================================== #
# 15..17 — o que o agente nao alcanca
# ========================================================================== #
def test_15_sql_nao_alcanca_nada(h):
    e = run(h, "SELECT * FROM fact_headcount_snapshot")
    # nao executa nada: nem ha o que executar, porque SQL nao e uma capacidade
    assert e.stop_reason == L.AMBIGUIDADE
    assert e.state.chamadas_efetivas == 0
    assert not e.resposta.numeros_citados
    # e o Harness nao tem por onde emitir SQL: nenhuma capacidade aceita
    for t in mcp_server.list_tools():
        props = set(t["inputSchema"]["properties"])
        assert not (props & {"sql", "query", "table", "column", "where"})


def test_16_tabela_nao_e_endereçavel(h):
    e = run(h, "Me mostre a tabela dim_employee")
    assert e.state.chamadas_efetivas == 0
    # nenhuma ferramenta do agente alem das seis do MCP
    assert set(plan_mod.MATRIZ[list(plan_mod.MATRIZ)[0]]) <= set(
        c.name for c in mcp_server.CAPACIDADES)
    usadas = {cap for caps in plan_mod.MATRIZ.values() for cap in caps}
    assert usadas <= {c.name for c in mcp_server.CAPACIDADES}


def test_17_repeticao_identica_para_o_loop(h):
    state = L.State(run_id="r", request_id="q", pergunta="p", actor_ref="a")
    args = {"kpi": "headcount", "period": {"grain": "mes", "from": "2026-06"}}
    state.chamadas.append(L.Chamada(1, "get_kpi", args, "ANSWER", "t1"))
    assert state.ja_chamou("get_kpi", dict(args)) is True
    assert state.ja_chamou("get_kpi", {**args, "kpi": "fte"}) is False


def test_18_loop_tem_limite_de_iteracoes(cfg):
    apertado = alim.Limites(max_iteracoes=1, max_chamadas_mcp=5)
    harness = Harness.start(cfg, limites=apertado)
    try:
        e = harness.run("Por que o turnover aumentou em 2025?", registrar=False)
    finally:
        harness.close()
    assert e.stop_reason in (L.LIMITE_ITERACOES, L.SUFICIENTE)
    if e.stop_reason == L.LIMITE_ITERACOES:
        assert e.resposta.parcial is True
        assert "parcial" in e.resposta.texto.lower()


def test_19_limite_de_chamadas(cfg):
    apertado = alim.Limites(max_chamadas_mcp=1)
    harness = Harness.start(cfg, limites=apertado)
    try:
        e = harness.run("Por que o turnover aumentou em 2025?", registrar=False)
    finally:
        harness.close()
    assert e.state.chamadas_efetivas <= 1
    assert e.stop_reason in (L.LIMITE_CHAMADAS, L.SUFICIENTE)


def test_20_timeout_configuravel(cfg):
    imediato = alim.Limites(timeout_s=0.0)
    harness = Harness.start(cfg, limites=imediato)
    try:
        e = harness.run("Qual foi o turnover em 2025?", registrar=False)
    finally:
        harness.close()
    assert e.stop_reason == L.TIMEOUT
    assert e.resposta.parcial is True
    assert e.state.chamadas_efetivas == 0


def test_21_mcp_error_nao_vira_valor_inventado(h):
    """Erro tecnico e relatado; nenhuma estimativa toma o lugar do numero."""
    envelope = menv.error("get_kpi", "r1", "t" * 16,
                          classe=menv.PARAMETRO_INVALIDO,
                          mensagem="campo desconhecido",
                          o_que_resolveria="corrigir a chamada").to_dict()
    r = render.falha_tecnica(envelope)
    assert r.stop_reason == L.FALHA_TECNICA
    assert "não vou estimar" in r.texto.lower()
    assert not r.numeros_citados


def test_22_ranking_com_maioria_suprimida(h):
    e = run(h, "Quais departamentos tiveram maior turnover em 2024?")
    assert e.stop_reason == L.SUFICIENTE
    d = e.state.observacoes[-1].envelope["data"]
    assert d["rows_suppressed"] == 19 and len(d["rows"]) == 26
    t = e.resposta.texto
    assert "19 de 26" in t
    assert "não é necessariamente o maior de todos" in t
    assert "37,99%" in t                      # formatado como taxa, do envelope


def test_23_nenhum_numero_sem_trace_id(h):
    """P-01: todo numero citado casa com um envelope observado."""
    for pergunta in ("Qual foi o turnover em 2025?",
                     "Compare o turnover de 2025 com o ano anterior.",
                     "Quais departamentos tiveram maior turnover em 2024?"):
        e = run(h, pergunta)
        assert e.resposta.trace_ids and all(e.resposta.trace_ids)
        observados = {o.trace_id for o in e.state.observacoes}
        assert set(e.resposta.trace_ids) <= observados
        # e cada numero citado existe em algum envelope
        for n in e.resposta.numeros_citados:
            assert any(_contem_numero(o.envelope, n) for o in e.state.observacoes)


def _contem_numero(envelope: dict, valor) -> bool:
    texto = json.dumps(envelope, default=str)
    return str(valor) in texto or str(round(float(valor), 6)) in texto


def test_24_plano_existe_antes_da_primeira_chamada(h):
    e = run(h, "Qual foi o turnover em 2025?")
    assert e.state.plano is not None
    d = e.state.plano.to_dict()
    assert d["steps"] and d["justificativa"]
    for s in d["steps"]:
        assert s["capacidade"] and s["motivo"] and s["objetivo"]
        assert "args" in s and "filters" not in s["args"]   # sem valor de filtro
    # a decisao de PLAN vem antes da primeira de ACT/INTERPRET
    passos = [dec.passo for dec in e.state.decisoes]
    assert passos.index("PLAN") < passos.index("INTERPRET")


def test_25_selecao_de_tool_segue_a_matriz(h):
    casos = {
        "Qual foi o turnover em 2025?": ["get_kpi"],
        "Compare o turnover de 2025 com o ano anterior.": ["compare_kpi"],
        "Quais departamentos tiveram maior turnover em 2024?": ["breakdown_kpi"],
        "O que significa turnover?": ["get_kpi_definition"],
        "Posso confiar no turnover de 2025?": ["get_trust"],
        "Por que o turnover aumentou em 2025?": ["compare_kpi", "breakdown_kpi"],
    }
    for pergunta, esperado in casos.items():
        e = run(h, pergunta)
        assert e.state.plano.capacidades == esperado, pergunta
        assert [c.tool for c in e.state.chamadas if not c.bloqueada][:len(esperado)] \
            == esperado[:e.state.chamadas_efetivas]


def test_26_compare_kpi_valido(h):
    e = run(h, "Compare o turnover de 2025 com o ano anterior.")
    d = e.state.observacoes[-1].envelope["data"]
    assert d["current"]["value"] == pytest.approx(0.204785, abs=1e-6)
    assert d["baseline"]["value"] == pytest.approx(0.253766, abs=1e-6)
    assert d["statement_kind"] == "ASSOCIACAO"
    assert "associação: não sustenta afirmação de causalidade" in e.resposta.texto


def test_27_fallback_a05_permitido(h):
    """A-05: dois `get_kpi` lado a lado, quando a comparacao e recusada."""
    intent = Intent(question_type="COMPARACAO", kpi_candidates=["turnover_rate"],
                    period={"grain": "ano", "from": "2025", "to": "2025"},
                    compare_to="periodo_anterior")
    passos = plan_mod.fallback_a05(intent, h.contexto, passo=2)
    assert len(passos) == 2
    assert all(s.capacidade == "get_kpi" for s in passos)
    assert all(s.origem == "FALLBACK_A05" for s in passos)
    assert [s.args["period"]["from"] for s in passos] == ["2025", "2024"]
    assert "sem cálculo de diferença" in passos[0].motivo


def test_28_fallback_a05_nao_calcula(h):
    """O proibido: delta, percentual, tendencia. So os dois valores."""
    envs = []
    for ano in ("2025", "2024"):
        e = h.servidor.call("get_kpi", {"kpi": "turnover_rate",
                                        "period": {"grain": "ano", "from": ano}},
                            registrar=False)
        envs.append(e.to_dict())
    r = render.resposta_lado_a_lado(envs)
    assert "20,48%" in r.texto and "25,38%" in r.texto
    assert "independentes" in r.texto
    assert "comparação formal não foi disponibilizada" in r.texto
    for proibido in ("caiu", "subiu", "p.p.", "-19", "4,90", "variação"):
        assert proibido not in r.texto, proibido
    # e nenhum numero citado alem dos dois que vieram dos envelopes
    assert sorted(r.numeros_citados) == sorted(
        [e["data"]["value"] for e in envs])


def test_29_log_com_sanitizacao_de_pii(h_tmp, cfg_tmp):
    """A-04: a pergunta e registrada depois de sanitizada."""
    e = h_tmp.run("Qual foi o turnover da equipe da Ana Ribeiro em 2025? "
                  "meu email e ana.ribeiro@novaora.com, tel 11 98765-4321")
    linha = aobs.ler(cfg_tmp, e.state.run_id)
    assert linha is not None
    reg = linha["pergunta_sanitizada"]
    assert linha["pergunta_redigida"] == 1
    assert "Ana Ribeiro" not in reg and "[NOME]" in reg
    assert "ana.ribeiro@novaora.com" not in reg and "[EMAIL]" in reg
    assert "98765-4321" not in reg
    # o que e governado sobrevive
    assert "turnover" in reg and "2025" in reg
    # rastreabilidade intacta
    assert linha["run_id"] == e.state.run_id and linha["stop_reason"]
    assert linha["trace_ids"]
    # nenhuma coluna proibida
    colunas = {l.strip().split()[0] for l in aobs.DDL.splitlines()
               if l.strip() and l.strip()[0].islower()}
    for proibido in aobs.NUNCA_REGISTRADO:
        assert proibido not in colunas


def test_30_sem_memoria_persistente(h):
    """O estado morre com a execucao."""
    a = run(h, "Qual foi o turnover em 2025?")
    b = run(h, "Qual foi o turnover em 2025?")
    assert a.state.run_id != b.state.run_id
    assert a.state is not b.state
    assert not hasattr(h, "memoria") and not hasattr(h, "cache")
    # e o modulo nao guarda nada entre execucoes
    fonte = (ROOT / "src" / "agent" / "harness.py").read_text(encoding="utf-8")
    for proibido in ("cache", "memoria_longo_prazo", "persist"):
        assert proibido not in fonte.lower(), proibido


# ========================================================================== #
# A-01..A-05, verificacoes diretas
# ========================================================================== #
def test_a01_ambiguidade_nunca_gera_chamada_de_valor(h):
    ambiguas = [
        "Qual foi o turnover de Tecnologia no Q2 de 2026?",
        "Qual foi o headcount de Jurídico em 2025?",
        "Qual foi o turnover no Q2 de 2025?",
        "Qual foi o índice de engajamento em 2025?",
    ]
    for p in ambiguas:
        e = run(h, p)
        assert e.stop_reason == L.AMBIGUIDADE, p
        assert e.state.chamadas_efetivas == 0, p
        assert e.resposta.pergunta_de_volta, p


def test_a02_vocabulario_no_contexto_sem_setima_capacidade(h):
    assert len(h.contexto.vocabulario["departamento"]) == 27
    assert "Engineering" in h.contexto.vocabulario["departamento"]
    assert h.contexto.termo_valido("pais", "Brasil")
    assert h.contexto.termo_valido("pais", "brazil")
    # membro reservado NAO e termo consultavel
    assert not h.contexto.termo_valido("departamento", "UNMAPPED")
    assert not h.contexto.termo_valido("nivel", "DECISAO_PENDENTE")
    # sem fuzzy matching
    assert not h.contexto.termo_valido("pais", "Brasilia")
    assert not h.contexto.termo_valido("departamento", "Engineer")
    # e o MCP continua com seis capacidades
    assert len(mcp_server.CAPACIDADES) == 6


def test_a03_guarda_vive_no_harness_e_nao_no_prompt():
    fonte = (ROOT / "src" / "agent" / "privacy_guard.py").read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    funcoes = {n.name for n in ast.walk(arvore)
               if isinstance(n, ast.FunctionDef)}
    assert "permite" in funcoes and "registrar_supressao" in funcoes
    # o harness chama a guarda ANTES de chamar o servidor
    hsrc = (ROOT / "src" / "agent" / "harness.py").read_text(encoding="utf-8")
    assert hsrc.index("guarda.permite(") < hsrc.index("self.servidor.call(")


def test_a04_redacao_usa_o_vocabulario_como_allowlist(h):
    allow = h.contexto.todos_os_termos()
    seguro = "turnover de Customer Service no Brasil em 2025"
    assert redaction.redigir(seguro, allow) == seguro
    perigoso = "turnover da Maria Fernanda Souza"
    assert "[NOME]" in redaction.redigir(perigoso, allow)
    assert "Maria" not in redaction.redigir(perigoso, allow)
    assert redaction.redigir("cpf 123.456.789-00", allow).count("[DOCUMENTO]") == 1
    assert "[EMAIL]" in redaction.redigir("fale com x@y.com", allow)
    assert not redaction.contem_pii(seguro, allow)


def test_a05_registra_que_sao_valores_independentes(h):
    intent = Intent(question_type="COMPARACAO", kpi_candidates=["turnover_rate"],
                    period={"grain": "ano", "from": "2025", "to": "2025"})
    passos = plan_mod.fallback_a05(intent, h.contexto, passo=2)
    d = [s.to_dict() for s in passos]
    assert all(s["origem"] == "FALLBACK_A05" for s in d)
    assert all("independente" in s["motivo"] for s in d)


# ========================================================================== #
# Cenários da demonstração
# ========================================================================== #
def test_cenarios_da_demo(h):
    c1 = run(h, "Qual foi o turnover de Tecnologia no Q2 de 2026?")
    assert c1.stop_reason == L.AMBIGUIDADE and c1.state.chamadas_efetivas == 0

    c2 = run(h, "Compare o turnover de 2025 com o ano anterior.")
    assert c2.state.plano.capacidades == ["compare_kpi"]

    c3 = run(h, "Quais departamentos tiveram maior turnover em 2024?")
    assert c3.state.plano.capacidades == ["breakdown_kpi"]
    assert "19 de 26" in c3.resposta.texto

    c4 = run(h, "Por que o turnover aumentou em 2025?")
    assert "caiu, não subiu" in c4.resposta.texto
    assert c4.resposta.level == "CONTEXT"

    c5 = run(h, "A política de trabalho remoto causou a queda do turnover em 2025?")
    assert "não posso afirmar" in c5.resposta.texto

    c6 = run(h, "Qual foi a taxa de promoção em 2025?")
    assert c6.state.chamadas[0].refusal_class == "KPI_BLOQUEADO"

    c8 = run(h, "O que significa turnover?")
    assert c8.state.plano.capacidades == ["get_kpi_definition"]
    assert "Desligamentos" in c8.resposta.texto


def test_cenario_9_lineage_usa_o_trace_anterior(h_tmp):
    anterior = h_tmp.run("Qual foi o turnover em 2025?")
    e = h_tmp.run("De onde veio esse número?",
                  trace_anterior=anterior.resposta.trace_ids[0])
    assert e.stop_reason == L.SUFICIENTE
    assert e.state.plano.capacidades == ["get_lineage"]
    assert "turnover_rate" in e.resposta.texto
    assert "camada analítica governada" in e.resposta.texto
    assert "não percorre" in e.resposta.texto


# ========================================================================== #
# Invariantes estruturais
# ========================================================================== #
def test_toda_execucao_termina_com_stop_reason(h):
    perguntas = [
        "Qual foi o turnover em 2025?",
        "Qual foi o turnover de Tecnologia no Q2 de 2026?",
        "Qual foi a taxa de promoção em 2025?",
        "O que significa turnover?",
        "Posso confiar no turnover de 2025?",
        "Quais departamentos tiveram maior turnover em 2024?",
        "Por que o turnover aumentou em 2025?",
        "blablabla",
    ]
    vistos = set()
    for p in perguntas:
        e = run(h, p)
        assert e.stop_reason in L.STOP_REASONS, p
        assert e.resposta.texto
        vistos.add(e.stop_reason)
    assert {L.SUFICIENTE, L.AMBIGUIDADE, L.RECUSA_GOVERNADA} <= vistos


def test_o_agente_nao_calcula_nem_faz_aritmetica():
    """Nenhuma conta entre resultados, verificada na arvore sintatica."""
    for nome in ("render.py", "harness.py", "plan.py"):
        fonte = (ROOT / "src" / "agent" / nome).read_text(encoding="utf-8")
        arvore = ast.parse(fonte)
        for no in ast.walk(arvore):
            if isinstance(no, ast.BinOp) and isinstance(
                    no.op, (ast.Sub, ast.Div, ast.Mult)):
                trecho = ast.unparse(no)
                permitido = (
                    "100" in trecho              # formatacao de percentual
                    or "perf_counter" in trecho  # medicao de duracao
                    or "len(" in trecho          # contagem de itens de lista
                    or "int(" in trecho          # aritmetica de calendario
                    or trecho.endswith(("ano - 1", "mes - 1", "tri - 1")))
                assert permitido, f"{nome}: aritmetica suspeita -> {trecho}"


def test_o_agente_so_alcanca_o_mcp():
    """Nenhum modulo do agente importa dado, banco ou camada analitica."""
    for p in (ROOT / "src" / "agent").glob("*.py"):
        fonte = p.read_text(encoding="utf-8")
        for proibido in ("import duckdb", "read_parquet", "import polars",
                         "from analytics.semantic import ask",
                         "from analytics.semantic import executor",
                         "analytical", "fact_", "dim_"):
            assert proibido not in fonte, (p.name, proibido)
    # a unica porta para dado quantitativo e o servidor MCP
    hsrc = (ROOT / "src" / "agent" / "harness.py").read_text(encoding="utf-8")
    assert "self.servidor.call(" in hsrc
    assert hsrc.count("self.servidor.call(") == 1


def test_reprodutibilidade_do_plano(h):
    """AA-11: o que reproduz e o plano e a sequencia, nao a prosa."""
    a = run(h, "Quais departamentos tiveram maior turnover em 2024?")
    b = run(h, "Quais departamentos tiveram maior turnover em 2024?")
    assert a.state.plano.to_dict() == b.state.plano.to_dict()
    assert [c.tool for c in a.state.chamadas] == [c.tool for c in b.state.chamadas]
    assert a.resposta.texto == b.resposta.texto
    assert a.state.run_id != b.state.run_id


def test_nenhuma_resposta_com_verbo_causal_abaixo_de_causality(h):
    for p in ("Compare o turnover de 2025 com o ano anterior.",
              "Quais departamentos tiveram maior turnover em 2024?",
              "Qual foi o turnover em 2025?"):
        e = run(h, p)
        violacoes = render.verificar_redacao(e.resposta)
        assert violacoes == [], (p, violacoes)


def test_limites_configuraveis_estao_declarados():
    d = alim.PADRAO.to_dict()
    assert d["max_iteracoes"] == 6
    assert d["max_chamadas_mcp"] == 5
    assert d["timeout_s"] == 60.0
    assert d["max_repeticao_identica"] == 0
    assert d["max_consultas_vizinhas"] == 2
    assert d["max_palavras_resposta"] == 400
    # e sao de fato configuraveis
    custom = alim.Limites(max_iteracoes=2)
    assert custom.max_iteracoes == 2 and custom.max_chamadas_mcp == 5


def test_teto_do_ator_restringe_mas_nao_eleva(cfg):
    restrito = mcp_actor.Actor(id="a", type="human", max_response_level="FACT")
    harness = Harness.start(cfg, actor=restrito)
    try:
        e = harness.run("Compare o turnover de 2025 com o ano anterior.",
                        actor=restrito, registrar=False)
    finally:
        harness.close()
    assert e.stop_reason == L.RECUSA_GOVERNADA
    envelope = e.state.observacoes[-1].envelope
    assert envelope["response_level"]["ceiling_from"] == menv.CEILING_ATOR


# ========================================================================== #
# Dimensao inferida: uma dimensao so entra no Intent se foi dita (EV-11)
# ========================================================================== #
def _filtros(h, pergunta) -> dict[str, str]:
    """Filtros do UNDERSTAND, como dicionario dimensao -> termo."""
    intent = RuleInterpreter().understand(pergunta, h.contexto)
    return {f["dimension"]: f["terms"][0] for f in intent.filters}


def test_ev11_dimensao_nao_dita_nao_entra(h):
    """`Customer Service` e departamento; `Customer` nao foi dito.

    O numero coincidiria — Customer Service pertence a BU Customer — mas a
    coincidencia e do dado, e nao da pergunta.
    """
    f = _filtros(h, "Qual foi o turnover de Customer Service em 2025?")
    assert f == {"departamento": "Customer Service"}
    assert "business_unit" not in f


def test_ev11_dimensao_dita_sozinha_entra(h):
    f = _filtros(h, "Qual foi o turnover da Business Unit Customer em 2025?")
    assert f == {"business_unit": "Customer"}


def test_ev11_as_duas_ditas_entram_as_duas(h):
    f = _filtros(h, "Qual foi o turnover de Customer Service "
                    "na Business Unit Customer em 2025?")
    assert f == {"departamento": "Customer Service", "business_unit": "Customer"}


def test_ev11_a_regra_e_geral_e_nao_um_caso(h):
    """Mesma forma, outro par do vocabulario: nada aqui e `Customer`."""
    f = _filtros(h, "Qual foi o turnover de Digital Marketing em 2025?")
    assert f == {"departamento": "Digital Marketing"}

    f = _filtros(h, "Qual foi o turnover de Marketplace Operations em 2025?")
    assert f == {"departamento": "Marketplace Operations"}

    # e vale dentro de uma mesma dimensao: `Data` cabe em `Data & Analytics`
    f = _filtros(h, "Qual foi o turnover de Data & Analytics em 2025?")
    assert f == {"departamento": "Data & Analytics"}

    # o termo curto continua valendo quando e ele que foi dito
    f = _filtros(h, "Qual foi o turnover da Business Unit Digital em 2025?")
    assert f == {"business_unit": "Digital"}


def test_ev11_extracao_correta_permanece(h):
    """Sem regressao: o que ja saia certo continua saindo certo."""
    assert _filtros(h, "Qual foi o turnover no Brasil em 2025?") == {"pais": "Brasil"}
    # o sinonimo do KPI continua consumido antes dos filtros
    assert _filtros(h, "Quantas mulheres em lideranca em 2025?") == {}
    # termo fora do vocabulario continua chegando ao RESOLVE
    assert _filtros(h, "Qual foi o turnover de Tecnologia no Q2 de 2026?") == \
        {"departamento": "Tecnologia"}
    # sem recorte nenhum, nenhum filtro
    assert _filtros(h, "Qual foi o turnover em 2025?") == {}
