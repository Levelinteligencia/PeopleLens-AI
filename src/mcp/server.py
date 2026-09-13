"""Registro de capacidades e dispatch (MCP SPEC v0.1, Partes II e V; ADR-0031).

Seis ferramentas, e **nenhuma outra**. Uma sétima é mudança de SPEC, não de
configuração.

O registro é a fronteira. Não existe `execute_sql`, `query_database`,
`read_table`, `list_tables`, `describe_schema`, `run_python` nem `read_file`, e
o teste é o da decisão 2 do ADR-0031: **se o chamador escolhe o objeto que será
lido, a ferramenta é genérica** — ainda que o nome pareça específico.

Escrita não é negada por permissão: não há ferramenta de escrita, então não há
chamada a negar. O servidor anuncia `read_only` e o teste verifica que a
declaração bate com o registro.

Este módulo é o *boundary*, não o transporte. `list_tools()` devolve o manifesto
em forma de `tools/list` (nome, descrição, `inputSchema`), e `call()` executa uma
capacidade. Ligar isso a um transporte concreto é um passo mecânico e posterior,
deliberadamente fora da v0.1: o que precisa estar certo aqui é a superfície.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from generator.config import Config
from analytics.semantic import ask as semantic_ask
from analytics.semantic import trace as semtrace

from . import actor as act
from . import envelope as env
from . import limits, observability, tools

READ_ONLY = True

# Nomes que não podem existir neste servidor, em nenhuma versão. A lista é
# verificada por teste, e não confiada à revisão.
CAPACIDADES_PROIBIDAS = (
    "execute_sql", "query_database", "read_table", "arbitrary_query",
    "run_python", "read_file", "list_tables", "describe_schema", "get_connection",
    "write_kpi", "update_kpi", "set_trust", "approve_mapping", "resolve_identity",
    "delete_kpi", "upsert", "insert", "update", "delete",
)

_PERIODO = {
    "type": "object", "additionalProperties": False,
    "required": ["grain", "from"],
    "properties": {
        "grain": {"enum": ["mes", "trimestre", "ano", "ciclo"]},
        "from": {"type": "string"},
        "to": {"type": "string"},
    },
}

_FILTROS = {
    "type": "array",
    "items": {
        "type": "object", "additionalProperties": False,
        "required": ["dimension", "in"],
        "properties": {
            "dimension": {"type": "string"},
            "in": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        },
    },
}


@dataclass(frozen=True)
class Capacidade:
    name: str
    scope: str
    description: str
    input_schema: dict
    handler: object


CAPACIDADES: tuple[Capacidade, ...] = (
    Capacidade(
        name="get_kpi", scope=act.VALUE,
        description=("Valor de um KPI governado num periodo, sem quebra por "
                     "dimensao. Nao aceita SQL, tabela nem coluna."),
        input_schema={
            "type": "object", "additionalProperties": False,
            "required": ["kpi", "period"],
            "properties": {
                "kpi": {"type": "string"},
                "period": _PERIODO,
                "filters": _FILTROS,
                "requested_level": {"enum": ["FACT", "CONTEXT"]},
                "kpi_version": {"type": "string"},
                "request_id": {"type": "string"},
            },
        },
        handler=tools.get_kpi),
    Capacidade(
        name="compare_kpi", scope=act.VALUE,
        description=("Compara o mesmo KPI, no mesmo recorte, com uma base de "
                     "comparacao declarada. Opera em CONTEXT."),
        input_schema={
            "type": "object", "additionalProperties": False,
            "required": ["kpi", "period", "compare_to"],
            "properties": {
                "kpi": {"type": "string"},
                "period": _PERIODO,
                "compare_to": {"enum": ["periodo_anterior",
                                        "mesmo_periodo_ano_anterior",
                                        "media_da_populacao"]},
                "filters": _FILTROS,
                "kpi_version": {"type": "string"},
                "request_id": {"type": "string"},
            },
        },
        handler=tools.compare_kpi),
    Capacidade(
        name="breakdown_kpi", scope=act.VALUE,
        description=("Quebra um KPI por ate duas dimensoes permitidas pelo "
                     "contrato. A supressao por privacidade vem da camada "
                     "semantica e e preservada."),
        input_schema={
            "type": "object", "additionalProperties": False,
            "required": ["kpi", "period", "dimensions"],
            "properties": {
                "kpi": {"type": "string"},
                "period": _PERIODO,
                # Sem `maxItems`: passar do limite de dimensoes e RECUSA
                # explicada, e nao erro de forma (SPEC Parte VIII). O numero
                # maximo viaja na descricao e na recusa.
                "dimensions": {"type": "array", "items": {"type": "string"},
                               "minItems": 1},
                "filters": _FILTROS,
                "order_by": {"enum": ["value", "dimension"]},
                "top_n": {"type": "integer", "minimum": 1,
                          "maximum": limits.MAX_LINHAS_RETORNADAS},
                "requested_level": {"enum": ["FACT", "CONTEXT"]},
                "kpi_version": {"type": "string"},
                "request_id": {"type": "string"},
            },
        },
        handler=tools.breakdown_kpi),
    Capacidade(
        name="get_kpi_definition", scope=act.DEFINITION,
        description=("Definicao governada de um KPI em linguagem de negocio, ou "
                     "o catalogo resumido. Nao expoe tabela nem SQL."),
        input_schema={
            "type": "object", "additionalProperties": False,
            "properties": {
                "kpi": {"type": "string"},
                "version": {"type": "string"},
                "include": {"type": "array", "items": {"type": "string"}},
                "request_id": {"type": "string"},
            },
        },
        handler=tools.get_kpi_definition),
    Capacidade(
        name="get_trust", scope=act.TRUST,
        description=("Confianca governada de um KPI num recorte, sem calcular o "
                     "valor. Preserva CERTIFIED / LIMITED / BLOCKED."),
        input_schema={
            "type": "object", "additionalProperties": False,
            "required": ["kpi"],
            "properties": {
                "kpi": {"type": "string"},
                "period": _PERIODO,
                "scope": {"type": "object", "additionalProperties": False,
                          "properties": {"filters": _FILTROS}},
                "explain": {"type": "boolean"},
                "request_id": {"type": "string"},
            },
        },
        handler=tools.get_trust),
    Capacidade(
        name="get_lineage", scope=act.LINEAGE,
        description=("Linhagem de uma resposta (por trace_id) ou de um KPI. O "
                     "degrau de fonte descreve o caminho e nao o percorre."),
        input_schema={
            "type": "object", "additionalProperties": False,
            "properties": {
                "trace_id": {"type": "string"},
                "kpi": {"type": "string"},
                "depth": {"enum": ["definition", "rule", "table", "source"]},
                "request_id": {"type": "string"},
            },
        },
        handler=tools.get_lineage),
)

POR_NOME = {c.name: c for c in CAPACIDADES}


def list_tools() -> list[dict]:
    """Manifesto das capacidades, em forma de `tools/list`."""
    return [{"name": c.name, "description": c.description,
             "inputSchema": c.input_schema, "scope": c.scope,
             "readOnly": True}
            for c in CAPACIDADES]


def _valida_forma(cap: Capacidade, args: dict) -> str | None:
    """Campo desconhecido reprova, e essa é a porta que fica fechada.

    Ignorar o campo extra seria por onde `{"sql": ...}` ou
    `{"table": "fact_headcount_snapshot"}` entraria sem ninguem notar, e o
    objeto deixaria de ser a fronteira do ADR-0028.
    """
    schema = cap.input_schema
    permitidos = set(schema["properties"])
    extras = set(args) - permitidos
    if extras:
        return (f"campos desconhecidos em {cap.name}: {sorted(extras)}. "
                "A fronteira nao aceita SQL, nome de tabela, coluna ou junção.")
    for obrig in schema.get("required", ()):
        if obrig not in args:
            return f"campo obrigatorio ausente em {cap.name}: {obrig}"
    for chave, sub in (("period", _PERIODO), ("scope", None)):
        valor = args.get(chave)
        if isinstance(valor, dict) and sub:
            sobra = set(valor) - set(sub["properties"])
            if sobra:
                return f"campos desconhecidos em `{chave}`: {sorted(sobra)}"
    for f in args.get("filters") or ():
        if not isinstance(f, dict):
            return "cada filtro e um objeto {dimension, in}"
        sobra = set(f) - {"dimension", "in"}
        if sobra:
            return (f"campos desconhecidos no filtro: {sorted(sobra)}. "
                    "Filtro nao aceita expressao, operador nem coluna fisica.")

    # Enum e tipo: o que o `inputSchema` declara e o que a fronteira aceita.
    # Sem esta verificacao, o manifesto anuncia um contrato e o servidor honra
    # outro, e quem integra confia no manifesto.
    problema = _valida_valores(schema["properties"], args, cap.name)
    if problema:
        return problema
    valor_periodo = args.get("period")
    if isinstance(valor_periodo, dict):
        problema = _valida_valores(_PERIODO["properties"], valor_periodo,
                                   f"{cap.name}.period")
        if problema:
            return problema
    return None


def _valida_valores(props: dict, args: dict, onde: str) -> str | None:
    for chave, valor in args.items():
        spec = props.get(chave)
        if not spec or valor is None:
            continue
        if "enum" in spec and valor not in spec["enum"]:
            return (f"valor invalido para `{chave}` em {onde}: {valor!r}. "
                    f"Valores aceitos: {spec['enum']}")
        tipo = spec.get("type")
        if tipo == "string" and not isinstance(valor, str):
            return f"`{chave}` em {onde} precisa ser texto"
        if tipo == "integer" and not isinstance(valor, int):
            return f"`{chave}` em {onde} precisa ser inteiro"
        if tipo == "boolean" and not isinstance(valor, bool):
            return f"`{chave}` em {onde} precisa ser booleano"
        if tipo == "array" and not isinstance(valor, list):
            return f"`{chave}` em {onde} precisa ser lista"
        if tipo == "array" and spec.get("maxItems") and len(valor) > spec["maxItems"]:
            return (f"`{chave}` em {onde} aceita no maximo {spec['maxItems']} "
                    f"itens, e vieram {len(valor)}")
    return None


@dataclass
class Server:
    """A fronteira. Guarda o motor da F7 e despacha as seis capacidades."""
    cfg: Config
    engine: semantic_ask.Engine
    read_only: bool = READ_ONLY

    @classmethod
    def start(cls, cfg: Config, engine: semantic_ask.Engine | None = None) -> "Server":
        return cls(cfg=cfg, engine=engine or semantic_ask.engine(cfg))

    def close(self) -> None:
        self.engine.close()

    # ---------------------------------------------------------------- dispatch
    def call(self, tool: str, args: dict | None = None,
             actor: act.Actor | None = None, registrar: bool = True) -> env.Envelope:
        args = dict(args or {})
        ator = actor or act.ATOR_PADRAO
        request_id = str(args.pop("request_id", None) or semtrace.novo_trace_id())
        t0 = time.perf_counter()

        cap = POR_NOME.get(tool)
        if cap is None:
            e = env.error(tool, request_id, semtrace.novo_trace_id(),
                          classe=env.CAPACIDADE_INEXISTENTE,
                          mensagem=f"a capacidade {tool!r} nao existe neste MCP.",
                          o_que_resolveria="usar uma das capacidades declaradas: "
                                           + ", ".join(POR_NOME),
                          detalhe={"capacidades": sorted(POR_NOME)})
            return self._fim(e, request_id, tool, ator, args, t0, registrar)

        # Escopo antes de qualquer coisa: uma chamada nao autorizada nao deve
        # nem revelar se o KPI existe (ADR-0033, decisao 5).
        if not ator.pode(tool):
            e = env.error(tool, request_id, semtrace.novo_trace_id(),
                          classe=env.ESCOPO_INSUFICIENTE,
                          mensagem=f"o ator nao tem o escopo {cap.scope!r}.",
                          o_que_resolveria=f"solicitar o escopo {cap.scope} ao "
                                           "administrador",
                          detalhe={"escopo_exigido": cap.scope})
            return self._fim(e, request_id, tool, ator, args, t0, registrar)

        problema = _valida_forma(cap, args)
        if problema:
            e = env.error(tool, request_id, semtrace.novo_trace_id(),
                          classe=env.PARAMETRO_INVALIDO, mensagem=problema,
                          o_que_resolveria="enviar apenas os campos declarados no "
                                           "inputSchema desta capacidade")
            return self._fim(e, request_id, tool, ator, args, t0, registrar)

        kpi_pedido = args.get("kpi")
        if kpi_pedido and not ator.pode_kpi(kpi_pedido):
            e = env.error(tool, request_id, semtrace.novo_trace_id(),
                          classe=env.ESCOPO_INSUFICIENTE,
                          mensagem=f"o ator nao tem acesso ao KPI {kpi_pedido!r}.",
                          o_que_resolveria="solicitar acesso ao KPI, ou consultar "
                                           "um dos permitidos")
            return self._fim(e, request_id, tool, ator, args, t0, registrar)

        ctx = tools.Contexto(engine=self.engine, actor=ator, request_id=request_id)
        envelope, _ans, _dur = cap.handler(ctx, **args)
        return self._fim(envelope, request_id, tool, ator, args, t0, registrar)

    # --------------------------------------------------------------- registro
    def _fim(self, envelope: env.Envelope, request_id: str, tool: str,
             ator: act.Actor, args: dict, t0: float,
             registrar: bool) -> env.Envelope:
        if not registrar:
            return envelope
        data = envelope.data or {}
        observability.registrar(
            self.cfg, request_id=request_id, trace_id=envelope.trace_id,
            tool=tool, actor=ator, envelope=envelope,
            kpi_id=(envelope.kpi or {}).get("id") or args.get("kpi"),
            kpi_version=(envelope.kpi or {}).get("version"),
            period=args.get("period"),
            dimensions=list(args.get("dimensions") or []),
            filter_dimensions=[f.get("dimension") for f in args.get("filters") or ()],
            rows_returned=int(data.get("rows_returned") or 0),
            rows_suppressed=int(data.get("rows_suppressed") or 0),
            duration_ms=int((time.perf_counter() - t0) * 1000))
        return envelope
