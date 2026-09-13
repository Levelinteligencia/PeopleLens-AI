"""Execucao governada: consulta semantica -> SQL -> numero (ADR-0009, ADR-0028).

A traducao daqui para baixo e **codigo, nao modelo**. Dada a mesma consulta e o
mesmo estado do dado, o SQL gerado e sempre o mesmo, e os filtros fixos do
contrato sao aplicados pelo executor, jamais pelo chamador.

Tres schemas, como a Parte VIII da SPEC define:

    analytical   views sobre os Parquet da L3 (F6)
    semantic     uma view por KPI, com os filtros fixos JA aplicados
    truth        registrado **somente** sob pedido explicito, e nunca pela
                 camada semantica (ver `connect`)

A camada semantica le `semantic.` e nada mais. Nao existe caminho daqui para
RAW, standardized, conformed ou camada de verdade: o schema nao esta registrado
na conexao, entao nao e um acordo de cavalheiros, e sim um objeto que nao
existe.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from generator.config import Config

from . import plans
from .catalog import Kpi
from .query import Refusal, SemanticQuery

L3 = ("data", "processed", "analytical")

# Predicado do vocabulario -> coluna da view. O vocabulario fala em
# (tabela, coluna) fisica; a view expoe a mesma condicao ja resolvida. Sem este
# mapa um predicado viraria SQL montado a partir do YAML, que e exatamente o
# tipo de expressao livre que o ADR-0028 mantem fora.
PREDICADO_COL = {
    ("dim_job_level", "is_leadership"): "is_lideranca",
    ("dim_origin", "is_hire"): "is_contratacao",
}


class ExecutorError(RuntimeError):
    pass


@dataclass
class ExecResult:
    linhas: list[dict]
    populacao: int
    sql: str
    periodos: list[str] = field(default_factory=list)
    extras: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Conexao
# --------------------------------------------------------------------------- #
def connect(cfg: Config, with_truth: bool = False):
    """Conexao DuckDB com os schemas da Parte VIII.

    `with_truth` existe para as ferramentas de auditoria que precisam comparar
    as duas camadas, e a camada semantica **nunca** o liga. Quando desligado, a
    camada de verdade nao esta registrada na conexao: nao ha nome por onde
    alcanca-la, e nao apenas uma convencao de nao usa-la. O teste F-13 da F6
    proibiu o literal no codigo do modelo; aqui a proibicao vira a ausencia do
    objeto.
    """
    import duckdb

    con = duckdb.connect(":memory:")
    base = Path(cfg.root).joinpath(*L3)
    con.execute("CREATE SCHEMA IF NOT EXISTS analytical")
    for p in sorted(base.glob("*.parquet")):
        con.execute(
            f"CREATE OR REPLACE VIEW analytical.{p.stem} AS "
            f"SELECT * FROM read_parquet('{p.as_posix()}')")

    if with_truth:
        tp = Path(cfg.root) / "data" / "synthetic" / "truth"
        con.execute("CREATE SCHEMA IF NOT EXISTS truth")
        for p in sorted(tp.glob("*.parquet")):
            con.execute(
                f"CREATE OR REPLACE VIEW truth.{p.stem} AS "
                f"SELECT * FROM read_parquet('{p.as_posix()}')")

    con.execute("CREATE SCHEMA IF NOT EXISTS semantic")
    for kpi_id, plano in plans.PLANS.items():
        con.execute(f"CREATE OR REPLACE VIEW semantic.kpi_{kpi_id} AS {plano.sql}")
    return con


def schemas(con) -> set[str]:
    return {r[0] for r in con.execute(
        "SELECT DISTINCT schema_name FROM information_schema.schemata").fetchall()}


# --------------------------------------------------------------------------- #
# Montagem da consulta
# --------------------------------------------------------------------------- #
def _lit(v: str) -> str:
    return "'" + str(v).replace("'", "''") + "'"


def _where(q: SemanticQuery, resolvido: dict, plano: plans.Plan,
           col_periodo: str) -> tuple[list[str], Refusal | None]:
    onde = [f"{col_periodo} BETWEEN {_lit(q.period.inicio)} AND {_lit(q.period.fim)}"]

    for f in resolvido.get("filtros") or []:
        col = f["dimension"]
        if col not in plano.dimensoes:
            return [], Refusal(
                "DIMENSAO_NAO_PERMITIDA",
                f"{q.kpi} nao expoe {col!r} na camada analitica.",
                f"filtrar por: {', '.join(plano.dimensoes)}")
        valores = ", ".join(_lit(v) for v in f["members"])
        onde.append(f"{col} IN ({valores})")

    for p in resolvido.get("predicados") or []:
        chave = (p.get("table"), p.get("column"))
        col = PREDICADO_COL.get(chave)
        if col is None or col not in _colunas_do_plano(plano):
            return [], Refusal(
                "PREDICADO_INDISPONIVEL",
                f"o termo {p.get('grupo')!r} resolve para {chave[0]}.{chave[1]}, "
                f"que {q.kpi} nao expoe.",
                f"usar um termo das dimensoes que este KPI expoe: "
                f"{', '.join(plano.dimensoes)}")
        onde.append(f"{col} = {'TRUE' if p.get('equals') else 'FALSE'}")

    return onde, None


def _colunas_do_plano(plano: plans.Plan) -> set[str]:
    """Colunas que a view do plano expoe, lidas do proprio SQL do plano."""
    import re
    return {m.group(1) for m in re.finditer(r"AS\s+(\w+)", plano.sql)}


def _agregacao(m: plans.Measure) -> str:
    if m.tipo == "contagem_distinta":
        return f"COUNT(DISTINCT {m.coluna}) AS valor"
    if m.tipo == "soma":
        return f"SUM({m.coluna}) AS valor"
    if m.tipo == "mediana":
        return f"MEDIAN({m.coluna}) AS valor"
    if m.tipo == "razao":
        return (f"{m.numerador} AS numerador, {m.denominador} AS denominador, "
                f"CASE WHEN {m.denominador} = 0 THEN NULL "
                f"ELSE CAST({m.numerador} AS DOUBLE) / {m.denominador} END AS valor")
    if m.tipo == "turnover":
        return f"{m.numerador} AS numerador"
    raise ExecutorError(f"tipo de medida desconhecido: {m.tipo}")


def build_sql(q: SemanticQuery, kpi: Kpi, resolvido: dict,
              plano: plans.Plan) -> tuple[str, Refusal | None]:
    """Monta o SQL. Determinístico: mesma consulta, mesmo texto."""
    col_periodo = plans.PERIODO_COLS[q.period.grain]
    onde, recusa = _where(q, resolvido, plano, col_periodo)
    if recusa:
        return "", recusa

    dims = [d for d in q.dimensions]
    grupos = [col_periodo] + dims
    selecao = grupos + [_agregacao(plano.measure),
                        f"{plano.measure.populacao} AS populacao"]

    rollup = resolvido.get("rollup")
    fonte = f"semantic.kpi_{kpi.kpi_id}"

    if rollup == "ultimo_periodo":
        # Estoque nao se soma ao longo do tempo: doze fotos mensais somadas dao
        # doze vezes a empresa. O valor do periodo mais grosso e o do ultimo mes
        # dentro dele, que e o que o contrato declara.
        fonte = (f"(SELECT * FROM semantic.kpi_{kpi.kpi_id} "
                 f"QUALIFY periodo_mes = MAX(periodo_mes) OVER (PARTITION BY {col_periodo}))")

    sql = ("SELECT " + ", ".join(selecao) +
           f" FROM {fonte} WHERE " + " AND ".join(onde) +
           (" GROUP BY " + ", ".join(grupos) if grupos else "") +
           " ORDER BY " + ", ".join(grupos))
    return sql, None


# --------------------------------------------------------------------------- #
# Execucao
# --------------------------------------------------------------------------- #
def execute(con, q: SemanticQuery, kpi: Kpi, resolvido: dict
            ) -> tuple[ExecResult | None, Refusal | None]:
    plano = plans.plano(kpi.kpi_id)
    if plano is None:
        return None, Refusal(
            "SEM_PLANO_DE_EXECUCAO",
            f"{kpi.kpi_id} nao tem plano de execucao sobre a L3.",
            "resolver o bloqueador declarado no contrato; um KPI sem definicao "
            "fechada nao ganha plano para nao produzir numero por acidente")

    if q.period.grain not in plano.grains:
        return None, Refusal(
            "GRAIN_INCOMPATIVEL",
            f"{kpi.kpi_id} nao e apurado por {q.period.grain}.",
            f"consultar por: {', '.join(plano.grains)}")

    sql, recusa = build_sql(q, kpi, resolvido, plano)
    if recusa:
        return None, recusa

    cur = con.execute(sql)
    colunas = [d[0] for d in cur.description]
    linhas = [dict(zip(colunas, r)) for r in cur.fetchall()]

    if plano.measure.tipo == "turnover":
        linhas, sql = _turnover(con, q, kpi, resolvido, plano, linhas, sql)

    pop = sum(int(l.get("populacao") or 0) for l in linhas)
    col_periodo = plans.PERIODO_COLS[q.period.grain]
    periodos = sorted({str(l.get(col_periodo)) for l in linhas})

    extras = dict(plano.extras)
    if "taxa_de_nao_declaracao_de" in extras:
        extras["taxa_de_nao_declaracao"] = _nao_declaracao(
            con, q, kpi, resolvido, extras["taxa_de_nao_declaracao_de"])

    return ExecResult(linhas=linhas, populacao=pop, sql=sql,
                      periodos=periodos, extras=extras), None


def _turnover(con, q: SemanticQuery, kpi: Kpi, resolvido: dict,
              plano: plans.Plan, linhas: list[dict], sql: str):
    """Denominador do turnover: media do headcount das pontas do periodo.

    Nao e a soma dos meses nem a media de doze fotos: e o que o contrato declara,
    media de inicio e fim. Reusa a view de `headcount`, com o filtro fixo de
    sistema de registro ja dentro dela.
    """
    dims = list(q.dimensions)
    grupos = ["periodo_ano"] + dims
    filtros = []
    for f in resolvido.get("filtros") or []:
        if f["dimension"] in plans.PLANS["headcount"].dimensoes:
            filtros.append(f"{f['dimension']} IN (" +
                           ", ".join(_lit(v) for v in f["members"]) + ")")
    onde = [f"periodo_ano BETWEEN {_lit(q.period.inicio)} AND {_lit(q.period.fim)}"] + filtros

    den_sql = f"""
WITH base AS (
    SELECT * FROM semantic.kpi_headcount WHERE {" AND ".join(onde)}
),
pontas AS (
    SELECT {", ".join(grupos)}, periodo_mes,
           COUNT(DISTINCT party_key) AS pessoas
    FROM base GROUP BY {", ".join(grupos)}, periodo_mes
)
SELECT {", ".join(grupos)},
       (MIN_BY(pessoas, periodo_mes) + MAX_BY(pessoas, periodo_mes)) / 2.0 AS denominador
FROM pontas GROUP BY {", ".join(grupos)}
"""
    den = {tuple(str(r[i]) for i in range(len(grupos))): r[len(grupos)]
           for r in con.execute(den_sql).fetchall()}

    saida = []
    for l in linhas:
        chave = tuple(str(l.get(g)) for g in grupos)
        d = den.get(chave)
        l = dict(l)
        l["denominador"] = d
        l["valor"] = (None if not d else float(l.get("numerador") or 0) / float(d))
        saida.append(l)
    return saida, sql + "\n-- denominador:\n" + den_sql


def _nao_declaracao(con, q: SemanticQuery, kpi: Kpi, resolvido: dict,
                    campo: str) -> float | None:
    """Taxa de nao declaracao no mesmo recorte.

    Vai junto da resposta sempre (ADR-0022): excluir a nao declaracao dos dois
    lados sem reportar a taxa e o que faz o indicador parecer melhor do que e.
    Penalizar a nao declaracao no trust continua proibido.
    """
    col_periodo = plans.PERIODO_COLS[q.period.grain]
    coluna = {"genero": "genero", "disability_flag": "disability_flag"}.get(campo)
    if coluna is None:
        return None
    filtros = [f"{col_periodo} BETWEEN {_lit(q.period.inicio)} AND {_lit(q.period.fim)}"]
    for f in resolvido.get("filtros") or []:
        if f["dimension"] in plans.PLANS["headcount"].dimensoes:
            filtros.append(f"{f['dimension']} IN (" +
                           ", ".join(_lit(v) for v in f["members"]) + ")")
    nulo = (f"{coluna} IS NULL OR {coluna} IN ('Not informed', 'UNMAPPED')"
            if coluna == "genero" else f"{coluna} IS NULL")
    r = con.execute(f"""
        SELECT COUNT(DISTINCT CASE WHEN {nulo} THEN party_key END) * 1.0
               / NULLIF(COUNT(DISTINCT party_key), 0)
        FROM semantic.kpi_headcount WHERE {" AND ".join(filtros)}
    """).fetchone()
    return None if r is None or r[0] is None else round(float(r[0]), 6)
