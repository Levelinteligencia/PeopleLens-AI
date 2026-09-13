"""PLAN: o plano é um artefato, não um raciocínio (ADR-0034; SPEC Partes VI e VII).

O plano existe **antes** da primeira chamada ao MCP, como objeto estruturado, e
fica no registro. Sem isso, três critérios de aceite ficam inverificáveis: não há
como testar "a seleção de ferramenta é governada" se a escolha vive em raciocínio
oculto, nem como reproduzir uma execução, nem como comparar o que o agente fez
com o que a matriz prescreve.

Cada passo declara **passo, capacidade, motivo e objetivo**. Não entra cadeia de
pensamento: justificativa operacional estruturada, e nada além.

A seleção de capacidade vem da **matriz da SPEC**, aqui como código. É mais
estrito do que a SPEC exigia, de propósito: o modelo não escolhe ferramenta, e
por isso a política P-03 deixa de depender de o modelo obedecer.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .intent import (CAUSAL, COMPARACAO, CONFIANCA, DEFINICAO, LINHAGEM,
                     RANKING, VALOR, Intent)

GET_KPI = "get_kpi"
COMPARE_KPI = "compare_kpi"
BREAKDOWN_KPI = "breakdown_kpi"
GET_DEFINITION = "get_kpi_definition"
GET_TRUST = "get_trust"
GET_LINEAGE = "get_lineage"

# Matriz tipo de pergunta -> capacidade (SPEC §21). É a fonte da seleção.
MATRIZ = {
    VALOR: (GET_KPI,),
    COMPARACAO: (COMPARE_KPI,),
    RANKING: (BREAKDOWN_KPI,),
    DEFINICAO: (GET_DEFINITION,),
    CONFIANCA: (GET_TRUST,),
    LINHAGEM: (GET_LINEAGE,),
    CAUSAL: (COMPARE_KPI, BREAKDOWN_KPI),
}


@dataclass
class Step:
    passo: int
    capacidade: str
    motivo: str
    objetivo: str
    args: dict = field(default_factory=dict)
    origem: str = "MATRIZ"          # MATRIZ | FALLBACK_A05 | SEGUIMENTO

    def to_dict(self) -> dict:
        return {"passo": self.passo, "capacidade": self.capacidade,
                "motivo": self.motivo, "objetivo": self.objetivo,
                "origem": self.origem,
                # os argumentos entram sem valores de filtro, que não vão ao log
                "args": {k: v for k, v in self.args.items() if k != "filters"}}


@dataclass
class Plan:
    steps: list[Step] = field(default_factory=list)
    justificativa: str = ""

    def to_dict(self) -> dict:
        return {"justificativa": self.justificativa,
                "steps": [s.to_dict() for s in self.steps]}

    @property
    def capacidades(self) -> list[str]:
        return [s.capacidade for s in self.steps]


def _periodo_args(intent: Intent) -> dict:
    p = dict(intent.period or {})
    if p.get("to") == p.get("from"):
        p.pop("to", None)
    return p


def _filtros_args(intent: Intent, contexto) -> list[dict]:
    """Filtros no formato do MCP, com o termo canônico do vocabulário.

    Canônico, não aproximado: o termo já passou pelo `RESOLVE` e é igual a um
    termo declarado. O que se faz aqui é usar a grafia oficial.
    """
    saida = []
    for f in intent.filters:
        termos = [contexto.termo_canonico(f["dimension"], t) or t
                  for t in f.get("terms") or []]
        saida.append({"dimension": f["dimension"], "in": termos})
    return saida


def montar(intent: Intent, contexto) -> Plan:
    """O plano, a partir da intenção resolvida. Nunca chamado com ambiguidade."""
    kpi = intent.kpi
    periodo = _periodo_args(intent)
    filtros = _filtros_args(intent, contexto)
    steps: list[Step] = []

    capacidades = MATRIZ.get(intent.question_type, ())

    for i, cap in enumerate(capacidades, start=1):
        args: dict = {"kpi": kpi}
        motivo = objetivo = ""

        if cap == GET_KPI:
            args.update(period=periodo)
            motivo = "pergunta de valor, sem quebra por dimensão"
            objetivo = f"obter o valor governado de {kpi}"
        elif cap == COMPARE_KPI:
            args.update(period=periodo,
                        compare_to=intent.compare_to or "periodo_anterior")
            motivo = ("comparação é capacidade própria; subtrair dois get_kpi "
                      "seria o agente calculando")
            objetivo = f"obter a variação governada de {kpi}"
        elif cap == BREAKDOWN_KPI:
            dims = intent.dimensions or ["departamento"]
            args.update(period=periodo, dimensions=dims)
            motivo = ("pergunta de ranking; vários get_kpi filtrados seriam "
                      "sondagem")
            objetivo = f"obter {kpi} por {', '.join(dims)}"
        elif cap == GET_DEFINITION:
            motivo = "a definição é contrato, e responder de memória seria inventá-la"
            objetivo = f"obter a definição governada de {kpi}"
        elif cap == GET_TRUST:
            args = {"kpi": kpi}
            if filtros:
                args["scope"] = {"filters": filtros}
            motivo = ("pergunta sobre confiança; reinterpretar o trust de um "
                      "get_kpi não responde o que melhoraria")
            objetivo = f"obter a confiança governada de {kpi} no recorte"
        elif cap == GET_LINEAGE:
            args = {"kpi": kpi} if kpi else {}
            motivo = "pergunta de linhagem; descrever o pipeline de memória seria inventar"
            objetivo = "obter os degraus da linhagem"

        if filtros and cap in (GET_KPI, COMPARE_KPI, BREAKDOWN_KPI):
            args["filters"] = filtros
        if cap in (GET_KPI, BREAKDOWN_KPI) and intent.requested_level == "CONTEXT":
            args["requested_level"] = "CONTEXT"

        steps.append(Step(passo=i, capacidade=cap, motivo=motivo,
                          objetivo=objetivo, args=args))

    justificativa = {
        VALOR: "um valor, uma chamada",
        COMPARACAO: "a comparação vem da capacidade que a calcula",
        RANKING: "a quebra vem da capacidade que a calcula, com a supressão dela",
        DEFINICAO: "a definição vem do contrato",
        CONFIANCA: "a confiança vem da capacidade que a explica",
        LINHAGEM: "a linhagem vem da capacidade que a encadeia",
        CAUSAL: ("causalidade não é respondível; o plano coleta o que sustenta "
                 "CONTEXT e a resposta nega a causa"),
    }.get(intent.question_type, "")

    return Plan(steps=steps, justificativa=justificativa)


def passo_de_seguimento(capacidade: str, args: dict, motivo: str,
                        objetivo: str, passo: int, origem: str = "SEGUIMENTO") -> Step:
    return Step(passo=passo, capacidade=capacidade, motivo=motivo,
                objetivo=objetivo, args=args, origem=origem)


def fallback_a05(intent: Intent, contexto, passo: int) -> list[Step]:
    """Decisão A-05: dois `get_kpi` lado a lado quando `compare_kpi` recusa.

    Os dois valores são **apresentação factual independente**, e o plano registra
    isso. Nenhuma aritmética entre eles: sem delta, sem percentual, sem tendência.
    Calcular a diferença seria reconstruir por fora a comparação que a camada
    governada recusou.
    """
    periodo = _periodo_args(intent)
    filtros = _filtros_args(intent, contexto)
    grain = (periodo or {}).get("grain")
    atual = (periodo or {}).get("from")
    anterior = _anterior(grain, atual)
    if anterior is None:
        return []

    motivo = ("A-05: compare_kpi recusou; apresentação factual independente dos "
              "dois períodos, sem cálculo de diferença")
    passos = []
    for i, valor in enumerate((atual, anterior)):
        args = {"kpi": intent.kpi, "period": {"grain": grain, "from": valor}}
        if filtros:
            args["filters"] = filtros
        passos.append(Step(passo=passo + i, capacidade=GET_KPI, motivo=motivo,
                           objetivo=f"valor independente de {intent.kpi} em {valor}",
                           args=args, origem="FALLBACK_A05"))
    return passos


def _anterior(grain: str | None, valor: str | None) -> str | None:
    if not grain or not valor:
        return None
    if grain == "ano":
        return str(int(valor) - 1)
    if grain == "mes":
        ano, mes = int(valor[:4]), int(valor[5:7])
        ano, mes = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
        return f"{ano}-{mes:02d}"
    if grain == "trimestre":
        ano, tri = int(valor[:4]), int(valor[-1])
        ano, tri = (ano - 1, 4) if tri == 1 else (ano, tri - 1)
        return f"{ano}-Q{tri}"
    return None
