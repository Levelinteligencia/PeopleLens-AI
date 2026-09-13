"""RESPOND: a resposta em texto, e as regras que ela obedece (SPEC Partes IX e X).

Regras que este módulo faz valer, e que não são pedidas ao modelo:

1. **todo número citado vem de um envelope**, com `trace_id` (Política P-01).
   O renderizador não recebe números soltos: ele lê observações;
2. **nenhuma aritmética entre envelopes.** Diferença vem de `compare_kpi`, e a
   decisão A-05 permite mostrar dois valores lado a lado sem calcular nada;
3. **`LIMITED` põe a ressalva na mesma frase**, não em rodapé — rodapé é o que
   não se lê, e oito dos treze KPIs respondem `LIMITED` hoje;
4. **recusa tem quatro partes**: o que não responde, por quê, o que resolveria,
   e a pergunta vizinha que responde;
5. **parcial se declara parcial**;
6. **associação nunca sai com verbo de causa**, e há verificação.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from analytics.semantic.response import viola_regra_de_redacao

from . import loop as L


@dataclass
class Resposta:
    texto: str
    level: str | None
    stop_reason: str
    trust: dict | None = None
    trace_ids: list[str] = field(default_factory=list)
    parcial: bool = False
    pergunta_de_volta: list[str] = field(default_factory=list)
    numeros_citados: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"texto": self.texto, "level": self.level,
                "stop_reason": self.stop_reason, "trust": self.trust,
                "trace_ids": list(self.trace_ids), "parcial": self.parcial,
                "pergunta_de_volta": list(self.pergunta_de_volta)}


def _pct(v) -> str:
    return f"{v * 100:.2f}%".replace(".", ",")


def _num(v, unidade: str) -> str:
    if v is None:
        return "—"
    if unidade in ("share", "taxa"):
        return _pct(v)
    if isinstance(v, float):
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{v:,}".replace(",", ".")


def _periodo(p: dict | None) -> str:
    if not p:
        return ""
    ini, fim = p.get("from"), p.get("to") or p.get("from")
    return ini if ini == fim else f"{ini}..{fim}"


def _ressalva_de_trust(trust: dict | None) -> str:
    """A ressalva do `LIMITED`, na mesma frase e dizendo qual lado prendeu."""
    if not trust:
        return ""
    status = trust.get("status")
    if status == "CERTIFIED":
        return ""
    if status == "INDETERMINADO":
        return (" — sem check aplicável a este recorte, o que não é o mesmo que "
                "estar tudo bem")
    limitado = trust.get("limitado_por")
    motivo = {
        "GOVERNANCA": "o KPI não está certificado; certificar é decisão de People Analytics",
        "COBERTURA": "a cobertura de população declarada no contrato é parcial",
        "DADO": "a confiança do dado neste recorte não é total",
    }.get(limitado, trust.get("motivo") or "há limitação declarada")
    return f" — confiança {status}, porque {motivo}"


ENCAMINHAMENTO = {
    "EVIDENCIA": "não há regra de interpretação registrada para este KPI",
    "GOVERNANCA": "este KPI não está certificado, e certificar é decisão de "
                  "People Analytics",
    "TRUST": "a confiança do dado neste recorte não sustenta esse nível",
    "ATOR": "seu perfil de acesso não inclui esse nível de resposta",
}


# --------------------------------------------------------------------------- #
def ambiguidade(intent) -> Resposta:
    """A-01: pergunta de volta, com as opções válidas. Zero chamadas de valor."""
    linhas = ["Não consigo responder isso sem confirmar alguns pontos:"]
    perguntas = []
    for a in intent.ambiguity:
        if a.opcoes:
            mostrados = [str(o) for o in a.opcoes[:12]]
            resto = len(a.opcoes) - len(mostrados)
            opcoes = ", ".join(mostrados) + (f" (e mais {resto})" if resto else "")
            linhas.append(f"- {a.motivo}. Opções válidas: {opcoes}.")
            perguntas.append(f"{a.campo}: {opcoes}")
        else:
            linhas.append(f"- {a.motivo}.")
            perguntas.append(a.campo)
    linhas.append("Me diga qual combinação você quer e eu respondo.")
    return Resposta(texto="\n".join(linhas), level=None,
                    stop_reason=L.AMBIGUIDADE, pergunta_de_volta=perguntas)


def recusa(envelope: dict, contexto=None) -> Resposta:
    """As quatro partes: o quê, por quê, o que resolveria, a pergunta vizinha."""
    r = envelope.get("refusal") or {}
    partes = [r.get("mensagem", "Não consigo responder.")]
    if r.get("o_que_resolveria"):
        partes.append(f"Para responder seria necessário: {r['o_que_resolveria']}.")

    alternativa = _alternativa(envelope, r, contexto)
    if alternativa:
        partes.append(alternativa)

    return Resposta(texto=" ".join(partes), level=None,
                    stop_reason=L.RECUSA_GOVERNADA,
                    trust=envelope.get("trust"),
                    trace_ids=[envelope.get("trace_id", "")])


def _alternativa(envelope: dict, r: dict, contexto) -> str:
    """A pergunta vizinha que responde — quando ela existe de verdade.

    Em `KPI_BLOQUEADO` **não se oferece KPI substituto**: oferecer
    `internal_mobility_rate` a quem pediu `promotion_rate` parece prestativo e é
    escolher em silêncio um KPI parecido, que é a proibição central.
    """
    classe = r.get("classe")
    detalhe = r.get("detalhe") or {}
    if classe == "PERIODO_FORA_DE_COBERTURA" and detalhe.get("cobertura"):
        ini, fim = detalhe["cobertura"]
        return f"Posso responder dentro de {ini} a {fim}."
    if classe == "DIMENSAO_NAO_PERMITIDA" and detalhe.get("permitidas"):
        return ("Posso responder por: "
                + ", ".join(detalhe["permitidas"]) + ".")
    if classe == "KPI_BLOQUEADO":
        return ("Não vou sugerir outro indicador no lugar: escolher um parecido "
                "seria trocar a definição sem você saber.")
    return ""


def supressao(envelope: dict) -> Resposta:
    """A palavra é privacidade, e a frase diz que não é desconfiança no dado."""
    s = envelope.get("suppressed") or {}
    texto = (
        f"Esse recorte não pode ser mostrado por **privacidade**: ele tem menos "
        f"pessoas do que o mínimo de {s.get('minimum_n')} que este indicador "
        "exige. Não é desconfiança no dado — é proteção de quem está no grupo. "
        "Posso responder um recorte mais amplo.")
    return Resposta(texto=texto, level=None, stop_reason=L.SUPRESSAO,
                    trust=envelope.get("trust"),
                    trace_ids=[envelope.get("trace_id", "")])


def bloqueio_de_privacidade(motivo: str) -> Resposta:
    """A-03: o Harness barrou a consulta de contorno."""
    texto = ("Não vou por esse caminho: a consulta anterior foi suprimida por "
             "privacidade, e refazer a pergunta com um recorte diferente no "
             "mesmo indicador e período seria uma tentativa de descobrir o valor "
             "protegido. Posso responder um recorte mais amplo.")
    return Resposta(texto=texto, level=None, stop_reason=L.SUPRESSAO)


def falha_tecnica(envelope: dict) -> Resposta:
    r = envelope.get("refusal") or {}
    texto = (f"Houve uma falha na consulta: {r.get('mensagem', 'erro não descrito')}. "
             "Não vou estimar um valor no lugar.")
    return Resposta(texto=texto, level=None, stop_reason=L.FALHA_TECNICA,
                    trace_ids=[envelope.get("trace_id", "")])


def negacao_causal(intent, observacoes: list[dict]) -> Resposta:
    """A negação útil: diz o que responderia, e não afirma causa.

    Antes disso, corrige a premissa quando o dado a contradiz. "Por que o
    turnover aumentou?" quando ele caiu: aceitar a premissa para ser prestativo
    é concordar com algo falso.
    """
    partes = []
    for env in observacoes:
        correcao = corrigir_premissa(intent, env)
        if correcao:
            partes.append(correcao)
            break
    contexto_txt = valor_de_contexto(observacoes)
    if contexto_txt:
        partes.append(contexto_txt)
    partes.append(
        "Sobre o motivo: não posso afirmar. Não há estudo causal registrado para "
        "este indicador, e uma variação no tempo mostra associação. "
        "Responderia isso um estudo com grupo de tratamento e de controle "
        "comparáveis, efeito estimado, intervalo de confiança e limitações "
        "declaradas, aprovado por People Analytics.")
    return Resposta(texto=" ".join(partes), level="CONTEXT" if contexto_txt else None,
                    stop_reason=L.SUFICIENTE,
                    trace_ids=[o.get("trace_id", "") for o in observacoes])


def valor_de_contexto(observacoes: list[dict]) -> str:
    """O que os envelopes sustentam, sem nenhuma conta feita aqui."""
    for env in observacoes:
        d = env.get("data") or {}
        if "current" in d and "baseline" in d:
            unidade = d.get("unit", "")
            atual, base = d["current"], d["baseline"]
            direcao = {"SUBIU": "subiu", "CAIU": "caiu",
                       "ESTAVEL": "ficou estável"}.get(d.get("direction"), "variou")
            return (f"{_num(atual['value'], unidade)} em "
                    f"{_periodo(atual['period'])}, contra "
                    f"{_num(base['value'], unidade)} em {_periodo(base['period'])}: "
                    f"{direcao}. É uma variação observada no tempo, ou seja, "
                    f"associação.")
    return ""


def resposta_de_valor(envelope: dict, intent=None) -> Resposta:
    d = envelope.get("data") or {}
    trust = envelope.get("trust") or {}
    nivel = (envelope.get("response_level") or {}).get("granted")
    unidade = d.get("unit", "")
    kpi = (envelope.get("kpi") or {}).get("id", "")

    if d.get("series"):
        linhas = [f"{p['period']}: {_num(p['value'], unidade)}"
                  for p in d["series"] if not p.get("suppressed")]
        corpo = (f"{kpi}, por período{_ressalva_de_trust(trust)}:\n"
                 + "\n".join(f"- {l}" for l in linhas))
        numeros = [p["value"] for p in d["series"] if p.get("value") is not None]
    else:
        corpo = (f"{_num(d.get('value'), unidade)}"
                 + (f" {unidade}" if unidade not in ("share", "taxa") else "")
                 + f" em {_periodo(d.get('period'))}"
                 + _ressalva_de_trust(trust) + ".")
        numeros = [d.get("value")] if d.get("value") is not None else []

    extras = []
    cob = d.get("coverage") or {}
    if cob.get("population_covered") is not None and cob["population_covered"] < 1:
        extras.append(f"A cobertura de população declarada é de "
                      f"{cob['population_covered'] * 100:.1f}%".replace(".", ",") + ".")
    teto = (envelope.get("response_level") or {}).get("ceiling_from")
    if teto in ("GOVERNANCA", "TRUST", "ATOR") and nivel:
        extras.append(f"Não posso ir além de {nivel} aqui: "
                      f"{ENCAMINHAMENTO.get(teto, '')}.")

    texto = " ".join([corpo, *extras]).strip()
    return Resposta(texto=texto, level=nivel, stop_reason=L.SUFICIENTE,
                    trust=trust, trace_ids=[envelope.get("trace_id", "")],
                    numeros_citados=[n for n in numeros if n is not None])


def resposta_de_comparacao(envelope: dict) -> Resposta:
    d = envelope.get("data") or {}
    trust = envelope.get("trust") or {}
    unidade = d.get("unit", "")
    atual, base = d.get("current", {}), d.get("baseline", {})
    direcao = {"SUBIU": "subiu", "CAIU": "caiu",
               "ESTAVEL": "ficou estável"}.get(d.get("direction"), "variou")
    delta_rel = d.get("delta_relative")
    txt_rel = f" ({_pct(delta_rel)})" if delta_rel is not None else ""
    texto = (f"{_num(atual.get('value'), unidade)} em {_periodo(atual.get('period'))}, "
             f"contra {_num(base.get('value'), unidade)} em "
             f"{_periodo(base.get('period'))}: {direcao}{txt_rel}"
             f"{_ressalva_de_trust(trust)}. É uma variação observada no tempo, "
             "ou seja, associação: não sustenta afirmação de causalidade.")
    return Resposta(texto=texto,
                    level=(envelope.get("response_level") or {}).get("granted"),
                    stop_reason=L.SUFICIENTE, trust=trust,
                    trace_ids=[envelope.get("trace_id", "")],
                    numeros_citados=[v for v in (atual.get("value"),
                                                 base.get("value"),
                                                 d.get("delta"))
                                     if v is not None])


def resposta_lado_a_lado(envelopes: list[dict]) -> Resposta:
    """A-05: dois valores independentes, e nenhuma conta entre eles.

    A comparação formal foi recusada, e é isso que a resposta diz. Calcular a
    diferença aqui reconstruiria por fora o que a camada governada recusou.
    """
    linhas, numeros, traces = [], [], []
    unidade = ""
    for env in envelopes:
        d = env.get("data") or {}
        unidade = d.get("unit", unidade)
        linhas.append(f"- {_periodo(d.get('period'))}: {_num(d.get('value'), unidade)}")
        if d.get("value") is not None:
            numeros.append(d["value"])
        traces.append(env.get("trace_id", ""))
    texto = ("A comparação formal não foi disponibilizada para este recorte, "
             "então apresento os dois valores como medidas **independentes**, "
             "sem calcular a diferença entre eles:\n" + "\n".join(linhas))
    trust = (envelopes[0].get("trust") if envelopes else None)
    return Resposta(texto=texto, level="FACT", stop_reason=L.SUFICIENTE,
                    trust=trust, trace_ids=traces, numeros_citados=numeros)


def resposta_de_ranking(envelope: dict, unidade: str = "") -> Resposta:
    """Ranking com supressão: nomeia o maior **entre os publicados**.

    No caso real, 19 das 26 linhas saem suprimidas. Um agente que aponta o maior
    visível como se fosse o maior absoluto está errado com cara de certo.
    """
    d = envelope.get("data") or {}
    trust = envelope.get("trust") or {}
    # A unidade vem do contexto fechado (definição do KPI), e não de dentro do
    # payload da quebra: o MCP não a repete lá, e inferi-la do número seria
    # adivinhar se 0,38 é 38% ou 0,38 pessoa.
    unidade = unidade or d.get("unit") or ""
    dims = d.get("dimensions") or []
    publicadas = [r for r in d.get("rows", []) if not r.get("suppressed")]
    suprimidas = d.get("rows_suppressed", 0)

    if not publicadas:
        return Resposta(
            texto=("Nenhum recorte desta quebra pôde ser publicado: todos ficaram "
                   "abaixo do mínimo de pessoas exigido, e a supressão é por "
                   "privacidade, não por qualidade do dado."),
            level=None, stop_reason=L.SUPRESSAO, trust=trust,
            trace_ids=[envelope.get("trace_id", "")])

    linhas = [f"- {', '.join(str(r['keys'][k]) for k in dims)}: "
              f"{_num(r['value'], unidade)}" for r in publicadas[:10]]
    ressalva = ""
    if suprimidas:
        ressalva = (f" {suprimidas} de {len(d.get('rows', []))} recortes não "
                    "puderam ser mostrados por privacidade, então **este não é "
                    "necessariamente o maior de todos** — é o maior entre os "
                    "publicados.")
    texto = (f"Entre os recortes publicados{_ressalva_de_trust(trust)}:\n"
             + "\n".join(linhas) + ressalva)
    return Resposta(texto=texto,
                    level=(envelope.get("response_level") or {}).get("granted"),
                    stop_reason=L.SUFICIENTE, trust=trust,
                    trace_ids=[envelope.get("trace_id", "")],
                    numeros_citados=[r["value"] for r in publicadas
                                     if r.get("value") is not None])


def resposta_de_definicao(envelope: dict) -> Resposta:
    d = envelope.get("data") or {}
    gov = d.get("governance") or {}
    partes = [d.get("business_definition", "")]
    if d.get("period_grain"):
        partes.append(f"É apurado por {d['period_grain']}.")
    cov = d.get("period_coverage")
    if cov:
        partes.append(f"Há dado de {cov['from']} a {cov['to']}.")
    if d.get("minimum_n"):
        partes.append(f"Recortes com menos de {d['minimum_n']} pessoas não são "
                      "publicados, por privacidade.")
    if d.get("exclusions"):
        fora = "; ".join(e.get("o_que", "") for e in d["exclusions"][:2])
        partes.append(f"Ficam de fora: {fora}.")
    if gov.get("status") == "BLOCKED" and gov.get("blockers"):
        partes.append(f"Hoje ele está bloqueado: {gov['blockers'][0]['motivo']}")
    else:
        teto = (d.get("response_levels") or {}).get("ceiling")
        porque = (d.get("response_levels") or {}).get("why")
        partes.append(f"O teto de resposta é {teto}, porque {porque}.")
    return Resposta(texto=" ".join(p for p in partes if p), level=None,
                    stop_reason=L.SUFICIENTE,
                    trace_ids=[envelope.get("trace_id", "")])


def resposta_de_trust(envelope: dict) -> Resposta:
    d = envelope.get("data") or {}
    partes = [f"A confiança é **{d.get('status')}**"]
    if d.get("score") is not None:
        partes[0] += f", com score de {d['score']:.4f}".replace(".", ",")
    partes[0] += f", limitada por {d.get('limitado_por')}."
    melhora = d.get("what_would_improve_it") or []
    if melhora:
        partes.append("O que melhoraria: " + "; ".join(melhora[:3]) + ".")
    return Resposta(texto=" ".join(partes), level=None, stop_reason=L.SUFICIENTE,
                    trust=d, trace_ids=[envelope.get("trace_id", "")])


def resposta_de_linhagem(envelope: dict) -> Resposta:
    d = envelope.get("data") or {}
    kpi = d.get("kpi") or {}
    definicao = d.get("definicao") or {}
    tabela = d.get("tabela_analitica") or {}
    partes = [
        f"O número vem de {kpi.get('id')} versão {kpi.get('version')}, "
        f"assinado por {kpi.get('owner')}.",
        f"A definição é: {definicao.get('business_definition')}",
        f"O cálculo roda sobre a camada analítica governada"
        + (f" (execução {tabela.get('l3_run_id')})" if tabela.get("l3_run_id") else "")
        + ", com os filtros fixos do contrato aplicados.",
        "Dali a rastreabilidade segue até o registro de origem e o arquivo bruto "
        "imutável, por um caminho que este canal descreve mas não percorre.",
    ]
    return Resposta(texto=" ".join(partes), level=None, stop_reason=L.SUFICIENTE,
                    trace_ids=[envelope.get("trace_id", "")])


def parada_por_limite(stop_reason: str, observacoes: list[dict]) -> Resposta:
    """Parcial, e dito como parcial."""
    base = {
        L.LIMITE_ITERACOES: "atingi o limite de passos desta execução",
        L.LIMITE_CHAMADAS: "atingi o limite de consultas desta execução",
        L.TIMEOUT: "a execução passou do tempo permitido",
        L.REPETICAO: "a próxima consulta repetiria uma que já fiz",
    }.get(stop_reason, "a execução parou")
    texto = (f"Resposta **parcial**: {base}, então o que segue não é a resposta "
             "completa à sua pergunta.")
    uteis = [o for o in observacoes if o.get("outcome") == "ANSWER"]
    if uteis:
        texto += " " + resposta_de_valor(uteis[0]).texto
    return Resposta(texto=texto, level=None, stop_reason=stop_reason,
                    parcial=True,
                    trace_ids=[o.get("trace_id", "") for o in observacoes])


def corrigir_premissa(intent, envelope: dict) -> str:
    """A premissa da pergunta contra o que o dado mostra.

    "Por que o turnover aumentou?" quando ele caiu. Aceitar a premissa para ser
    prestativo é concordar com algo falso; a correção vem antes da resposta, sem
    constranger quem perguntou.
    """
    d = envelope.get("data") or {}
    direcao = d.get("direction")
    if not intent.premissa or not direcao:
        return ""
    if intent.premissa == "AUMENTO" and direcao == "CAIU":
        return "Antes de responder, um ajuste: no período o indicador caiu, não subiu."
    if intent.premissa == "QUEDA" and direcao == "SUBIU":
        return "Antes de responder, um ajuste: no período o indicador subiu, não caiu."
    return ""


def verificar_redacao(resposta: Resposta) -> list[str]:
    """Regra 2 da F7: verbo causal em nível abaixo de CAUSALITY."""
    if resposta.level is None:
        return []
    return viola_regra_de_redacao(resposta.level, resposta.texto)
