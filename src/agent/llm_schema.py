"""O contrato de saída do LLM, e sua validação local (SPEC Partes III e XI).

**Não existe um segundo schema.** O conjunto de campos é derivado do `Intent`
por `dataclasses.fields`, e um teste confere a igualdade. Se alguém acrescentar
um campo ao `Intent` sem passar por aqui, o teste quebra — que é o
comportamento desejado, e não um incômodo.

Os enums também não são redigitados: `question_type` vem de `intent.TIPOS`,
`requested_level` de `analytics.semantic.catalog.NIVEIS`, `grain` de
`context.PADRAO_PERIODO`, `dimension` de `interpreter.DIMENSOES_DE_FILTRO`.
Redigitar qualquer um deles criaria duas verdades sobre a mesma coisa.

A regra do ADR-0035, decisão 2, em código: **campo desconhecido rejeita o
`Intent` inteiro.** Ignorar o campo extra é a porta por onde entra a capacidade
que ninguém aprovou, porque basta que alguém, depois, comece a lê-lo.
"""
from __future__ import annotations

from dataclasses import fields as campos_de

from analytics.semantic.catalog import NIVEIS

from .context import PADRAO_PERIODO
from .intent import TIPOS, Ambiguity, Intent
from .interpreter import DIMENSOES_DE_FILTRO

SCHEMA_VERSION = "intent/1.0"

# Derivado, nunca redigitado.
CAMPOS_DO_INTENT: tuple[str, ...] = tuple(f.name for f in campos_de(Intent))
CAMPOS_DA_SAIDA: tuple[str, ...] = ("schema_version", *CAMPOS_DO_INTENT)

# Base do termo. Três estados, e não existe um quarto (SPEC, seção 6).
EXATO = "EXATO"
SINONIMO_DECLARADO = "SINONIMO_DECLARADO"
NAO_RESOLVIDO = "NAO_RESOLVIDO"
BASES = (EXATO, SINONIMO_DECLARADO, NAO_RESOLVIDO)

# Bases de comparação declaradas em `config/semantic/vocabulary.yaml`.
# Um teste confere que esta tupla e o arquivo não divergiram.
COMPARACOES = ("periodo_anterior", "mesmo_periodo_ano_anterior",
               "media_da_populacao")

PREMISSAS = ("AUMENTO", "QUEDA")
GRAINS = tuple(PADRAO_PERIODO)

# Motivos de rejeição. Fechado: o registro não aceita motivo inventado.
JSON_INVALIDO = "JSON_INVALIDO"
VERSAO_DESCONHECIDA = "VERSAO_DESCONHECIDA"
CAMPO_DESCONHECIDO = "CAMPO_DESCONHECIDO"
CAMPO_OBRIGATORIO_AUSENTE = "CAMPO_OBRIGATORIO_AUSENTE"
TIPO_INVALIDO = "TIPO_INVALIDO"
ENUM_INVALIDO = "ENUM_INVALIDO"
MOTIVOS = (JSON_INVALIDO, VERSAO_DESCONHECIDA, CAMPO_DESCONHECIDO,
           CAMPO_OBRIGATORIO_AUSENTE, TIPO_INVALIDO, ENUM_INVALIDO)


class ErroDeSchema(Exception):
    """Falha estrutural. Carrega o motivo, e **nunca** o texto que a causou.

    O texto que violou o schema pode conter um trecho da pergunta, e a SPEC já
    decidiu que o log guarda qual regra foi violada, não o conteúdo que a
    violou (Parte XIII).
    """

    def __init__(self, motivo: str, onde: str = ""):
        self.motivo = motivo
        self.onde = onde
        super().__init__(f"{motivo}{f' em {onde}' if onde else ''}")


# --------------------------------------------------------------------------- #
# O schema que vai para o provedor
# --------------------------------------------------------------------------- #
def json_schema() -> dict:
    """JSON Schema do `Intent`, para o structured output do provedor.

    Fechado em todo nível: `additionalProperties: false` em cada objeto. A
    validação local roda de qualquer jeito (ADR-0035, decisão 2); isto aqui é
    conveniência do provedor, não a fronteira.

    Três regras do modo estrito, e nenhuma delas é opcional para o provedor:

    1. **todo esquema de propriedade declara `type`.** `enum` e `const` sozinhos
       são rejeitados, com "schema must have a 'type' key";
    2. **toda chave de `properties` aparece em `required`.** Campo opcional se
       expressa pelo tipo nulável, nunca pela ausência em `required`;
    3. **`additionalProperties: false` em cada objeto.**

    Nada disso muda o contrato: os campos, os enums e a semântica de nulo são
    os mesmos, e a validação local continua sendo a fronteira.
    """
    termo = {
        "type": "object",
        "additionalProperties": False,
        "required": ["literal", "governado", "base"],
        "properties": {
            "literal": {"type": "string"},
            "governado": {"type": ["string", "null"]},
            "base": {"type": "string", "enum": list(BASES)},
        },
    }
    filtro = {
        "type": "object",
        "additionalProperties": False,
        "required": ["dimension", "terms"],
        "properties": {
            "dimension": {"type": "string", "enum": list(DIMENSOES_DE_FILTRO)},
            "terms": {"type": "array", "items": termo},
        },
    }
    periodo = {
        "type": ["object", "null"],
        "additionalProperties": False,
        # Todas as chaves entram em `required`: o modo estrito do provedor não
        # aceita propriedade opcional, e a opcionalidade se expressa pelo tipo
        # nulável. A semântica não muda — `from`, `to` e `relativo` continuam
        # podendo vir vazios — e a validação local segue aceitando as duas
        # formas, com a chave ausente ou presente e nula.
        "required": ["grain", "from", "to", "relativo"],
        "properties": {
            "grain": {"type": "string", "enum": list(GRAINS)},
            "from": {"type": ["string", "null"]},
            "to": {"type": ["string", "null"]},
            # Termo relativo é **marcado**, nunca resolvido pelo LLM (P-02).
            "relativo": {"type": ["string", "null"]},
        },
    }
    ambiguidade = {
        "type": "object",
        "additionalProperties": False,
        "required": ["campo", "motivo", "opcoes"],
        "properties": {
            "campo": {"type": "string"},
            "motivo": {"type": "string"},
            "opcoes": {"type": "array", "items": {"type": "string"}},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(CAMPOS_DA_SAIDA),
        "properties": {
            # `const` não é aceito pelo modo estrito: o valor fixo se expressa
            # como enum de um elemento, com o tipo declarado.
            "schema_version": {"type": "string", "enum": [SCHEMA_VERSION]},
            "question_type": {"type": "string", "enum": list(TIPOS)},
            "kpi_candidates": {"type": "array", "items": {"type": "string"}},
            "period": periodo,
            "filters": {"type": "array", "items": filtro},
            "dimensions": {"type": "array",
                           "items": {"type": "string",
                                     "enum": list(DIMENSOES_DE_FILTRO)}},
            "requested_level": {"type": "string", "enum": list(NIVEIS)},
            "compare_to": {"type": ["string", "null"], "enum": [*COMPARACOES, None]},
            "ambiguity": {"type": "array", "items": ambiguidade},
            "premissa": {"type": ["string", "null"], "enum": [*PREMISSAS, None]},
            "referencia_anterior": {"type": "boolean"},
        },
    }


# --------------------------------------------------------------------------- #
# Validação local — sempre, mesmo com schema do provedor
# --------------------------------------------------------------------------- #
def validar(payload) -> dict:
    """Valida e devolve o payload. Levanta `ErroDeSchema` na primeira violação.

    Estrito de propósito: sem coerção de tipo, sem normalização de caixa, sem
    conserto. Reparar é reinterpretar, e o projeto recusa correção silenciosa
    desde a F3.
    """
    if not isinstance(payload, dict):
        raise ErroDeSchema(TIPO_INVALIDO, "raiz")

    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ErroDeSchema(VERSAO_DESCONHECIDA, "schema_version")

    extras = set(payload) - set(CAMPOS_DA_SAIDA)
    if extras:
        # O nome do campo extra entra; o valor dele, nunca.
        raise ErroDeSchema(CAMPO_DESCONHECIDO, ",".join(sorted(extras)))

    faltando = set(CAMPOS_DA_SAIDA) - set(payload)
    if faltando:
        raise ErroDeSchema(CAMPO_OBRIGATORIO_AUSENTE, ",".join(sorted(faltando)))

    _enum(payload["question_type"], TIPOS, "question_type")
    _enum(payload["requested_level"], NIVEIS, "requested_level")
    _lista_de_str(payload["kpi_candidates"], "kpi_candidates")
    _booleano(payload["referencia_anterior"], "referencia_anterior")

    if payload["compare_to"] is not None:
        _enum(payload["compare_to"], COMPARACOES, "compare_to")
    if payload["premissa"] is not None:
        _enum(payload["premissa"], PREMISSAS, "premissa")

    for d in _lista(payload["dimensions"], "dimensions"):
        _enum(d, DIMENSOES_DE_FILTRO, "dimensions")

    _periodo(payload["period"])
    for f in _lista(payload["filters"], "filters"):
        _filtro(f)
    for a in _lista(payload["ambiguity"], "ambiguity"):
        _ambiguidade(a)
    return payload


def _enum(valor, permitidos, onde: str) -> None:
    if valor not in permitidos:
        raise ErroDeSchema(ENUM_INVALIDO, onde)


def _lista(valor, onde: str) -> list:
    if not isinstance(valor, list):
        raise ErroDeSchema(TIPO_INVALIDO, onde)
    return valor


def _lista_de_str(valor, onde: str) -> None:
    for item in _lista(valor, onde):
        if not isinstance(item, str):
            raise ErroDeSchema(TIPO_INVALIDO, onde)


def _booleano(valor, onde: str) -> None:
    if not isinstance(valor, bool):
        raise ErroDeSchema(TIPO_INVALIDO, onde)


def _campos(obj, obrigatorios, opcionais, onde: str) -> None:
    if not isinstance(obj, dict):
        raise ErroDeSchema(TIPO_INVALIDO, onde)
    extras = set(obj) - set(obrigatorios) - set(opcionais)
    if extras:
        raise ErroDeSchema(CAMPO_DESCONHECIDO, f"{onde}.{','.join(sorted(extras))}")
    faltando = set(obrigatorios) - set(obj)
    if faltando:
        raise ErroDeSchema(CAMPO_OBRIGATORIO_AUSENTE,
                           f"{onde}.{','.join(sorted(faltando))}")


def _periodo(p) -> None:
    if p is None:
        return
    _campos(p, ("grain",), ("from", "to", "relativo"), "period")
    _enum(p["grain"], GRAINS, "period.grain")
    for chave in ("from", "to", "relativo"):
        if p.get(chave) is not None and not isinstance(p[chave], str):
            raise ErroDeSchema(TIPO_INVALIDO, f"period.{chave}")


def _filtro(f) -> None:
    _campos(f, ("dimension", "terms"), (), "filters")
    _enum(f["dimension"], DIMENSOES_DE_FILTRO, "filters.dimension")
    for t in _lista(f["terms"], "filters.terms"):
        _campos(t, ("literal", "governado", "base"), (), "filters.terms")
        if not isinstance(t["literal"], str):
            raise ErroDeSchema(TIPO_INVALIDO, "filters.terms.literal")
        if t["governado"] is not None and not isinstance(t["governado"], str):
            raise ErroDeSchema(TIPO_INVALIDO, "filters.terms.governado")
        _enum(t["base"], BASES, "filters.terms.base")


def _ambiguidade(a) -> None:
    _campos(a, ("campo", "motivo"), ("opcoes",), "ambiguity")
    for chave in ("campo", "motivo"):
        if not isinstance(a[chave], str):
            raise ErroDeSchema(TIPO_INVALIDO, f"ambiguity.{chave}")
    for o in _lista(a.get("opcoes") or [], "ambiguity.opcoes"):
        if not isinstance(o, str):
            raise ErroDeSchema(TIPO_INVALIDO, "ambiguity.opcoes")


# --------------------------------------------------------------------------- #
# Payload validado -> Intent
# --------------------------------------------------------------------------- #
def para_intent(payload: dict) -> Intent:
    """Converte o payload já validado no `Intent` que o `RESOLVE` recebe.

    O contrato do `Intent` **não muda**: `filters` continua sendo
    `{dimension, terms: [str]}`. A base de cada termo é informação de
    interpretação, e vai para o registro do interpretador, não para o `Intent`.

    Termo `NAO_RESOLVIDO` entra com o **literal**, e é isso que faz o `RESOLVE`
    devolver a pergunta com as opções válidas (A-01). Descartá-lo aqui faria a
    pergunta parecer resolvida e responder outra coisa.
    """
    filtros = []
    for f in payload["filters"]:
        termos = [t["governado"] if t["base"] != NAO_RESOLVIDO and t["governado"]
                  else t["literal"]
                  for t in f["terms"]]
        if termos:
            filtros.append({"dimension": f["dimension"], "terms": termos})

    return Intent(
        question_type=payload["question_type"],
        kpi_candidates=list(payload["kpi_candidates"]),
        period=_periodo_do_intent(payload["period"]),
        filters=filtros,
        dimensions=list(payload["dimensions"]),
        requested_level=payload["requested_level"],
        compare_to=payload["compare_to"],
        ambiguity=[Ambiguity(a["campo"], a["motivo"], list(a.get("opcoes") or []))
                   for a in payload["ambiguity"]],
        premissa=payload["premissa"],
        referencia_anterior=payload["referencia_anterior"],
    )


def _periodo_do_intent(p: dict | None) -> dict | None:
    """Período do `Intent`, e o que se faz com termo relativo (P-02, D-L1).

    Três casos, e nenhum deles resolve nada aqui:

    - **período absoluto** passa como está, com `to` igual a `from` quando a
      pergunta cita um período único;
    - **período relativo** é **preservado** como `{grain, relativo}`, para que o
      `RESOLVE` o materialize contra a cobertura declarada do KPI. Este módulo
      não conhece cobertura e não deve conhecer: resolver aqui seria decidir
      período sem saber até onde o dado vai;
    - **ausência de período** continua sendo `None`, e o `RESOLVE` já a trata
      como ambiguidade com os períodos válidos como opções.

    O período relativo nunca chega ao MCP nesta forma. Ou o `RESOLVE` o
    transforma em período absoluto dentro da cobertura, ou produz ambiguidade e
    o loop para antes de qualquer chamada de valor (A-01).
    """
    if not p:
        return None
    if p.get("from"):
        saida = {"grain": p["grain"], "from": p["from"]}
        saida["to"] = p.get("to") or p["from"]
        return saida
    if p.get("relativo"):
        return {"grain": p["grain"], "relativo": p["relativo"]}
    return None


def relativo_de(payload: dict) -> str | None:
    p = payload.get("period") or {}
    return p.get("relativo") if not p.get("from") else None


def bases_de(payload: dict) -> list[str]:
    """As bases usadas, para o registro. Sem os termos, que não vão ao log."""
    return sorted({t["base"] for f in payload["filters"] for t in f["terms"]})
