"""As seis capacidades governadas (MCP SPEC v0.1, Parte V).

Nenhuma delas calcula. Cada uma traduz a entrada tipada para o que a Semantic
Layer já sabe fazer, chama `analytics.semantic.ask`, e **preserva integralmente**
o que volta: valor, unidade, trust, teto de nível, supressão por privacidade e
estados governados.

Preservar é a palavra operante. Uma linha suprimida não é reconstruída, inferida,
substituída nem removida. `UNMAPPED` não vira `null` nem "não informado".
`BLOCKED` não vira `LIMITED`. O MCP não tem por onde fazer isso: não monta SQL,
não conhece nome de tabela e não recalcula medida.

    entrada tipada  ->  SemanticQuery  ->  ask()  ->  Answer  ->  Envelope
                        (F7 valida)      (F7 calcula)   (aqui só adapta)
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from analytics.semantic import ask as semantic_ask
from analytics.semantic import catalog as semcat
from analytics.semantic import certify, plans, trace as semtrace
from analytics.semantic.catalog import ORDEM_NIVEL
from analytics.semantic.query import QueryShapeError, validate

from . import actor as act
from . import envelope as env
from . import limits

# Campos do contrato que NUNCA saem em `get_kpi_definition`. O agente não precisa
# deles para explicar um número, e expô-los daria a ele nomes físicos para
# tentar usar.
NAO_EXPOSTO_NA_DEFINICAO = ("source_tables", "depends_on_checks")

MEDIDAS_SOMAVEIS = ("contagem_distinta", "soma")


@dataclass
class Contexto:
    """O que uma chamada precisa: motor da F7, ator e identificadores."""
    engine: semantic_ask.Engine
    actor: act.Actor
    request_id: str


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _filtro_em_negocio(f: dict) -> str:
    """O `porque` do contrato, que e a versao em linguagem de negocio.

    O campo `regra` e escrito em termos fisicos (`is_system_of_record = true`) e
    nao atravessa a fronteira: expo-lo daria ao agente um nome de coluna para
    tentar usar, e a Semantic Layer existe para que ele nao precise conhecer
    nenhum.
    """
    return f.get("porque") or "filtro fixo declarado no contrato do KPI"


def _bloco_kpi(kpi) -> dict | None:
    if kpi is None:
        return None
    return {"id": kpi.kpi_id, "version": kpi.version, "status": kpi.status,
            "owner": kpi.owner}


def _nivel(pedido: str, ans, ator: act.Actor, kpi) -> dict:
    """O bloco `response_level`, com a origem do teto.

    O nível concedido vem da F7. O MCP nunca o eleva: ele já pediu à F7 o
    mínimo entre o pedido e o teto do ator, e a F7 aplicou os dela por cima.
    """
    concedido = ans.level
    trust_status = (ans.trust or {}).get("status")
    return {"requested": pedido,
            "granted": concedido,
            "ceiling_from": act.origem_do_teto(
                pedido, concedido, ator.max_response_level, trust_status,
                kpi.status if kpi else None)}


def _do_answer(tool: str, ctx: Contexto, ans, pedido: str, kpi,
               data: dict, extra_limits: dict | None = None) -> env.Envelope:
    return env.answer(tool, ctx.request_id, ans.trace_id, data=data,
                      kpi=_bloco_kpi(kpi), trust=ans.trust,
                      response_level=_nivel(pedido, ans, ctx.actor, kpi),
                      limits=limits.aplicados(**(extra_limits or {})),
                      caveats=list(ans.caveats))


def _da_recusa(tool: str, ctx: Contexto, ans, kpi, pedido: str) -> env.Envelope:
    """Recusa da Semantic Layer, transportada sem tradução (ADR-0032).

    A classe, a mensagem e o `o_que_resolveria` atravessam verbatim. Traduzir
    criaria um segundo vocabulário para o mesmo conceito.
    """
    r = ans.refusal
    return env.refusal(tool, ctx.request_id, ans.trace_id,
                       classe=r["classe"], mensagem=r["mensagem"],
                       o_que_resolveria=r["o_que_resolveria"],
                       detalhe=r.get("detalhe") or {},
                       kpi=_bloco_kpi(kpi), trust=ans.trust,
                       response_level={"requested": pedido, "granted": None,
                                       "ceiling_from": env.CEILING_GOVERNANCA
                                       if r["classe"] == "KPI_BLOQUEADO"
                                       else env.CEILING_EVIDENCIA},
                       limits=limits.aplicados())


def _da_supressao(tool: str, ctx: Contexto, ans, kpi) -> env.Envelope:
    """Supressão por privacidade, preservada como categoria própria.

    Não vira recusa e não vira erro. Um agente que lê "erro" tenta outro
    recorte, e é assim que se reidentifica alguém por tentativa.
    """
    return env.suppressed(tool, ctx.request_id, ans.trace_id,
                          detalhe=ans.suppressed, kpi=_bloco_kpi(kpi),
                          trust=ans.trust, limits=limits.aplicados(),
                          caveats=list(ans.caveats))


def _erro_de_periodo(tool: str, ctx: Contexto, grain: str, ini: str,
                     fim: str) -> env.Envelope | None:
    n = limits.excede_periodos(grain, ini, fim)
    if n is None:
        return None
    return env.refusal(
        tool, ctx.request_id, semtrace.novo_trace_id(),
        classe=env.LIMITE_DE_RESULTADO_EXCEDIDO,
        mensagem=f"a janela pedida cobre {n} periodos, e o limite por chamada e "
                 f"{limits.MAX_PERIODOS}.",
        o_que_resolveria=f"estreitar a janela para no maximo "
                         f"{limits.MAX_PERIODOS} periodos",
        detalhe={"periodos_pedidos": n, "limite": limits.MAX_PERIODOS},
        limits=limits.aplicados())


def _consulta(kpi: str, period: dict, filters, nivel: str,
              dimensions=None, compare=None, compare_period=None,
              kpi_version=None) -> dict:
    """Monta o dicionário que a F7 vai validar.

    Só campos que o `SemanticQuery` conhece. Se o chamador mandou algo a mais,
    já foi barrado pelo schema da tool antes de chegar aqui — e, se escapasse,
    seria barrado de novo pelo `parse`, que reprova campo desconhecido.
    """
    c = {"kpi": kpi, "period": period, "requested_level": nivel}
    if filters:
        c["filters"] = filters
    if dimensions:
        c["dimensions"] = dimensions
    if compare:
        c["compare"] = compare
    if compare_period:
        c["compare_period"] = compare_period
    if kpi_version:
        c["kpi_version"] = kpi_version
    return c


def _executa(tool: str, ctx: Contexto, consulta: dict, pedido: str):
    """Chama a Semantic Layer e devolve (envelope, answer, kpi, duracao_ms)."""
    t0 = time.perf_counter()
    try:
        ans = semantic_ask.ask(ctx.engine, consulta)
    except QueryShapeError as e:
        # A F7 rejeitou a forma. É defeito do chamador, e por isso é ERROR.
        dur = int((time.perf_counter() - t0) * 1000)
        return (env.error(tool, ctx.request_id, semtrace.novo_trace_id(),
                          classe=env.PARAMETRO_INVALIDO, mensagem=str(e),
                          o_que_resolveria="enviar uma consulta semantica valida; "
                                           "a fronteira nao aceita SQL, nome de "
                                           "tabela, coluna ou junção (ADR-0028)"),
                None, None, dur)
    dur = int((time.perf_counter() - t0) * 1000)
    kpi = ctx.engine.catalog.get(consulta["kpi"])
    if ans.refusal:
        return _da_recusa(tool, ctx, ans, kpi, pedido), ans, kpi, dur
    if ans.suppressed:
        return _da_supressao(tool, ctx, ans, kpi), ans, kpi, dur
    return None, ans, kpi, dur


# --------------------------------------------------------------------------- #
# 1. get_kpi
# --------------------------------------------------------------------------- #
def get_kpi(ctx: Contexto, *, kpi: str, period: dict, filters=None,
            requested_level: str = "FACT", kpi_version: str | None = None):
    """Um valor, de um KPI, num período, sem quebra por dimensão."""
    pedido = requested_level
    erro = _erro_de_periodo("get_kpi", ctx, period.get("grain"),
                            str(period.get("from")),
                            str(period.get("to") or period.get("from")))
    if erro:
        return erro, None, 0

    nivel_para_f7 = act.teto_composto(pedido, ctx.actor.max_response_level)
    envelope, ans, kpi_obj, dur = _executa(
        "get_kpi", ctx, _consulta(kpi, period, filters, nivel_para_f7,
                                  kpi_version=kpi_version), pedido)
    if envelope is not None:
        return envelope, ans, dur

    plano = plans.plano(kpi_obj.kpi_id)
    data = {
        "value": ans.value,
        "unit": ans.unit,
        "period": ans.scope.get("period"),
        "population": (ans.coverage or {}).get("population"),
        "filters_applied": {
            # O filtro fixo aparece pelo QUE ELE PROTEGE, nunca pela expressao
            # tecnica: o agente precisa saber que ele existe sem precisar saber
            # como a coluna se chama (SPEC Parte V).
            "declared_by_contract": [_filtro_em_negocio(f)
                                     for f in kpi_obj.doc.get("filters") or []],
            "requested_by_caller": ans.scope.get("filters") or [],
        },
        "exclusions": [e.get("o_que") for e in kpi_obj.doc.get("exclusions") or []],
        "coverage": ans.coverage,
    }
    # Desvio D-1, autorizado. A SPEC permite `to` diferente de `from` (ate 24
    # periodos) e o schema de saida so nomeia `value` escalar. A serie sai em
    # campo proprio e **nao altera nada**: um periodo continua respondendo com
    # `value` escalar, e nenhum valor e recalculado aqui — cada item e a linha
    # que a Semantic Layer devolveu, com os metadados governados dela.
    if len(ans.rows) > 1:
        col = plans.PERIODO_COLS[period["grain"]]
        data["series"] = [{
            "period": l.get(col),
            "value": l.get("valor"),
            "population": l.get("populacao"),
            # metadados governados do item: a supressao por privacidade vale por
            # linha, e um periodo pequeno demais nao responde so porque a serie
            # inteira responde.
            "suppressed": bool(l.get("suprimido")),
            "suppression_reason": l.get("motivo_supressao"),
        } for l in ans.rows]
        data["series_meta"] = {
            "periods": len(ans.rows),
            "grain": period["grain"],
            "unit": ans.unit,
            # Trust e teto valem para a serie inteira: sao do KPI e do recorte,
            # e nao de cada ponto. Ficam no envelope, e aqui so se declara isso.
            "trust_escopo": "a serie inteira; ver `trust` no envelope",
            "suppressed_periods": sum(1 for l in ans.rows if l.get("suprimido")),
        }
    return _do_answer("get_kpi", ctx, ans, pedido, kpi_obj, data), ans, dur


# --------------------------------------------------------------------------- #
# 2. compare_kpi
# --------------------------------------------------------------------------- #
def compare_kpi(ctx: Contexto, *, kpi: str, period: dict, compare_to: str,
                compare_period: dict | None = None,
                filters=None, kpi_version: str | None = None):
    """O mesmo KPI, no mesmo recorte, em duas janelas.

    O nível é CONTEXT por definição: pedir FACT aqui é `get_kpi`. A comparação
    é feita pela Semantic Layer, que exige que a base seja ela própria
    respondível — comparar com um número que não existe é pior do que não
    comparar.

    Duas famílias de base, e a diferença é de onde vem o período:

    - **relativa** (`periodo_anterior`, `mesmo_periodo_ano_anterior`,
      `media_da_populacao`): a Semantic Layer **deriva** o período da base a
      partir do período pedido;
    - **declarada** (`periodo_declarado`): a pergunta nomeou os dois períodos,
      e o segundo chega em `compare_period`. Sem ele a comparação é recusada,
      e **não** cai para uma base relativa parecida (RF-02).
    """
    pedido = "CONTEXT"
    # Se foi o teto do ATOR que impediu CONTEXT, a recusa diz isso e nao culpa a
    # base de comparacao: sao acoes diferentes, de pessoas diferentes (ADR-0033).
    if act.teto_composto(pedido, ctx.actor.max_response_level) != pedido:
        return env.refusal(
            "compare_kpi", ctx.request_id, semtrace.novo_trace_id(),
            classe="NIVEL_SEM_EVIDENCIA",
            mensagem=f"comparar opera em CONTEXT, e o teto deste ator e "
                     f"{ctx.actor.max_response_level}.",
            o_que_resolveria="pedir CONTEXT ao administrador, ou consultar os "
                             "dois periodos com `get_kpi`",
            detalhe={"teto_do_ator": ctx.actor.max_response_level},
            response_level={"requested": pedido, "granted": None,
                            "ceiling_from": env.CEILING_ATOR},
            limits=limits.aplicados()), None, 0

    erro = _erro_de_periodo("compare_kpi", ctx, period.get("grain"),
                            str(period.get("from")),
                            str(period.get("to") or period.get("from")))
    if erro:
        return erro, None, 0

    if compare_to == "periodo_declarado" and not compare_period:
        return env.refusal(
            "compare_kpi", ctx.request_id, semtrace.novo_trace_id(),
            classe="COMPARACAO_NAO_RESPONDIVEL",
            mensagem="`periodo_declarado` exige `compare_period`: a base "
                     "declarada e um periodo, e nao ha o que derivar.",
            o_que_resolveria="declarar o periodo de comparacao, ou escolher "
                             "uma base relativa",
            detalhe={"compare_to": compare_to},
            limits=limits.aplicados()), None, 0

    if compare_period:
        erro = _erro_de_periodo(
            "compare_kpi", ctx, compare_period.get("grain"),
            str(compare_period.get("from")),
            str(compare_period.get("to") or compare_period.get("from")))
        if erro:
            return erro, None, 0

    nivel_para_f7 = act.teto_composto(pedido, ctx.actor.max_response_level)
    envelope, ans, kpi_obj, dur = _executa(
        "compare_kpi", ctx,
        _consulta(kpi, period, filters, nivel_para_f7, compare=compare_to,
                  compare_period=compare_period, kpi_version=kpi_version),
        pedido)
    if envelope is not None:
        return envelope, ans, dur

    if not ans.comparison:
        # A base não é respondível, ou o teto não sustenta CONTEXT. Recusa
        # estruturada, e não um FACT disfarçado de comparação.
        motivo = ("a base de comparacao nao e respondivel neste recorte"
                  if ans.level == "FACT" else
                  f"o KPI nao responde em CONTEXT: teto {ans.level}")
        return env.refusal(
            "compare_kpi", ctx.request_id, ans.trace_id,
            classe="COMPARACAO_NAO_RESPONDIVEL",
            mensagem=f"{kpi} nao pode ser comparado com `{compare_to}`: {motivo}.",
            o_que_resolveria="escolher uma base de comparacao que seja ela "
                             "propria respondivel, dentro da cobertura do KPI",
            detalhe={"compare_to": compare_to, "nivel_obtido": ans.level},
            kpi=_bloco_kpi(kpi_obj), trust=ans.trust,
            response_level=_nivel(pedido, ans, ctx.actor, kpi_obj),
            limits=limits.aplicados()), ans, dur

    c = ans.comparison
    delta = c.get("delta")
    data = {
        "current": {"value": ans.value, "period": ans.scope.get("period"),
                    "population": (ans.coverage or {}).get("population")},
        "baseline": {"value": c["base"]["value"], "period": c["base"]["period"],
                     "trust_status": c["base"].get("trust")},
        "delta": delta,
        "delta_relative": c.get("delta_relativo"),
        "direction": ("ESTAVEL" if not delta else
                      "SUBIU" if delta > 0 else "CAIU"),
        # Nunca CAUSA. Associação no tempo é associação, e o campo existe para
        # que o agente não precise inferir o regime da afirmação (ADR-0015).
        "statement_kind": "ASSOCIACAO",
        "unit": ans.unit,
    }
    return _do_answer("compare_kpi", ctx, ans, pedido, kpi_obj, data), ans, dur


# --------------------------------------------------------------------------- #
# 3. breakdown_kpi
# --------------------------------------------------------------------------- #
def breakdown_kpi(ctx: Contexto, *, kpi: str, period: dict, dimensions: list,
                  filters=None, order_by: str = "value",
                  top_n: int | None = None, requested_level: str = "FACT",
                  kpi_version: str | None = None):
    """O mesmo KPI, um período, quebrado por até duas dimensões permitidas.

    A proteção de privacidade **já pertence à Semantic Layer**. O MCP não
    implementa `minimum_n` de novo: ele preserva a linha suprimida como veio,
    sem reconstruir, inferir, substituir nem remover.
    """
    pedido = requested_level
    if not dimensions:
        return env.error("breakdown_kpi", ctx.request_id, semtrace.novo_trace_id(),
                         classe=env.PARAMETRO_INVALIDO,
                         mensagem="`dimensions` e obrigatorio em breakdown_kpi.",
                         o_que_resolveria="informar 1 ou 2 dimensoes permitidas "
                                          "pelo contrato do KPI"), None, 0
    if len(dimensions) > limits.MAX_DIMENSOES:
        return env.refusal(
            "breakdown_kpi", ctx.request_id, semtrace.novo_trace_id(),
            classe=env.LIMITE_DE_RESULTADO_EXCEDIDO,
            mensagem=f"{len(dimensions)} dimensoes pedidas, e o limite e "
                     f"{limits.MAX_DIMENSOES}.",
            o_que_resolveria=f"quebrar por no maximo {limits.MAX_DIMENSOES} "
                             "dimensoes; tres pulverizam o recorte abaixo do n minimo",
            detalhe={"pedidas": list(dimensions)},
            limits=limits.aplicados()), None, 0

    negada = ctx.actor.dimensao_negada(dimensions)
    if negada:
        return env.refusal(
            "breakdown_kpi", ctx.request_id, semtrace.novo_trace_id(),
            classe="DIMENSAO_NAO_PERMITIDA",
            mensagem=f"este ator nao recorta por {negada!r}.",
            o_que_resolveria="pedir a dimensao ao administrador, ou consultar "
                             "por outra dimensao permitida",
            detalhe={"dimensao": negada, "origem": env.CEILING_ATOR},
            limits=limits.aplicados()), None, 0

    erro = _erro_de_periodo("breakdown_kpi", ctx, period.get("grain"),
                            str(period.get("from")),
                            str(period.get("to") or period.get("from")))
    if erro:
        return erro, None, 0

    nivel_para_f7 = act.teto_composto(pedido, ctx.actor.max_response_level)
    envelope, ans, kpi_obj, dur = _executa(
        "breakdown_kpi", ctx,
        _consulta(kpi, period, filters, nivel_para_f7, dimensions=list(dimensions),
                  kpi_version=kpi_version), pedido)
    if envelope is not None:
        return envelope, ans, dur

    linhas = list(ans.rows)
    if len(linhas) > limits.MAX_LINHAS_AVALIADAS:
        return env.refusal(
            "breakdown_kpi", ctx.request_id, ans.trace_id,
            classe=env.LIMITE_DE_RESULTADO_EXCEDIDO,
            mensagem=f"a quebra produz {len(linhas)} linhas, e o limite avaliado "
                     f"e {limits.MAX_LINHAS_AVALIADAS}.",
            o_que_resolveria="estreitar o periodo, filtrar, ou pedir `top_n`",
            detalhe={"linhas": len(linhas)},
            kpi=_bloco_kpi(kpi_obj), trust=ans.trust,
            limits=limits.aplicados()), ans, dur

    disponiveis = len(linhas)
    truncou_por_pedido = False
    if order_by == "value":
        linhas.sort(key=lambda l: (l.get("valor") is None, -(l.get("valor") or 0)))
    else:
        linhas.sort(key=lambda l: tuple(str(l.get(d)) for d in dimensions))

    if top_n is not None:
        if top_n > limits.MAX_LINHAS_RETORNADAS:
            return env.refusal(
                "breakdown_kpi", ctx.request_id, ans.trace_id,
                classe=env.LIMITE_DE_RESULTADO_EXCEDIDO,
                mensagem=f"`top_n` de {top_n} acima do limite de "
                         f"{limits.MAX_LINHAS_RETORNADAS}.",
                o_que_resolveria=f"pedir no maximo {limits.MAX_LINHAS_RETORNADAS} linhas",
                kpi=_bloco_kpi(kpi_obj), trust=ans.trust,
                limits=limits.aplicados()), ans, dur
        truncou_por_pedido = top_n < disponiveis
        linhas = linhas[:top_n]
    elif disponiveis > limits.MAX_LINHAS_RETORNADAS:
        # Nunca truncagem silenciosa: um top-50 apresentado como total e um
        # numero errado com cara de certo.
        return env.refusal(
            "breakdown_kpi", ctx.request_id, ans.trace_id,
            classe=env.LIMITE_DE_RESULTADO_EXCEDIDO,
            mensagem=f"a quebra produz {disponiveis} linhas, acima das "
                     f"{limits.MAX_LINHAS_RETORNADAS} retornaveis.",
            o_que_resolveria="pedir `top_n` explicitamente, ou estreitar o recorte",
            detalhe={"linhas": disponiveis},
            kpi=_bloco_kpi(kpi_obj), trust=ans.trust,
            limits=limits.aplicados()), ans, dur

    plano = plans.plano(kpi_obj.kpi_id)
    somavel = plano.measure.tipo in MEDIDAS_SOMAVEIS

    rows = []
    for l in linhas:
        rows.append({
            "keys": {d: l.get(d) for d in dimensions},   # membro nomeado, nunca null
            "value": l.get("valor"),
            "population": l.get("populacao"),
            "suppressed": bool(l.get("suprimido")),
            "suppression_reason": l.get("motivo_supressao"),
        })

    total = None
    if somavel and not truncou_por_pedido:
        publicados = [r["value"] for r in rows if not r["suppressed"]
                      and r["value"] is not None]
        total = {"value": sum(publicados) if publicados else None,
                 "population": (ans.coverage or {}).get("population"),
                 "nota": "soma das linhas publicadas; as suprimidas nao entram"}

    data = {
        "dimensions": list(dimensions),
        "rows": rows,
        "total": total,
        "rows_returned": len(rows),
        "rows_available": disponiveis,
        "rows_suppressed": sum(1 for r in rows if r["suppressed"]),
        "coverage": ans.coverage,
    }
    return _do_answer("breakdown_kpi", ctx, ans, pedido, kpi_obj, data,
                      extra_limits={"top_n_aplicado": top_n,
                                    "truncado_a_pedido": truncou_por_pedido}), ans, dur


# --------------------------------------------------------------------------- #
# 4. get_kpi_definition
# --------------------------------------------------------------------------- #
def get_kpi_definition(ctx: Contexto, *, kpi: str | None = None,
                       version: str | None = None, include=None):
    """O contrato em linguagem de negócio.

    É a tool que impede o agente de inventar a definição — e a única que
    responde para um KPI `BLOCKED`, que é justamente a razão de ela existir:
    `internal_mobility_rate` não dá número, e dá explicação.

    `source_tables` **não sai**: o agente não precisa dele para explicar um
    número, e expô-lo daria nomes físicos para tentar usar.
    """
    tid = semtrace.novo_trace_id()
    cat = ctx.engine.catalog

    if kpi is None:
        itens = [{"kpi_id": k.kpi_id, "name": k.doc.get("name"),
                  "status": k.status, "version": k.version, "owner": k.owner,
                  "response_ceiling": k.teto_nivel}
                 for k in (cat[i] for i in cat.ids) if ctx.actor.pode_kpi(k.kpi_id)]
        return env.answer("get_kpi_definition", ctx.request_id, tid,
                          data={"catalog": itens, "total": len(itens)},
                          limits=limits.aplicados()), None, 0

    obj = cat.get(kpi)
    if obj is None:
        return env.refusal(
            "get_kpi_definition", ctx.request_id, tid,
            classe="KPI_INEXISTENTE",
            mensagem=f"nao existe KPI com id {kpi!r} no catalogo.",
            o_que_resolveria=f"consultar um dos KPIs do catalogo: "
                             f"{', '.join(cat.ids)}",
            limits=limits.aplicados()), None, 0

    if version and version != obj.version:
        return env.refusal(
            "get_kpi_definition", ctx.request_id, tid,
            classe="VERSAO_INEXISTENTE",
            mensagem=f"a versao {version} de {kpi} nao esta registrada; "
                     f"a corrente e {obj.version}.",
            o_que_resolveria="consultar uma versao registrada do KPI",
            detalhe={"corrente": obj.version},
            kpi=_bloco_kpi(obj), limits=limits.aplicados()), None, 0

    d = obj.doc
    cobertura = obj.period_coverage
    data = {
        "kpi_id": obj.kpi_id,
        "name": d.get("name"),
        "description": d.get("description"),
        "business_definition": d.get("business_definition"),
        "formula_plain": d.get("formula"),        # linguagem de negocio, nunca SQL
        "unit": (plans.plano(obj.kpi_id).measure.unidade
                 if plans.plano(obj.kpi_id) else None),
        "grain": d.get("grain"),
        "population": d.get("population"),
        "period_grain": obj.period_grain,
        "period_rollup": obj.period_rollup,
        "period_coverage": ({"from": cobertura[0], "to": cobertura[1]}
                            if cobertura else None),
        "allowed_dimensions": obj.allowed_dimensions,
        "fixed_filters": d.get("filters") or [],
        "exclusions": d.get("exclusions") or [],
        "minimum_n": obj.minimum_n,
        "response_levels": {
            "ceiling": obj.teto_nivel,
            "why": ("KPI em " + obj.status if obj.teto_nivel is None else
                    "sem interpretation_rules registradas"
                    if not d.get("interpretation_rules") else
                    "regra de interpretacao registrada"),
        },
        "governance": {
            "owner": obj.owner, "version": obj.version, "status": obj.status,
            "certified_at": (d.get("certification") or {}).get("approved_at"),
            "blockers": obj.bloqueadores,
        },
        "dependencies": {
            "checks_count": len(d.get("depends_on_checks") or []),
            "mappings": list(d.get("depends_on_mappings") or []),
        },
        "interpretation_rules": d.get("interpretation_rules") or [],
        "versions_queryable": [obj.version],
    }
    for proibido in NAO_EXPOSTO_NA_DEFINICAO:
        data.pop(proibido, None)
    return env.answer("get_kpi_definition", ctx.request_id, tid, data=data,
                      kpi=_bloco_kpi(obj), limits=limits.aplicados()), None, 0


# --------------------------------------------------------------------------- #
# 5. get_trust
# --------------------------------------------------------------------------- #
def get_trust(ctx: Contexto, *, kpi: str, period: dict | None = None,
              scope: dict | None = None, explain: bool = True):
    """A confiança de um KPI num recorte, **sem calcular o valor**.

    Responde "posso confiar nesse número?" e, principalmente, "o que precisa
    acontecer para eu poder". Os três estados da F5/F7 são preservados: o MCP
    nunca transforma `BLOCKED` em `LIMITED` ou `CERTIFIED`, e não cria score
    paralelo — o único número medido continua sendo o `trust_dado`.
    """
    tid = semtrace.novo_trace_id()
    cat = ctx.engine.catalog
    obj = cat.get(kpi)
    if obj is None:
        return env.refusal(
            "get_trust", ctx.request_id, tid, classe="KPI_INEXISTENTE",
            mensagem=f"nao existe KPI com id {kpi!r} no catalogo.",
            o_que_resolveria=f"consultar um dos KPIs do catalogo: {', '.join(cat.ids)}",
            limits=limits.aplicados()), None, 0

    # Resolve os filtros pelo vocabulário governado, sem executar nada. Termo
    # desconhecido continua sendo recusa, nunca aproximação.
    resolvido = {"filtros": [], "predicados": []}
    filtros = (scope or {}).get("filters") or []
    for f in filtros:
        membros = []
        for termo in f.get("in") or []:
            membro, pred, erro = ctx.engine.vocab.resolve(f.get("dimension"), termo)
            if erro:
                return env.refusal(
                    "get_trust", ctx.request_id, tid, classe="TERMO_DESCONHECIDO",
                    mensagem=erro,
                    o_que_resolveria="usar um termo declarado do vocabulario",
                    detalhe={"dimensao": f.get("dimension"), "termo": termo},
                    kpi=_bloco_kpi(obj), limits=limits.aplicados()), None, 0
            if membro:
                membros.append(membro)
        if membros:
            resolvido["filtros"].append({"dimension": f["dimension"],
                                         "members": membros})

    declarada = (obj.cobertura_declarada or {}).get("population_covered")
    t = certify.certify(ctx.engine.cfg, obj, resolvido, populacao=0,
                        cobertura_populacao=declarada,
                        trust_df=ctx.engine.trust_df)
    bloco = t.to_dict()

    data = {
        "status": bloco["status"],
        "score": bloco["score"],
        "trust_dado": bloco["trust_dado"],
        "trust_governanca": bloco["trust_governanca"],
        "limitado_por": bloco["limitado_por"],
        "motivo": bloco["motivo"],
        "composition": {
            "formula": "min(trust_dado, teto_do_status, teto_do_ator)",
            "bands": {"CERTIFIED": certify.__dict__.get("BANDS", None) or None},
        },
        "attribution": {
            "perda_por_erro": bloco["perda_por_erro"],
            "perda_por_pendencia": bloco["perda_por_pendencia"],
            "perda_por_classe": bloco["perda_por_classe"],
        },
        "verification": {
            "checks_avaliados": bloco["checks_avaliados"],
            "checks_declarados": bloco["checks_declarados"],
            "coverage": bloco["cobertura_de_verificacao"],
            "nota": "check nao avaliado nao e confianca nem perda",
        },
        "scope": {"recorte_usado": bloco["recorte_usado"],
                  "period": period, "filters": filtros},
    }
    from analytics.trust import BANDS, PISO_PENDENCIA
    data["composition"]["bands"] = {**BANDS, "piso_pendencia": PISO_PENDENCIA}

    if explain:
        data["what_would_improve_it"] = _o_que_melhoraria(obj, t)

    return env.answer("get_trust", ctx.request_id, tid, data=data,
                      kpi=_bloco_kpi(obj), trust=bloco,
                      limits=limits.aplicados()), None, 0


def _o_que_melhoraria(kpi, t) -> list[str]:
    """O campo que transforma trust em ação.

    Sem ele, `LIMITED` é um adjetivo. Com ele, é um encaminhamento: pendência de
    dado vai para engenharia e qualidade, pendência de definição vai para People
    Analytics.
    """
    saida: list[str] = []
    if kpi.status == "BLOCKED":
        for b in kpi.bloqueadores:
            saida.append(b.get("resolvido_por") or "resolver o bloqueador declarado")
        return saida
    if kpi.status in ("DECLARED", "DEPRECATED"):
        saida.append("certificar o KPI: e decisao de People Analytics, registrada "
                     "com dono e data, e nao consequencia do dado (ADR-0029)")
    cob = (kpi.cobertura_declarada or {}).get("population_covered")
    if cob is not None and cob < 1.0:
        saida.append(f"elevar a cobertura de populacao, hoje em {cob:.1%}: "
                     + ((kpi.cobertura_declarada or {}).get("nota") or ""))
    if t.perda_por_pendencia:
        saida.append("resolver as pendencias de governanca que compoem a perda "
                     "por pendencia (mapeamento, identidade, decisao)")
    if t.perda_por_erro:
        saida.append("corrigir na fonte os registros que reprovam nos checks de "
                     "validade")
    if t.cobertura_de_verificacao is not None and t.cobertura_de_verificacao < 1.0:
        saida.append(f"ampliar a cobertura de verificacao: {t.checks_avaliados} de "
                     f"{t.checks_declarados} checks rodaram neste recorte")
    return saida or ["nada pendente neste recorte"]


# --------------------------------------------------------------------------- #
# 6. get_lineage
# --------------------------------------------------------------------------- #
class _AnswerDoLog:
    """Adaptador mínimo para reconstruir a linhagem de uma resposta passada.

    `semtrace.trace` foi escrito para um `Answer` vivo. Uma resposta de semanas
    atrás só existe no `semantic_query_log`, com escopo, nível, valor e trust.
    Este adaptador entrega o que o log guardou e nada mais: os campos que não
    foram registrados ficam ausentes, e não preenchidos por adivinhação.
    """

    def __init__(self, linha: dict) -> None:
        import json
        self.trace_id = linha["trace_id"]
        self.level = linha.get("level")
        self.value = linha.get("valor")
        self.scope = json.loads(linha.get("recorte") or "{}")
        self.trust = {"status": linha.get("trust_status"),
                      "score": linha.get("trust_score"),
                      "recorte_usado": None, "perda_por_classe": None}
        self.rows = []
        self.caveats = json.loads(linha.get("caveats") or "[]")


def get_lineage(ctx: Contexto, *, trace_id: str | None = None,
                kpi: str | None = None, depth: str = "table"):
    """Os seis degraus, da resposta até o `_row_id` da fonte.

    O degrau `fonte` **descreve o caminho; não o percorre**. Ele diz por onde
    uma pessoa com acesso chega ao valor original, e não devolve o valor
    original, nem `source_row_id` de ninguém, nem amostra de linhas. Percorrer o
    último degrau é leitura de RAW, e nenhuma tool deste MCP faz isso.
    """
    tid = semtrace.novo_trace_id()
    cat = ctx.engine.catalog

    if not trace_id and not kpi:
        return env.error("get_lineage", ctx.request_id, tid,
                         classe=env.PARAMETRO_INVALIDO,
                         mensagem="informe `trace_id` ou `kpi`.",
                         o_que_resolveria="passar o trace_id de uma resposta "
                                          "anterior, ou o id de um KPI"), None, 0

    if trace_id:
        linha = semtrace.ler(ctx.engine.cfg, trace_id)
        if linha is None:
            return env.refusal(
                "get_lineage", ctx.request_id, tid, classe=env.TRACE_INEXISTENTE,
                mensagem=f"o trace_id {trace_id!r} nao esta no registro de consultas.",
                o_que_resolveria="usar o `trace_id` devolvido por uma chamada "
                                 "anterior deste MCP",
                limits=limits.aplicados()), None, 0
        obj = cat.get(linha["kpi_id"])
        if obj is None:
            return env.refusal(
                "get_lineage", ctx.request_id, tid, classe=env.LINEAGE_INDISPONIVEL,
                mensagem=f"a resposta {trace_id} cita um KPI que nao esta mais no "
                         "catalogo.",
                o_que_resolveria="consultar a linhagem de um KPI corrente",
                limits=limits.aplicados()), None, 0
        base = semtrace.trace(ctx.engine.cfg, _AnswerDoLog(linha), obj)
        base["resposta"]["kpi_version"] = linha.get("kpi_version")
        base["tabela_analitica"]["l3_run_id"] = linha.get("l3_run_id")
        base["tabela_analitica"]["linhas_consideradas"] = None
        base["tabela_analitica"]["nota"] = (
            "linhagem reconstruida do registro de consultas; a contagem de linhas "
            "nao foi registrada")
    else:
        obj = cat.get(kpi)
        if obj is None:
            return env.refusal(
                "get_lineage", ctx.request_id, tid, classe="KPI_INEXISTENTE",
                mensagem=f"nao existe KPI com id {kpi!r} no catalogo.",
                o_que_resolveria=f"consultar um dos KPIs do catalogo: "
                                 f"{', '.join(cat.ids)}",
                limits=limits.aplicados()), None, 0
        vazio = _AnswerDoLog({"trace_id": tid, "level": None, "valor": None,
                              "recorte": "{}", "trust_status": None,
                              "trust_score": None, "caveats": "[]"})
        base = semtrace.trace(ctx.engine.cfg, vazio, obj)
        base["resposta"] = {"trace_id": None,
                            "nota": "linhagem de definicao: nenhuma resposta a "
                                    "rastrear"}

    # O degrau de fonte nunca é percorrido, em nenhuma profundidade.
    base["fonte"]["acesso"] = "NAO_EXPOSTO_POR_ESTE_MCP"
    ordem = ["resposta", "kpi", "definicao", "regra", "tabela_analitica", "fonte"]
    corte = {"definition": 3, "rule": 4, "table": 5, "source": 6}.get(depth, 5)
    data = {k: base[k] for k in ordem[:corte]}
    data["fonte"] = base["fonte"]          # a descrição do caminho sai sempre
    data["depth"] = depth
    return env.answer("get_lineage", ctx.request_id, tid, data=data,
                      kpi=_bloco_kpi(obj), limits=limits.aplicados()), None, 0
