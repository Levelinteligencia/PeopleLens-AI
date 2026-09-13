"""LLM Interpreter v0.1: o modelo no passo UNDERSTAND, e nada além disso.

    LLM -> Intent -> validação -> RESOLVE -> PLAN -> MCP

O modelo termina **antes** da validação. Depois que ele devolve o `Intent`,
nenhuma etapa posterior volta a perguntar: não há segunda chamada para
desempatar, para confirmar, para melhorar. Se o `Intent` não serve, quem decide
é o `RESOLVE`, e a pessoa recebe a pergunta de volta.

Este módulo implementa o mesmo `Interpreter` que o `RuleInterpreter`, e devolve
o mesmo `Intent`. É isso que torna a substituição barata e a comparação honesta:
os dois são testados pela mesma suíte, contra o mesmo contrato.

Dois gatilhos de fallback, e só dois (SPEC seção 17):

    falha estrutural  -> RuleInterpreter
    ORCAMENTO_ESGOTADO -> RuleInterpreter

Nenhum dos dois é "o `Intent` ficou estranho". `Intent` válido vale, ainda que
o `RuleInterpreter` fosse devolver outro, e ainda que o resultado desagrade.
Retentar até o modelo dizer algo aceitável é treinar a resposta pela tentativa.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from .interpreter import Interpreter, RuleInterpreter
from .intent import Intent
from . import llm_client as cli
from . import llm_prompt, llm_schema
from .llm_schema import ErroDeSchema

INTERPRETER_VERSION = "llm/0.1.0"

LLM = "LLM"
RULE_FALLBACK = "RULE_FALLBACK"

# Motivos de falha, fechados. `llm_schema.MOTIVOS` cobre os estruturais.
TIMEOUT = "TIMEOUT"
FALHA_DO_PROVEDOR = "FALHA_DO_PROVEDOR"
SEM_CREDENCIAL = "SEM_CREDENCIAL"
ORCAMENTO_ESGOTADO = "ORCAMENTO_ESGOTADO"
MOTIVOS = (*llm_schema.MOTIVOS, TIMEOUT, FALHA_DO_PROVEDOR, SEM_CREDENCIAL,
           ORCAMENTO_ESGOTADO)

# Valor de DESENVOLVIMENTO. **Não é decisão de produto** (P-05 deixou o número
# como configuração operacional pendente de calibração). Só vale quando nenhum
# orçamento foi configurado, e o registro diz que a origem foi DEV.
ORCAMENTO_DEV = 50


@dataclass
class Orcamento:
    """Teto de uso do LLM por período, com a contagem do período corrente.

    O período é o dia, porque é a menor janela em que "quanto se gastou" é uma
    pergunta respondível sem infraestrutura nova. Atingir o teto **não** é erro:
    é uma condição prevista que troca de interpretador e declara isso.
    """
    teto: int | None = None
    origem: str = "DEV"          # DEV | CONFIGURADO
    _dia: str = ""
    _usadas: int = 0

    @classmethod
    def de(cls, limites, teto: int | None = None) -> "Orcamento":
        if teto is not None:
            return cls(teto=teto, origem="CONFIGURADO")
        configurado = getattr(limites, "orcamento_llm_por_periodo", None)
        if configurado is not None:
            return cls(teto=int(configurado), origem="CONFIGURADO")
        return cls(teto=ORCAMENTO_DEV, origem="DEV")

    def _virar_o_dia(self) -> None:
        hoje = date.today().isoformat()
        if hoje != self._dia:
            self._dia, self._usadas = hoje, 0

    @property
    def esgotado(self) -> bool:
        self._virar_o_dia()
        return self.teto is not None and self._usadas >= self.teto

    def consumir(self) -> None:
        self._virar_o_dia()
        self._usadas += 1

    def to_dict(self) -> dict:
        self._virar_o_dia()
        return {"teto": self.teto, "origem": self.origem, "usadas": self._usadas}


@dataclass
class Registro:
    """Metadados de uma interpretação (SPEC Parte XIII, seção 18).

    O que **não** entra aqui, e a ausência é a parte importante: a pergunta, o
    texto devolvido pelo modelo, valores de filtro, credencial. `schema_erros`
    guarda qual regra foi violada e onde, nunca o conteúdo que a violou.
    """
    interpreter_used: str = LLM
    interpreter_version: str = INTERPRETER_VERSION
    provider: str | None = None
    model: str | None = None
    schema_version: str = llm_schema.SCHEMA_VERSION
    request_id: str | None = None
    validation: str = "OK"                  # OK | REJEITADO | NAO_EXECUTADA
    schema_erros: list[str] = field(default_factory=list)
    retries: int = 0
    fallback: bool = False
    fallback_reason: str | None = None
    tokens_entrada: int | None = None
    tokens_saida: int | None = None
    latencia_ms: int = 0
    periodo_relativo: str | None = None
    bases: list[str] = field(default_factory=list)
    orcamento: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "interpreter_used": self.interpreter_used,
            "interpreter_version": self.interpreter_version,
            "provider": self.provider, "model": self.model,
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "validation": self.validation,
            "schema_erros": list(self.schema_erros),
            "retries": self.retries,
            "fallback": self.fallback,
            "fallback_reason": self.fallback_reason,
            "tokens_entrada": self.tokens_entrada,
            "tokens_saida": self.tokens_saida,
            "latencia_ms": self.latencia_ms,
            "periodo_relativo": self.periodo_relativo,
            "bases": list(self.bases),
            "orcamento": dict(self.orcamento),
        }


class LLMInterpreter:
    """Implementação do `Interpreter` com um modelo de linguagem.

    O `RuleInterpreter` continua existindo e é o fallback. Ele não compete com
    o modelo: responde quando o modelo falha estruturalmente ou quando o
    orçamento acabou.
    """

    def __init__(self, cliente: cli.Cliente | None = None,
                 fallback: Interpreter | None = None,
                 limites=None, orcamento: Orcamento | None = None,
                 max_retries: int = 1):
        self.cliente = cliente or cli.ClienteOpenAI()
        self.fallback = fallback or RuleInterpreter()
        self.orcamento = orcamento or Orcamento.de(limites)
        self.max_retries = max_retries
        self.registro = Registro()

    # ------------------------------------------------------------------ público
    def understand(self, pergunta: str, contexto) -> Intent:
        self.registro = Registro(provider=self.cliente.provedor,
                                 model=self.cliente.modelo,
                                 orcamento=self.orcamento.to_dict())

        if self.orcamento.esgotado:
            return self._cair_para_regra(pergunta, contexto, ORCAMENTO_ESGOTADO,
                                         validation="NAO_EXECUTADA")

        mensagens = llm_prompt.mensagens(contexto, pergunta)
        motivo = None

        for tentativa in range(self.max_retries + 1):
            self.registro.retries = tentativa
            try:
                self.orcamento.consumir()
                resposta = self.cliente.completar(mensagens)
            except cli.SemCredencial:
                # Sem credencial não há o que retentar, e contornar está proibido.
                return self._cair_para_regra(pergunta, contexto, SEM_CREDENCIAL,
                                             validation="NAO_EXECUTADA")
            except cli.FalhaDoProvedor as e:
                motivo = TIMEOUT if "timeout" in str(e).lower() else FALHA_DO_PROVEDOR
                continue

            self.registro.request_id = resposta.request_id
            self.registro.tokens_entrada = resposta.tokens_entrada
            self.registro.tokens_saida = resposta.tokens_saida
            self.registro.latencia_ms += resposta.latencia_ms

            try:
                payload = self._payload(resposta.texto)
                llm_schema.validar(payload)
            except ErroDeSchema as e:
                motivo = e.motivo
                self.registro.schema_erros.append(
                    f"{e.motivo}:{e.onde}" if e.onde else e.motivo)
                continue

            # Sucesso. `Intent` válido vale, e não se retenta por conteúdo.
            self.registro.validation = "OK"
            self.registro.periodo_relativo = llm_schema.relativo_de(payload)
            self.registro.bases = llm_schema.bases_de(payload)
            self.registro.interpreter_used = LLM
            return llm_schema.para_intent(payload)

        return self._cair_para_regra(pergunta, contexto, motivo or FALHA_DO_PROVEDOR,
                                     validation="REJEITADO")

    # ------------------------------------------------------------------ privado
    @staticmethod
    def _payload(texto: str) -> dict:
        """Texto do modelo -> objeto. Sem tolerância e sem conserto.

        Não se tenta extrair JSON de dentro de texto livre, não se remove cerca
        de markdown, não se corta prefixo. Interpretar texto livre como se fosse
        estrutura é justamente a porta que o structured output existe para
        fechar: o que entra por ela não tem contrato nenhum.
        """
        try:
            return json.loads(texto)
        except (ValueError, TypeError):
            raise ErroDeSchema(llm_schema.JSON_INVALIDO) from None

    def _cair_para_regra(self, pergunta: str, contexto, motivo: str,
                         validation: str) -> Intent:
        """Fallback declarado, nunca silencioso (D-05).

        O `RuleInterpreter` produz o mesmo contrato de `Intent`, e o caminho
        depois daqui é idêntico: mesma validação de vocabulário no `RESOLVE`,
        mesmas políticas, mesmos tetos. O fallback **não** é modo degradado com
        permissões próprias.
        """
        self.registro.interpreter_used = RULE_FALLBACK
        self.registro.fallback = True
        self.registro.fallback_reason = motivo
        self.registro.validation = validation
        return self.fallback.understand(pergunta, contexto)
