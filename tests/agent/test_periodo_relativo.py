"""Periodo relativo no RESOLVE (P-02, D-L1).

    "Termo relativo resolve contra a cobertura do KPI, nunca contra o relogio."

A referencia temporal existe e e governada: `config/semantic/vocabulary.yaml`
declara `relative_terms`, e cada um resolve para `coverage_end` num grain fixo.
Nenhum teste aqui depende da data de hoje, e nenhum passaria a falhar amanha.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agent import llm_eval
from agent.harness import Harness
from agent.intent import VALOR, Intent, resolve
from agent.interpreter import RuleInterpreter
from generator import config

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def cfg():
    return config.load(ROOT)


@pytest.fixture(scope="module")
def h(cfg):
    harness = Harness.start(cfg)
    yield harness
    harness.close()


@pytest.fixture(scope="module")
def contexto(h):
    return h.contexto


def intent_relativo(kpi: str, termo: str, grain: str = "ano") -> Intent:
    """Intencao como o interpretador a entrega: termo marcado, nao resolvido."""
    return Intent(question_type=VALOR, kpi_candidates=[kpi],
                  period={"grain": grain, "relativo": termo})


def ambiguidades_de_periodo(intent) -> list:
    """`period` e `period.grain`, que e como o RESOLVE ja nomeava os dois."""
    return [a for a in intent.ambiguity if a.campo.startswith("period")]


# ========================================================================== #
# 1 — identificavel, mas sem referencia temporal suficiente
# ========================================================================== #
def test_01_sem_referencia_suficiente_vira_ambiguidade(contexto):
    """`headcount` vai ate 2026-06: nao existe "ultimo ano" inequivoco.

    2026 esta pela metade. Responder 2026 entregaria meio ano apresentado como
    ano inteiro, que e exatamente a conversao silenciosa que a decisao proibe.
    """
    r = resolve(intent_relativo("headcount", "ultimo ano"), contexto)
    assert ambiguidades_de_periodo(r)
    assert "2026-06" in ambiguidades_de_periodo(r)[0].motivo
    # e o periodo NAO foi materializado
    assert not (r.period or {}).get("from")


def test_01b_termo_nao_declarado_vira_ambiguidade(contexto):
    """"trimestre passado" nao esta no vocabulario, e nao vira o mais parecido."""
    for termo in ("trimestre passado", "ano passado", "ultimos 6 meses",
                  "semestre passado"):
        r = resolve(intent_relativo("turnover_rate", termo), contexto)
        amb = ambiguidades_de_periodo(r)
        assert amb, termo
        assert "não existe termo relativo declarado" in amb[0].motivo
        assert not (r.period or {}).get("from"), termo


# ========================================================================== #
# 2 — referencia explicita e regra deterministica
# ========================================================================== #
def test_02_resolucao_correta_contra_a_cobertura(contexto):
    casos = [
        ("turnover_rate", "ultimo ano", "ano", "2026"),
        ("turnover_rate", "último ano", "ano", "2026"),     # acento, mesmo termo
        ("headcount", "ultimo mes", "mes", "2026-06"),
        ("time_to_fill", "ultimo trimestre", "trimestre", "2026-Q2"),
    ]
    for kpi, termo, grain, esperado in casos:
        r = resolve(intent_relativo(kpi, termo, grain), contexto)
        assert not r.ambiguity, (kpi, termo, [a.motivo for a in r.ambiguity])
        assert r.period == {"grain": grain, "from": esperado, "to": esperado}, \
            (kpi, termo)


def test_02b_o_valor_vem_da_cobertura_declarada_e_nao_do_relogio(contexto):
    """O periodo materializado e, por construcao, o fim da cobertura."""
    r = resolve(intent_relativo("headcount", "ultimo mes", "mes"), contexto)
    cobertura = contexto.catalogo["headcount"]["period_coverage"]
    assert r.period["from"] == str(cobertura["to"])


# ========================================================================== #
# 3 — fora da cobertura, ou grain que o KPI nao responde
# ========================================================================== #
def test_03_grain_que_o_kpi_nao_responde_vira_ambiguidade(contexto):
    """`turnover_rate` e anual: "ultimo trimestre" nao tem versao trimestral."""
    r = resolve(intent_relativo("turnover_rate", "ultimo trimestre", "trimestre"),
                contexto)
    amb = ambiguidades_de_periodo(r)
    assert amb
    assert "não existe versão por trimestre" in amb[0].motivo
    assert not (r.period or {}).get("from")


def test_03b_a_ambiguidade_oferece_periodos_validos(contexto):
    r = resolve(intent_relativo("turnover_rate", "ultimos 6 meses"), contexto)
    amb = ambiguidades_de_periodo(r)[0]
    assert amb.opcoes == contexto.periodos_sugeridos("turnover_rate")
    assert amb.opcoes                                  # e nao uma lista vazia


# ========================================================================== #
# 4 e 5 — o que nunca pode acontecer
# ========================================================================== #
def test_04_ultimo_trimestre_nunca_vira_serie_inteira(contexto):
    """Resolvido vira um trimestre unico; nao resolvido vira ambiguidade."""
    for kpi in sorted(contexto.catalogo):
        r = resolve(intent_relativo(kpi, "ultimo trimestre", "trimestre"), contexto)
        p = r.period or {}
        if ambiguidades_de_periodo(r):
            assert not p.get("from"), kpi          # nada foi materializado
            continue
        assert p.get("from") and p.get("from") == p.get("to"), kpi
        assert p["grain"] == "trimestre", kpi
        # um trimestre, e nao um intervalo que cubra a serie
        assert p["from"] != str(
            (contexto.catalogo[kpi].get("period_coverage") or {}).get("from")), kpi


def test_05_ano_passado_nunca_vira_periodo_arbitrario(contexto):
    """Termo nao declarado nao materializa periodo nenhum, em nenhum KPI."""
    for kpi in sorted(contexto.catalogo):
        r = resolve(intent_relativo(kpi, "ano passado"), contexto)
        assert not (r.period or {}).get("from"), kpi
        assert r.ambiguity, kpi


# ========================================================================== #
# 6 — equivalente em ingles
# ========================================================================== #
def test_06_ingles_sem_sinonimo_declarado_vira_ambiguidade(contexto):
    """ADR-0020: sugestao nao atravessa fronteira de lingua.

    "last quarter" nao e sinonimo declarado de `ultimo_trimestre`. O contrato
    atual nao permite resolve-lo, entao o comportamento correto e ambiguidade,
    e nao uma traducao por semelhanca. O dia em que houver sinonimo declarado
    em EN-US, estes termos passam a resolver sem mudar uma linha de codigo.
    """
    doc = yaml.safe_load(
        (ROOT / "config" / "semantic" / "vocabulary.yaml").read_text(encoding="utf-8"))
    declarados = set((doc["periods"].get("relative_terms") or {}))
    assert not any(t.startswith("last_") for t in declarados)

    for termo in ("last quarter", "last year", "last month", "previous year"):
        r = resolve(intent_relativo("turnover_rate", termo), contexto)
        assert ambiguidades_de_periodo(r), termo
        assert not (r.period or {}).get("from"), termo


def test_06b_o_termo_declarado_resolve_igual_em_qualquer_grafia(contexto):
    """Igualdade normalizada: acento e underscore nao mudam o significado."""
    esperado = {"grain": "ano", "from": "2026", "to": "2026"}
    for termo in ("ultimo ano", "último ano", "ultimo_ano", "Último Ano"):
        r = resolve(intent_relativo("turnover_rate", termo), contexto)
        assert r.period == esperado, termo


# ========================================================================== #
# 7 — nenhuma resolucao sai da cobertura
# ========================================================================== #
def test_07_nenhuma_resolucao_introduz_periodo_fora_da_cobertura(contexto):
    """Varredura: todo termo declarado, contra todo KPI do catalogo."""
    doc = yaml.safe_load(
        (ROOT / "config" / "semantic" / "vocabulary.yaml").read_text(encoding="utf-8"))
    declarados = (doc["periods"].get("relative_terms") or {})
    assert declarados

    resolvidos = 0
    for kpi in sorted(contexto.catalogo):
        for termo, spec in declarados.items():
            r = resolve(intent_relativo(kpi, termo, spec["grain"]), contexto)
            if ambiguidades_de_periodo(r):
                continue
            resolvidos += 1
            assert contexto.fora_da_cobertura(kpi, r.period) is None, (kpi, termo)
            assert r.period["from"] == str(
                contexto.catalogo[kpi]["period_coverage"]["to"]), (kpi, termo)
    assert resolvidos, "nenhum caso resolveu: a varredura nao provou nada"


# ========================================================================== #
# 8, 9 e 10 — o que nao pode ter mudado
# ========================================================================== #
def test_08_periodo_absoluto_continua_igual(contexto):
    bom = Intent(question_type=VALOR, kpi_candidates=["turnover_rate"],
                 period={"grain": "ano", "from": "2025", "to": "2025"})
    r = resolve(bom, contexto)
    assert not r.ambiguity
    assert r.period == {"grain": "ano", "from": "2025", "to": "2025"}

    fora = Intent(question_type=VALOR, kpi_candidates=["turnover_rate"],
                  period={"grain": "ano", "from": "2011", "to": "2011"})
    assert ambiguidades_de_periodo(resolve(fora, contexto))

    grain_errado = Intent(question_type=VALOR, kpi_candidates=["turnover_rate"],
                          period={"grain": "trimestre", "from": "2026-Q2"})
    assert ambiguidades_de_periodo(resolve(grain_errado, contexto))


def test_09_pergunta_sem_periodo_continua_igual(contexto):
    sem = Intent(question_type=VALOR, kpi_candidates=["turnover_rate"])
    r = resolve(sem, contexto)
    amb = ambiguidades_de_periodo(r)
    assert amb and "não diz de que período" in amb[0].motivo
    # uma ambiguidade de periodo, e nao duas
    assert len(amb) == 1


def test_09b_pergunta_nao_quantitativa_sem_periodo_nao_exige_periodo(contexto):
    from agent.intent import DEFINICAO
    r = resolve(Intent(question_type=DEFINICAO,
                       kpi_candidates=["turnover_rate"]), contexto)
    assert not ambiguidades_de_periodo(r)


def test_10_casos_a_m_nao_mudaram(contexto):
    """A linha de base medida antes de D-L1 continua exatamente igual."""
    resultados = llm_eval.avaliar(RuleInterpreter(), contexto)
    resumo = llm_eval.resumo(resultados)
    assert resumo["por_resultado"] == {"PASSOU": 13, "FALHOU": 4}
    assert resumo["falharam"] == ["G", "D-EN", "E-EN", "F-EN"]


def test_10b_o_rule_interpreter_nao_produz_periodo_relativo(contexto):
    """Ele nao foi alterado, e continua sem marcar termo relativo."""
    intent = RuleInterpreter().understand(
        "Qual foi o turnover no ultimo ano?", contexto)
    assert not (intent.period or {}).get("relativo")
