"""Envelope comum das seis ferramentas (MCP SPEC v0.1, Parte IV; ADR-0032).

Toda tool devolve a mesma forma. O agente aprende uma, não seis.

A decisão que este módulo faz valer é a do ADR-0032: **recusa é resultado
bem-sucedido do transporte, não erro de protocolo**. Um resultado marcado como
erro chega ao modelo como "a ferramenta falhou", e o comportamento induzido é
sempre tentar de novo. Sobre a supressão por privacidade isso é ativamente
perigoso: repetir consultas estreitando o recorte até uma passar é
reidentificação por tentativa, e a proteção vira o gatilho.

Quatro resultados, e eles não se confundem:

    ANSWER      há valor
    REFUSAL     pergunta válida, resposta não sustentável   -> não é erro
    SUPPRESSED  há resposta; não sai por PRIVACIDADE        -> não é erro
    ERROR       chamada malformada, ou ator sem escopo      -> É erro, e só ele
"""
from __future__ import annotations

from dataclasses import dataclass, field

ANSWER = "ANSWER"
REFUSAL = "REFUSAL"
SUPPRESSED = "SUPPRESSED"
ERROR = "ERROR"

OUTCOMES = (ANSWER, REFUSAL, SUPPRESSED, ERROR)

# De onde veio o teto do nível de resposta. Sem este campo, um agente que recebe
# FACT quando pediu CONTEXT não sabe se deve pedir certificação a People
# Analytics, correção de dado a engenharia, uma regra assinada, ou permissão ao
# administrador. Quatro ações, quatro pessoas (ADR-0033).
CEILING_EVIDENCIA = "EVIDENCIA"
CEILING_GOVERNANCA = "GOVERNANCA"
CEILING_ATOR = "ATOR"
CEILING_TRUST = "TRUST"

# Classes que a fronteira acrescenta às da Semantic Layer. As da F7 atravessam
# verbatim, sem tradução: uma tabela de correspondência entre dois vocabulários
# para o mesmo conceito é o defeito que o `movement_type` já mostrou.
TRUST_INSUFICIENTE = "TRUST_INSUFICIENTE"
LIMITE_DE_RESULTADO_EXCEDIDO = "LIMITE_DE_RESULTADO_EXCEDIDO"
TRACE_INEXISTENTE = "TRACE_INEXISTENTE"
LINEAGE_INDISPONIVEL = "LINEAGE_INDISPONIVEL"

PARAMETRO_INVALIDO = "PARAMETRO_INVALIDO"
ESCOPO_INSUFICIENTE = "ESCOPO_INSUFICIENTE"
CAPACIDADE_INEXISTENTE = "CAPACIDADE_INEXISTENTE"

# Só estas três são erro de protocolo, e todas descrevem defeito de quem chamou.
CLASSES_DE_ERRO = (PARAMETRO_INVALIDO, ESCOPO_INSUFICIENTE, CAPACIDADE_INEXISTENTE)

CLASSES_DA_FRONTEIRA = (TRUST_INSUFICIENTE, LIMITE_DE_RESULTADO_EXCEDIDO,
                        TRACE_INEXISTENTE, LINEAGE_INDISPONIVEL, *CLASSES_DE_ERRO)


class EnvelopeError(RuntimeError):
    pass


@dataclass
class Envelope:
    tool: str
    outcome: str
    request_id: str
    trace_id: str
    kpi: dict | None = None
    data: dict | None = None
    trust: dict | None = None
    response_level: dict | None = None
    refusal: dict | None = None
    suppressed: dict | None = None
    limits: dict = field(default_factory=dict)
    caveats: list[str] = field(default_factory=list)
    lineage_ref: dict | None = None

    @property
    def ok(self) -> bool:
        return self.outcome == ANSWER

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise EnvelopeError(f"outcome desconhecido: {self.outcome!r}")
        # Regra do envelope (Parte IV): `data` e `refusal` nunca coexistem, e
        # pelo menos um dos quatro resultados está sempre preenchido.
        if self.data is not None and self.refusal is not None:
            raise EnvelopeError("`data` e `refusal` nao podem coexistir")
        if self.outcome == ANSWER and self.data is None:
            raise EnvelopeError("ANSWER exige `data`")
        if self.outcome in (REFUSAL, ERROR) and self.refusal is None:
            raise EnvelopeError(f"{self.outcome} exige `refusal`")
        if self.outcome == SUPPRESSED and self.suppressed is None:
            raise EnvelopeError("SUPPRESSED exige `suppressed`")
        if not self.trace_id:
            raise EnvelopeError("toda resposta carrega trace_id, inclusive recusa")

    def to_dict(self) -> dict:
        d = {
            "ok": self.ok,
            "outcome": self.outcome,
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "tool": self.tool,
            "data": self.data,
            "trust": self.trust,
            "refusal": self.refusal,
            "suppressed": self.suppressed,
            "limits": self.limits,
            "caveats": list(self.caveats),
        }
        if self.kpi is not None:
            d["kpi"] = self.kpi
        if self.response_level is not None:
            d["response_level"] = self.response_level
        if self.lineage_ref is not None:
            d["lineage_ref"] = self.lineage_ref
        return d


def _refusal(classe: str, mensagem: str, o_que_resolveria: str,
             detalhe: dict | None = None) -> dict:
    """Toda recusa preenche os três campos. `o_que_resolveria` não é opcional:
    recusa que não diz o caminho deixa o agente diante de porta fechada, e
    agente diante de porta fechada inventa."""
    return {"classe": classe, "mensagem": mensagem,
            "o_que_resolveria": o_que_resolveria, "detalhe": detalhe or {}}


def answer(tool: str, request_id: str, trace_id: str, data: dict,
           kpi: dict | None = None, trust: dict | None = None,
           response_level: dict | None = None, limits: dict | None = None,
           caveats: list[str] | None = None) -> Envelope:
    return Envelope(tool=tool, outcome=ANSWER, request_id=request_id,
                    trace_id=trace_id, data=data, kpi=kpi, trust=trust,
                    response_level=response_level, limits=limits or {},
                    caveats=list(caveats or []),
                    lineage_ref={"tool": "get_lineage", "trace_id": trace_id})


def refusal(tool: str, request_id: str, trace_id: str, classe: str,
            mensagem: str, o_que_resolveria: str, detalhe: dict | None = None,
            kpi: dict | None = None, trust: dict | None = None,
            response_level: dict | None = None,
            limits: dict | None = None) -> Envelope:
    """Recusa governada. `outcome` é REFUSAL — nunca ERROR."""
    if classe in CLASSES_DE_ERRO:
        raise EnvelopeError(
            f"{classe} e defeito do chamador e deve usar `error()`, nao `refusal()`")
    return Envelope(tool=tool, outcome=REFUSAL, request_id=request_id,
                    trace_id=trace_id,
                    refusal=_refusal(classe, mensagem, o_que_resolveria, detalhe),
                    kpi=kpi, trust=trust, response_level=response_level,
                    limits=limits or {},
                    lineage_ref={"tool": "get_lineage", "trace_id": trace_id})


def suppressed(tool: str, request_id: str, trace_id: str, detalhe: dict,
               kpi: dict | None = None, trust: dict | None = None,
               limits: dict | None = None,
               caveats: list[str] | None = None) -> Envelope:
    """Supressão por privacidade. Categoria própria, e a palavra é PRIVACIDADE.

    Não é recusa e não é erro: um agente que lê "erro" tenta outro recorte, e
    é assim que se reidentifica alguém por tentativa.
    """
    return Envelope(tool=tool, outcome=SUPPRESSED, request_id=request_id,
                    trace_id=trace_id, suppressed=detalhe, kpi=kpi, trust=trust,
                    limits=limits or {}, caveats=list(caveats or []),
                    lineage_ref={"tool": "get_lineage", "trace_id": trace_id})


def error(tool: str, request_id: str, trace_id: str, classe: str,
          mensagem: str, o_que_resolveria: str,
          detalhe: dict | None = None) -> Envelope:
    """Defeito do chamador: parâmetro inválido, escopo ausente, tool inexistente.

    O único resultado que merece ser tratado como falha. Tentar de novo igual
    não adianta; corrigir a chamada, sim.
    """
    if classe not in CLASSES_DE_ERRO:
        raise EnvelopeError(f"{classe} nao e classe de erro de chamador")
    return Envelope(tool=tool, outcome=ERROR, request_id=request_id,
                    trace_id=trace_id,
                    refusal=_refusal(classe, mensagem, o_que_resolveria, detalhe))
