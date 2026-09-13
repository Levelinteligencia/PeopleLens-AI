"""Response Contract: nivel, evidencia, ressalvas e trace (ADR-0015, F7 Parte V).

Quatro niveis, e a escada so sobe quando a evidencia sobe:

    FACT            o numero               KPI que responda, trust >= LIMITED,
                                           n >= minimo, dimensao permitida,
                                           periodo coberto
    CONTEXT         o numero comparado     tudo do FACT + base de comparacao
                                           que seja ela propria respondivel
    INTERPRETATION  se e bom ou ruim       tudo do CONTEXT + regra registrada
                                           com dono e data
    CAUSALITY       por que                NEGADO por padrao; exige estudo

As cinco regras de redacao da SPEC valem como contrato de saida, e duas delas
estao implementadas aqui e nao na cabeca de quem escreve o texto:

- associacao vive em CONTEXT e e sempre nomeada como associacao. As palavras
  "porque", "causou", "levou a", "impactou" e "explica" nao aparecem em CONTEXT,
  e ha verificacao;
- CAUSALITY e negada de forma UTIL: a recusa diz o que seria necessario.

`caveats` nao e decorativo: e onde a pendencia que nao derrubou o trust ainda
aparece para quem le.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .catalog import Kpi, ORDEM_NIVEL
from .certify import TrustResposta
from .query import Refusal, SemanticQuery

# Palavras que nao podem aparecer num texto de nivel CONTEXT. Associacao dita
# com verbo de causa vira causalidade na cabeca de quem le, independente do
# rotulo que o campo `level` carregue.
PALAVRAS_CAUSAIS = ("porque", "causou", "causa", "levou a", "impactou",
                    "explica", "por conta de", "devido a", "resultou em")

CAMPOS_OBRIGATORIOS_DA_RESPOSTA = (
    "level", "value", "unit", "kpi", "scope", "trust", "coverage", "caveats", "trace_id")


@dataclass
class Answer:
    """Uma resposta OU uma recusa. As duas carregam `trace_id`: uma recusa sem
    rastro ninguem descobre que se repete toda semana pelo mesmo motivo."""
    trace_id: str
    level: str | None
    value: float | int | None
    unit: str
    kpi: dict
    scope: dict
    trust: dict
    coverage: dict
    caveats: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    refusal: dict | None = None
    suppressed: dict | None = None
    comparison: dict | None = None
    explanation: str = ""

    @property
    def respondeu(self) -> bool:
        return self.refusal is None and self.suppressed is None

    def to_dict(self) -> dict:
        d = dict(level=self.level, value=self.value, unit=self.unit, kpi=self.kpi,
                 scope=self.scope, trust=self.trust, coverage=self.coverage,
                 caveats=self.caveats, trace_id=self.trace_id)
        if self.refusal:
            d["refusal"] = self.refusal
        if self.suppressed:
            d["suppressed"] = self.suppressed
        if self.comparison:
            d["comparison"] = self.comparison
        if self.explanation:
            d["explanation"] = self.explanation
        return d


def _kpi_bloco(kpi: Kpi) -> dict:
    return dict(id=kpi.kpi_id, version=kpi.version, status=kpi.status,
                owner=kpi.owner,
                certified_at=(kpi.doc.get("certification") or {}).get("approved_at"))


def nivel_efetivo(pedido: str, kpi: Kpi, trust: TrustResposta) -> tuple[str | None, str | None]:
    """O nivel em que a resposta pode operar, e o motivo se caiu.

    Regra 5 das cinco: a escada e limitada pelo trust. Em LIMITED, CONTEXT sai
    com ressalva e INTERPRETATION e bloqueado; em BLOCKED, nenhum nivel responde.
    """
    teto_kpi = kpi.teto_nivel
    if teto_kpi is None or trust.status in ("BLOCKED", "INDETERMINADO"):
        return None, ("trust do dado insuficiente" if teto_kpi
                      else f"KPI em {kpi.status}")
    teto = teto_kpi
    motivo = None
    if trust.status == "LIMITED" and ORDEM_NIVEL[teto] > ORDEM_NIVEL["CONTEXT"]:
        teto, motivo = "CONTEXT", "trust LIMITED bloqueia INTERPRETACAO"
    nivel = pedido if ORDEM_NIVEL[pedido] <= ORDEM_NIVEL[teto] else teto
    return nivel, motivo


def recusa(trace_id: str, q: SemanticQuery, r: Refusal, kpi: Kpi | None = None) -> Answer:
    return Answer(
        trace_id=trace_id, level=None, value=None, unit="",
        kpi=_kpi_bloco(kpi) if kpi else {"id": q.kpi},
        scope={"period": {"grain": q.period.grain, "from": q.period.inicio,
                          "to": q.period.fim},
               "dimensions": list(q.dimensions)},
        trust={"status": "BLOCKED" if r.classe == "KPI_BLOQUEADO" else "INDETERMINADO"},
        coverage={}, caveats=[], refusal=r.to_dict(),
        explanation=f"{r.mensagem} Para responder: {r.o_que_resolveria}")


def supressao(trace_id: str, q: SemanticQuery, kpi: Kpi, trust: TrustResposta,
              populacao: int, detalhe: dict | None = None) -> Answer:
    """Recorte abaixo do n minimo.

    Campo proprio, e a palavra e PRIVACIDADE. Nao e qualidade: "o grupo e pequeno
    demais para preservar anonimato" e diferente de "nao confio no dado", e
    misturar os dois faz a pessoa procurar o problema no lugar errado (ADR-0007).
    """
    return Answer(
        trace_id=trace_id, level=None, value=None, unit="",
        kpi=_kpi_bloco(kpi),
        scope={"period": {"grain": q.period.grain, "from": q.period.inicio,
                          "to": q.period.fim},
               "dimensions": list(q.dimensions)},
        trust=trust.to_dict(), coverage={},
        suppressed={**dict(motivo="PRIVACIDADE", minimum_n=kpi.minimum_n,
                           populacao=populacao,
                           nota="supressao por privacidade, nao por qualidade "
                                "do dado"),
                    **(detalhe or {})},
        explanation=(
            (f"nenhuma linha do recorte atinge o minimo de {kpi.minimum_n} pessoas "
             "deste KPI. A resposta e suprimida por privacidade, e nao por "
             "desconfianca no dado.")
            if detalhe else
            (f"o recorte tem {populacao} pessoas e o minimo deste KPI e "
             f"{kpi.minimum_n}. A resposta e suprimida por privacidade, "
             "e nao por desconfianca no dado.")))


def resposta(trace_id: str, q: SemanticQuery, kpi: Kpi, trust: TrustResposta,
             nivel: str, valor, unidade: str, linhas: list[dict],
             cobertura: dict, caveats: list[str],
             comparacao: dict | None = None) -> Answer:
    return Answer(
        trace_id=trace_id, level=nivel, value=valor, unit=unidade,
        kpi=_kpi_bloco(kpi),
        scope={"period": {"grain": q.period.grain, "from": q.period.inicio,
                          "to": q.period.fim},
               "dimensions": list(q.dimensions),
               "filters": [{"dimension": f.dimension, "in": list(f.valores)}
                           for f in q.filters]},
        trust=trust.to_dict(), coverage=cobertura, caveats=caveats,
        rows=linhas, comparison=comparacao)


def negacao_causal(kpi: Kpi) -> dict:
    """Negacao util (regra 4): diz o que seria necessario, nao apenas que nao da.

    CAUSALIDADE e negada por padrao desde o ADR-0015. O que a F7 acrescenta e
    que a negacao passa a nomear o desenho de estudo que responderia, com os
    campos que o contrato exige de um estudo registrado.
    """
    return dict(
        nivel="CAUSALITY", negado=True,
        motivo=("nao ha estudo registrado em `causal_studies` para este KPI; "
                "sem desenho de estudo, a serie mostra associacao e nao causa"),
        o_que_responderia=(
            "um estudo registrado com desenho (grupo de tratamento e de controle "
            "comparaveis), efeito estimado, intervalo de confianca e limitacoes "
            "declaradas, aprovado por People Analytics"),
        kpi=kpi.kpi_id)


def viola_regra_de_redacao(nivel: str, texto: str) -> list[str]:
    """Palavras causais num texto de nivel CONTEXT ou inferior (regra 2).

    Verificado e nao confiado: e a regra que a pratica mais viola, porque "caiu
    porque" sai da caneta sem passar pela cabeca.
    """
    if ORDEM_NIVEL.get(nivel, 0) >= ORDEM_NIVEL["CAUSALITY"]:
        return []
    baixo = texto.lower()
    return [p for p in PALAVRAS_CAUSAIS if re.search(rf"\b{re.escape(p)}\b", baixo)]
