"""Adapter do provedor (SPEC Parte XII; P-03 como candidato de avaliação).

Fino de propósito. Ele faz uma coisa: manda mensagens e devolve texto, tokens,
id de requisição e latência. Nenhuma regra do PeopleLens mora aqui, e nenhuma
decisão depende do que o provedor devolveu além de "chegou" ou "não chegou".

Trocar de provedor é escrever outro `Cliente`. É por isso que o protocolo tem
um método só: qualquer coisa a mais aqui viraria dependência de fornecedor
espalhada pelo resto.

**Credencial nunca passa por este módulo em texto.** A chave é lida do ambiente
pelo SDK e nunca é impressa, registrada, devolvida ou embutida em mensagem de
erro. Se ela não existir, isso é falha estrutural declarada, não um problema a
contornar.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Protocol

from .llm_schema import SCHEMA_VERSION, json_schema

PROVEDOR = "openai"

# Identificador do modelo. **PENDENTE DE CONFIRMAÇÃO** contra o provedor antes
# da primeira chamada real: P-03 autorizou o GPT-5.6 Luna como candidato de
# avaliação, e a grafia exata do id de API não foi verificada em fonte oficial.
# Configurável por ambiente justamente para que confirmar não exija editar código.
MODELO_PADRAO = os.environ.get("PEOPLELENS_LLM_MODEL", "gpt-5.6-luna")

# A SPEC, seção 15, fixou `temperature = 0` por reprodutibilidade do `Intent`.
# **O parâmetro não é enviado**, porque o modelo o recusa:
#
#   Unsupported value: 'temperature' does not support 0.0 with this model.
#   Only the default (1) value is supported.
#
# Consequência, e ela não é de implementação: a reprodutibilidade do `Intent`
# passa a depender do padrão do provedor, e AA-11 continua verificável pelo
# plano e pela sequência de chamadas, que é o que aquele critério de fato exige
# (ADR-0034). Enviar `temperature=1` explicitamente seria dizer que escolhemos
# o valor, quando não escolhemos: o provedor é que não dá alternativa.
TIMEOUT_S = 10.0

VARIAVEL_DA_CHAVE = "OPENAI_API_KEY"

# A API exige `^[a-zA-Z0-9_-]+$` no nome do structured output. `SCHEMA_VERSION`
# e identificador interno do contrato ("intent/1.0"), e nao muda por causa
# disso: quem se adapta ao provedor e o adapter, que existe para isso.
_CARACTERE_INVALIDO = re.compile(r"[^a-zA-Z0-9_-]")


def nome_do_schema(versao: str = SCHEMA_VERSION) -> str:
    """Nome tecnico do schema, na forma que a API aceita.

    "intent/1.0" -> "intent_1_0". A barra e o ponto sao ambos invalidos, e
    trocar so a barra deixava o ponto passar: era o defeito.
    """
    return _CARACTERE_INVALIDO.sub("_", versao)


class SemCredencial(RuntimeError):
    """Não há credencial no ambiente. Falha estrutural, nunca contornada."""


class FalhaDoProvedor(RuntimeError):
    """Erro de transporte, de API ou timeout. O motivo entra sem o corpo."""


@dataclass
class RespostaDoModelo:
    texto: str
    tokens_entrada: int | None = None
    tokens_saida: int | None = None
    request_id: str | None = None
    latencia_ms: int = 0


class Cliente(Protocol):
    """Um método. Mais do que isto espalharia o fornecedor pelo resto."""

    def completar(self, mensagens: list[dict]) -> RespostaDoModelo:  # pragma: no cover
        ...

    @property
    def modelo(self) -> str:                                          # pragma: no cover
        ...

    @property
    def provedor(self) -> str:                                        # pragma: no cover
        ...


class ClienteOpenAI:
    """Adapter do SDK oficial, com structured output estrito.

    O schema vai para o provedor com `strict: true`, e isso é **conveniência**:
    a validação local roda de qualquer jeito (ADR-0035, decisão 2). A garantia
    do fornecedor pode mudar de versão, degradar sob carga, ou simplesmente ser
    de outro fornecedor amanhã.
    """

    def __init__(self, modelo: str | None = None, timeout_s: float = TIMEOUT_S):
        self._modelo = modelo or MODELO_PADRAO
        self._timeout = timeout_s
        self._sdk = None

    @property
    def modelo(self) -> str:
        return self._modelo

    @property
    def provedor(self) -> str:
        return PROVEDOR

    def _cliente(self):
        """Import tardio: a suíte roda sem o SDK instalado."""
        if self._sdk is not None:
            return self._sdk
        if not os.environ.get(VARIAVEL_DA_CHAVE):
            raise SemCredencial(f"{VARIAVEL_DA_CHAVE} ausente no ambiente")
        try:
            from openai import OpenAI
        except ImportError as e:                       # pragma: no cover
            raise FalhaDoProvedor("SDK do provedor não instalado") from e
        # A chave é lida pelo SDK a partir do ambiente. Não passa por aqui.
        self._sdk = OpenAI(timeout=self._timeout)
        return self._sdk

    def completar(self, mensagens: list[dict]) -> RespostaDoModelo:
        cliente = self._cliente()
        t0 = time.perf_counter()
        try:
            r = cliente.chat.completions.create(
                model=self._modelo,
                messages=mensagens,
                timeout=self._timeout,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": nome_do_schema(),
                        "strict": True,
                        "schema": json_schema(),
                    },
                },
            )
        except Exception as e:
            # O tipo do erro entra; o corpo não, porque pode devolver o prompt.
            raise FalhaDoProvedor(type(e).__name__) from None
        dur = int((time.perf_counter() - t0) * 1000)

        uso = getattr(r, "usage", None)
        return RespostaDoModelo(
            texto=(r.choices[0].message.content or ""),
            tokens_entrada=getattr(uso, "prompt_tokens", None),
            tokens_saida=getattr(uso, "completion_tokens", None),
            request_id=getattr(r, "id", None),
            latencia_ms=dur,
        )


# --------------------------------------------------------------------------- #
# Cliente de teste
# --------------------------------------------------------------------------- #
class ClienteDeTeste:
    """Devolve respostas preparadas, na ordem. Para a suíte determinística.

    Existe para que os testes do interpretador não dependam de rede, de chave e
    de nenhum comportamento de fornecedor. Cada item de `respostas` é uma
    string (o que o modelo "devolveu"), um `dict` (serializado para JSON) ou uma
    exceção (levantada).
    """

    def __init__(self, respostas, modelo: str = "teste", provedor: str = "teste"):
        self._respostas = list(respostas)
        self._modelo = modelo
        self._provedor = provedor
        self.chamadas: list[list[dict]] = []

    @property
    def modelo(self) -> str:
        return self._modelo

    @property
    def provedor(self) -> str:
        return self._provedor

    def completar(self, mensagens: list[dict]) -> RespostaDoModelo:
        self.chamadas.append(mensagens)
        if not self._respostas:
            raise FalhaDoProvedor("sem resposta preparada")
        r = self._respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        texto = r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
        return RespostaDoModelo(texto=texto, tokens_entrada=0, tokens_saida=0,
                                request_id="teste", latencia_ms=0)
