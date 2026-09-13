"""Registro de execução do agente (SPEC Parte XIII; decisão A-04).

Quatro tabelas, uma chave, nenhuma duplicação:

    agent_run_log.trace_id -> mcp_call_log.trace_id -> semantic_query_log.trace_id
       por que chamou           quem chamou              o que foi perguntado

A pergunta original é registrada **depois de sanitizada** (A-04). O que nunca é
registrado, sanitizado ou não: dado pessoal descoberto durante a execução, linha
de resultado, valor individual — isso não é sanitização, é não gravar.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from generator.config import Config

from . import redaction

GOV_DB = ("data", "governance", "peoplelens_gov.db")

DDL = """
CREATE TABLE IF NOT EXISTS agent_run_log (
    run_id            TEXT PRIMARY KEY,
    request_id        TEXT NOT NULL,
    timestamp         TEXT NOT NULL,
    actor_ref         TEXT NOT NULL,
    actor_type        TEXT NOT NULL,
    pergunta_sanitizada TEXT,
    pergunta_redigida INTEGER NOT NULL,
    question_type     TEXT,
    kpi_id            TEXT,
    intent            TEXT,
    plan              TEXT,
    trace_ids         TEXT,
    tools_usadas      TEXT,
    outcomes          TEXT,
    trust_status      TEXT,
    response_level    TEXT,
    ceiling_from      TEXT,
    decisions         TEXT,
    stop_reason       TEXT NOT NULL,
    parcial           INTEGER NOT NULL,
    iteracoes         INTEGER,
    chamadas_mcp      INTEGER,
    bloqueios_privacidade INTEGER,
    duracao_ms        INTEGER,
    erro_tecnico      TEXT,
    interpretacao     TEXT
)
"""

# Colunas acrescentadas depois da primeira versão da tabela. `CREATE TABLE IF
# NOT EXISTS` não altera tabela existente, então a migração é explícita: sem
# ela, um banco de governança já criado perderia o registro do interpretador
# em silêncio, que é o tipo de perda que este módulo existe para não ter.
COLUNAS_ACRESCENTADAS = (("interpretacao", "TEXT"),)

# Nunca registrado, em nenhuma coluna e em nenhuma circunstância.
NUNCA_REGISTRADO = ("party_key", "employee_id", "source_employee_id", "full_name",
                    "pergunta_original", "filter_values", "result_rows",
                    "kpi_value", "valores")


def _conn(cfg: Config) -> sqlite3.Connection:
    p = Path(cfg.root).joinpath(*GOV_DB)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.execute(DDL)
    existentes = {r[1] for r in con.execute("PRAGMA table_info(agent_run_log)")}
    for coluna, tipo in COLUNAS_ACRESCENTADAS:
        if coluna not in existentes:
            con.execute(f"ALTER TABLE agent_run_log ADD COLUMN {coluna} {tipo}")
    con.commit()
    return con


def registrar(cfg: Config, execucao, ator, contexto) -> None:
    """Uma linha por execução — inclusive por recusa, ambiguidade e bloqueio."""
    state = execucao.state
    resposta = execucao.resposta
    allow = contexto.todos_os_termos() if contexto else set()

    bruta = state.pergunta or ""
    sanitizada = redaction.redigir(bruta, allow)
    foi_redigida = sanitizada != bruta

    intent = state.intent
    envs = [o.envelope for o in state.observacoes]
    trust = next((e.get("trust", {}).get("status") for e in envs
                  if (e.get("trust") or {}).get("status")), None)
    nivel = next(((e.get("response_level") or {}).get("granted") for e in envs
                  if (e.get("response_level") or {}).get("granted")), None)
    teto = next(((e.get("response_level") or {}).get("ceiling_from") for e in envs
                 if (e.get("response_level") or {}).get("ceiling_from")), None)
    erro = next((json.dumps((e.get("refusal") or {}).get("classe"))
                 for e in envs if e.get("outcome") == "ERROR"), None)

    # Metadados do interpretador. Não carregam pergunta, texto do modelo,
    # valor de filtro nem credencial: o `Registro` é fechado justamente para
    # que não possa carregar (ver `llm_interpreter.Registro`).
    interpretacao = getattr(execucao, "interpretacao", None) or {}

    con = _conn(cfg)
    con.execute(
        "INSERT OR REPLACE INTO agent_run_log VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (state.run_id, state.request_id,
         datetime.utcnow().isoformat(timespec="seconds"),
         ator.ref(), ator.type,
         sanitizada, int(foi_redigida),
         getattr(intent, "question_type", None),
         getattr(intent, "kpi", None),
         json.dumps(intent.to_dict(), ensure_ascii=False) if intent else None,
         json.dumps(state.plano.to_dict(), ensure_ascii=False) if state.plano else None,
         ",".join(c.trace_id for c in state.chamadas if c.trace_id),
         ",".join(c.tool for c in state.chamadas),
         ",".join(c.outcome for c in state.chamadas),
         trust, nivel, teto,
         json.dumps([d.to_dict() for d in state.decisoes], ensure_ascii=False),
         state.stop_reason, int(resposta.parcial),
         state.iteracoes, state.chamadas_efetivas,
         len(execucao.bloqueios_de_privacidade), execucao.duracao_ms, erro,
         json.dumps(interpretacao, ensure_ascii=False) if interpretacao else None))
    con.commit()
    con.close()


def ler(cfg: Config, run_id: str) -> dict | None:
    con = _conn(cfg)
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM agent_run_log WHERE run_id = ?",
                    (run_id,)).fetchone()
    con.close()
    return dict(r) if r else None


def contagem(cfg: Config) -> dict:
    con = _conn(cfg)
    total = con.execute("SELECT COUNT(*) FROM agent_run_log").fetchone()[0]
    por_parada = dict(con.execute(
        "SELECT stop_reason, COUNT(*) FROM agent_run_log GROUP BY 1").fetchall())
    con.close()
    return {"execucoes": total, "por_stop_reason": por_parada}
