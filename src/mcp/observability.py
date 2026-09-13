"""Log de chamada do MCP (MCP SPEC v0.1, Parte IX).

O log **não duplica** o `semantic_query_log` da F7. Ele registra quem chamou,
qual capacidade, com que escopo e em quanto tempo, e referencia o **mesmo**
`trace_id`. Duas tabelas descrevendo a mesma chamada divergem, que é a mesma
razão pela qual `depends_on_checks` é derivado e não digitado.

    mcp_call_log.trace_id  ->  semantic_query_log.trace_id  ->  l3_run_id
         quem chamou              o que foi perguntado          qual carga

O que **não** se registra é tão importante quanto o que se registra:

- nenhum identificador de pessoa (`party_key`, `employee_id`, nome);
- nenhuma linha do resultado;
- **nenhum valor de filtro**. Registra-se que houve filtro por `pais`, nunca
  quais países. Uma sequência de consultas estreitando o recorte é um traço de
  reidentificação, e guardá-la cria o risco que a supressão por n mínimo existe
  para evitar;
- nenhuma pergunta em linguagem natural: ela pode conter nome de pessoa.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from generator.config import Config

GOV_DB = ("data", "governance", "peoplelens_gov.db")

DDL = """
CREATE TABLE IF NOT EXISTS mcp_call_log (
    request_id      TEXT NOT NULL,
    trace_id        TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    tool            TEXT NOT NULL,
    actor_ref       TEXT NOT NULL,
    actor_type      TEXT NOT NULL,
    scopes_used     TEXT,
    kpi_id          TEXT,
    kpi_version     TEXT,
    period_grain    TEXT,
    period_from     TEXT,
    period_to       TEXT,
    dimensions      TEXT,
    filter_dimensions TEXT,
    outcome         TEXT NOT NULL,
    refusal_class   TEXT,
    trust_status    TEXT,
    trust_score     REAL,
    response_level  TEXT,
    rows_returned   INTEGER,
    rows_suppressed INTEGER,
    duration_ms     INTEGER,
    PRIMARY KEY (request_id, trace_id)
)
"""

# Campos que nunca entram no log, em nenhuma circunstância. A lista existe para
# ser verificada por teste, e não apenas prometida no docstring.
NUNCA_REGISTRADO = ("party_key", "employee_id", "source_employee_id", "full_name",
                    "filter_values", "pergunta", "result_rows", "kpi_value",
                    "gender", "race_ethnicity")


def _conn(cfg: Config) -> sqlite3.Connection:
    p = Path(cfg.root).joinpath(*GOV_DB)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.execute(DDL)
    return con


def registrar(cfg: Config, *, request_id: str, trace_id: str, tool: str,
              actor, envelope, kpi_id: str | None = None,
              kpi_version: str | None = None, period: dict | None = None,
              dimensions: list[str] | None = None,
              filter_dimensions: list[str] | None = None,
              rows_returned: int = 0, rows_suppressed: int = 0,
              duration_ms: int = 0) -> None:
    """Uma linha por chamada, inclusive por recusa e por supressão.

    Recusa entra com a mesma dignidade de uma resposta: sem isso, ninguém
    descobre que a mesma pergunta é recusada toda semana pelo mesmo mapeamento
    pendente.
    """
    trust = envelope.trust or {}
    nivel = (envelope.response_level or {}).get("granted")
    con = _conn(cfg)
    con.execute(
        "INSERT OR REPLACE INTO mcp_call_log VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (request_id, trace_id,
         datetime.utcnow().isoformat(timespec="seconds"),
         tool, actor.ref(), actor.type,
         ",".join(sorted(actor.scopes)),
         kpi_id, kpi_version,
         (period or {}).get("grain"), (period or {}).get("from"),
         (period or {}).get("to"),
         ",".join(dimensions or []),          # NOMES de dimensão
         ",".join(filter_dimensions or []),   # NOMES, nunca os valores filtrados
         envelope.outcome,
         (envelope.refusal or {}).get("classe"),
         trust.get("status"), trust.get("score"),
         nivel, rows_returned, rows_suppressed, duration_ms))
    con.commit()
    con.close()


def ler(cfg: Config, trace_id: str) -> dict | None:
    con = _conn(cfg)
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM mcp_call_log WHERE trace_id = ?",
                    (trace_id,)).fetchone()
    con.close()
    return dict(r) if r else None


def contagem(cfg: Config) -> dict:
    con = _conn(cfg)
    total = con.execute("SELECT COUNT(*) FROM mcp_call_log").fetchone()[0]
    por_outcome = dict(con.execute(
        "SELECT outcome, COUNT(*) FROM mcp_call_log GROUP BY 1").fetchall())
    por_tool = dict(con.execute(
        "SELECT tool, COUNT(*) FROM mcp_call_log GROUP BY 1").fetchall())
    con.close()
    return {"chamadas": total, "por_outcome": por_outcome, "por_tool": por_tool}
