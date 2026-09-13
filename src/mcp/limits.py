"""Limites da fronteira (MCP SPEC v0.1, Parte VIII).

Uma regra acima de todas: **nenhuma truncagem silenciosa**. Todo limite atingido
vira recusa explicada, dizendo o que estreitar. Devolver as 50 primeiras linhas
de 300 e chamar isso de resposta é o mesmo erro que responder zero para um
período sem carga — um número errado com cara de certo.

A exceção é o `top_n` pedido pelo chamador: aí o recorte é escolha dele, está
declarado na resposta, e não é silêncio.
"""
from __future__ import annotations

import re

MAX_PERIODOS = 24        # dois anos cabem; uma década é breakdown
MAX_DIMENSOES = 2        # três dimensões pulverizam o recorte abaixo do n mínimo
MAX_LINHAS_RETORNADAS = 50
MAX_LINHAS_AVALIADAS = 200
TIMEOUT_S = 30
MAX_PAYLOAD_BYTES = 256 * 1024

LIMITES = {
    "max_periodos": MAX_PERIODOS,
    "max_dimensoes": MAX_DIMENSOES,
    "max_linhas_retornadas": MAX_LINHAS_RETORNADAS,
    "max_linhas_avaliadas": MAX_LINHAS_AVALIADAS,
    "timeout_s": TIMEOUT_S,
    "max_payload_bytes": MAX_PAYLOAD_BYTES,
}

_MES = re.compile(r"^(\d{4})-(\d{2})$")
_TRI = re.compile(r"^(\d{4})-Q([1-4])$")
_ANO = re.compile(r"^(\d{4})$")
_CICLO = re.compile(r"^(\d{4})(?:-H([12]))?$")


def contar_periodos(grain: str, inicio: str, fim: str) -> int | None:
    """Quantos períodos a janela cobre. `None` quando a forma não é reconhecível.

    Forma inválida não é problema deste módulo: a validação da Semantic Layer
    devolve `GRAIN_INCOMPATIVEL` com a mensagem certa, e antecipar isso aqui
    produziria duas mensagens para o mesmo defeito.
    """
    if inicio == fim:
        return 1
    if grain == "mes":
        a, b = _MES.match(inicio), _MES.match(fim)
        if not (a and b):
            return None
        return ((int(b.group(1)) - int(a.group(1))) * 12
                + (int(b.group(2)) - int(a.group(2))) + 1)
    if grain == "trimestre":
        a, b = _TRI.match(inicio), _TRI.match(fim)
        if not (a and b):
            return None
        return ((int(b.group(1)) - int(a.group(1))) * 4
                + (int(b.group(2)) - int(a.group(2))) + 1)
    if grain in ("ano", "ciclo"):
        padrao = _ANO if grain == "ano" else _CICLO
        a, b = padrao.match(inicio), padrao.match(fim)
        if not (a and b):
            return None
        n = int(b.group(1)) - int(a.group(1)) + 1
        return n * 2 if grain == "ciclo" else n
    return None


def excede_periodos(grain: str, inicio: str, fim: str) -> int | None:
    """Quantidade de períodos, quando ela passa do limite. `None` quando cabe."""
    n = contar_periodos(grain, inicio, fim)
    if n is not None and n > MAX_PERIODOS:
        return n
    return None


def aplicados(**extra) -> dict:
    """O que a chamada aplicou, para a resposta declarar."""
    return {**LIMITES, **extra}
