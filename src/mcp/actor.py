"""Ator, escopos e a composição do teto de nível (MCP SPEC Parte VI; ADR-0033).

Autenticação corporativa fica para depois. O que existe aqui é o **contrato que
a autenticação vai preencher**, e a regra de composição, que precisa estar
fechada antes de haver autenticação — senão ela é decidida por acidente.

A regra, e ela só tem uma direção:

    response_level = min( nível pedido,
                          teto de evidência   (F7: status + regra + estudo),
                          teto do ator        (autorização) )

**Autorização só restringe.** Nenhuma configuração de ator destrava nível,
dimensão, KPI bloqueado, período fora de cobertura ou recorte abaixo do n
mínimo. Em particular, nenhum ator recebe INTERPRETATION de um KPI sem
`interpretation_rules`: evidência ausente não é permissão faltando.

Os quatro escopos separam por **natureza da informação**, e não por burocracia.
`kpi:read:definition` sem `kpi:read:value` é o perfil de quem audita a
metodologia sem ver resultado.

Nenhum escopo concede escrita, porque não há ferramenta de escrita. Um escopo
`kpi:write:*` não existe e não deve ser criado "para o futuro": escopo que
existe acaba sendo concedido.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from analytics.semantic.catalog import NIVEIS, ORDEM_NIVEL

from .envelope import (CEILING_ATOR, CEILING_EVIDENCIA, CEILING_GOVERNANCA,
                       CEILING_TRUST)

VALUE = "kpi:read:value"
DEFINITION = "kpi:read:definition"
TRUST = "kpi:read:trust"
LINEAGE = "kpi:read:lineage"

ESCOPOS = (VALUE, DEFINITION, TRUST, LINEAGE)

# Escopo exigido por ferramenta. É a segunda cerca, dentro de uma superfície que
# já é fechada (ADR-0031).
ESCOPO_DA_TOOL = {
    "get_kpi": VALUE,
    "compare_kpi": VALUE,
    "breakdown_kpi": VALUE,
    "get_kpi_definition": DEFINITION,
    "get_trust": TRUST,
    "get_lineage": LINEAGE,
}

TODOS = "ALL"


class ActorError(ValueError):
    pass


@dataclass(frozen=True)
class Actor:
    """Quem está perguntando.

    `id` é **referência opaca**: nunca e-mail, nome ou `employee_id`. O log liga
    a chamada a uma pessoa sem guardar quem ela é.
    """
    id: str
    type: str = "agent"                       # human | agent | service
    scopes: tuple[str, ...] = ESCOPOS
    max_response_level: str = "CAUSALITY"     # teto do ator; só restringe
    dimension_deny: tuple[str, ...] = ()
    kpi_allow: tuple[str, ...] | str = TODOS

    def __post_init__(self) -> None:
        if self.type not in ("human", "agent", "service"):
            raise ActorError(f"tipo de ator desconhecido: {self.type!r}")
        if self.max_response_level not in NIVEIS:
            raise ActorError(f"nivel desconhecido: {self.max_response_level!r}")
        for s in self.scopes:
            if s not in ESCOPOS:
                raise ActorError(f"escopo desconhecido: {s!r}")
            if ":write:" in s:               # defensivo, e a mensagem é o ponto
                raise ActorError("nao existe escopo de escrita: nao ha ferramenta "
                                 "de escrita a autorizar (ADR-0031)")

    # ------------------------------------------------------------- autorização
    def pode(self, tool: str) -> bool:
        escopo = ESCOPO_DA_TOOL.get(tool)
        return escopo is not None and escopo in self.scopes

    def pode_kpi(self, kpi_id: str) -> bool:
        return self.kpi_allow == TODOS or kpi_id in self.kpi_allow

    def dimensao_negada(self, dimensoes) -> str | None:
        for d in dimensoes or ():
            if d in self.dimension_deny:
                return d
        return None

    def ref(self) -> str:
        return self.id


# Ator padrão: todos os escopos, sem teto próprio. Existe para que a ausência de
# autenticação não seja, ela mesma, uma restrição silenciosa — o teto continua
# vindo inteiramente da evidência, como na F7.
ATOR_PADRAO = Actor(id="anon", type="service")


def teto_composto(pedido: str, teto_do_ator: str) -> str:
    """O menor entre o pedido e o teto do ator, antes de chamar a F7.

    Restringir o pedido ANTES evita calcular uma comparação que o ator não pode
    ver. A F7 aplica os tetos dela por cima, e o resultado é o mínimo dos três.
    """
    return pedido if ORDEM_NIVEL[pedido] <= ORDEM_NIVEL[teto_do_ator] else teto_do_ator


def origem_do_teto(pedido: str, concedido: str | None, teto_do_ator: str,
                   trust_status: str | None, kpi_status: str | None) -> str:
    """Qual dos três termos prendeu o nível.

    A ordem de atribuição importa: o ator só é apontado quando de fato foi ele
    que cortou, e nunca quando a evidência já cortava no mesmo ponto. Apontar o
    ator por engano manda a pessoa pedir permissão para um problema de dado.
    """
    if concedido is None:
        return (CEILING_GOVERNANCA if kpi_status in ("BLOCKED", "DRAFT")
                else CEILING_TRUST)
    if ORDEM_NIVEL[concedido] == ORDEM_NIVEL[pedido]:
        return CEILING_EVIDENCIA          # nada cortou: o pedido coube
    if (ORDEM_NIVEL[teto_do_ator] == ORDEM_NIVEL[concedido]
            and ORDEM_NIVEL[teto_do_ator] < ORDEM_NIVEL[pedido]):
        return CEILING_ATOR
    if trust_status == "LIMITED":
        return CEILING_TRUST
    if kpi_status in ("DECLARED", "DEPRECATED"):
        return CEILING_GOVERNANCA
    return CEILING_EVIDENCIA
