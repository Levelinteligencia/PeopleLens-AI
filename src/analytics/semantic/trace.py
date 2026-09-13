"""Lineage da resposta e `semantic_query_log` (F7 Parte VI).

"Como o PeopleLens chegou a essa resposta?" tem seis degraus, e cinco deles ja
existiam antes da F7:

    resposta          valor, recorte, nivel, trust
       v
    KPI               id, versao, dono, status, data de certificacao
       v
    definicao         business_definition, formula, populacao, filtros, exclusoes
       v
    regra             checks que compuseram o trust; mapeamentos; membros excluidos
       v
    tabela analitica  tabelas da L3, filtros fixos aplicados, linhas consideradas
       v
    fonte             _row_id -> transformation_log -> valor original, sistema,
                      regra -> arquivo bruto

A F7 **encadeia**. A unica coisa nova e o registro da consulta, e ele existe por
dois motivos: reproduzir uma resposta meses depois exige saber a versao do KPI e
a execucao da L3 que a produziram; e uma RECUSA tambem precisa ficar registrada,
porque sem isso ninguem descobre que a mesma pergunta e recusada toda semana
pelo mesmo mapeamento pendente.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from generator.config import Config

from .catalog import Kpi
from .plans import plano as plano_de
from .query import SemanticQuery

GOV_DB = ("data", "governance", "peoplelens_gov.db")

DDL = """
CREATE TABLE IF NOT EXISTS semantic_query_log (
    trace_id        TEXT PRIMARY KEY,
    asked_at        TEXT NOT NULL,
    pergunta        TEXT,
    consulta        TEXT NOT NULL,
    kpi_id          TEXT NOT NULL,
    kpi_version     TEXT,
    kpi_status      TEXT,
    recorte         TEXT,
    respondeu       INTEGER NOT NULL,
    level           TEXT,
    valor           REAL,
    trust_status    TEXT,
    trust_score     REAL,
    limitado_por    TEXT,
    refusal_class   TEXT,
    caveats         TEXT,
    l3_run_id       TEXT,
    sql_executado   TEXT
)
"""


def novo_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def _conn(cfg: Config) -> sqlite3.Connection:
    p = Path(cfg.root).joinpath(*GOV_DB)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.execute(DDL)
    return con


def l3_run_id(cfg: Config) -> str | None:
    """Execucao da L3 que produziu as tabelas consultadas.

    Sem isso, reproduzir a resposta daqui a seis meses exigiria adivinhar qual
    carga estava no disco.
    """
    m = Path(cfg.root) / "data" / "processed" / "analytical" / "manifest.json"
    if not m.exists():
        return None
    try:
        return json.loads(m.read_text(encoding="utf-8")).get("run_id")
    except (ValueError, OSError):
        return None


def registrar(cfg: Config, q: SemanticQuery, answer, sql: str | None = None) -> None:
    """Uma linha por resposta E por recusa."""
    con = _conn(cfg)
    trust = answer.trust or {}
    con.execute(
        "INSERT OR REPLACE INTO semantic_query_log VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (answer.trace_id,
         datetime.utcnow().isoformat(timespec="seconds"),
         q.pergunta,
         json.dumps(q.to_dict(), ensure_ascii=False),
         q.kpi,
         (answer.kpi or {}).get("version"),
         (answer.kpi or {}).get("status"),
         json.dumps(answer.scope, ensure_ascii=False),
         int(answer.respondeu),
         answer.level,
         None if answer.value is None else float(answer.value),
         trust.get("status"),
         trust.get("score"),
         trust.get("limitado_por"),
         (answer.refusal or {}).get("classe"),
         json.dumps(answer.caveats, ensure_ascii=False),
         l3_run_id(cfg),
         sql))
    con.commit()
    con.close()


def ler(cfg: Config, trace_id: str) -> dict | None:
    con = _conn(cfg)
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM semantic_query_log WHERE trace_id = ?",
                    (trace_id,)).fetchone()
    con.close()
    return dict(r) if r else None


def contagem(cfg: Config) -> dict:
    con = _conn(cfg)
    total = con.execute("SELECT COUNT(*) FROM semantic_query_log").fetchone()[0]
    recusas = con.execute(
        "SELECT COUNT(*) FROM semantic_query_log WHERE respondeu = 0").fetchone()[0]
    por_classe = dict(con.execute(
        "SELECT refusal_class, COUNT(*) FROM semantic_query_log "
        "WHERE refusal_class IS NOT NULL GROUP BY 1").fetchall())
    con.close()
    return {"consultas": total, "recusas": recusas, "recusas_por_classe": por_classe}


# --------------------------------------------------------------------------- #
# Os seis degraus
# --------------------------------------------------------------------------- #
def trace(cfg: Config, answer, kpi: Kpi | None) -> dict:
    """Encadeia os seis degraus, da resposta ate o `_row_id` da fonte.

    O ultimo degrau nao devolve as linhas: devolve **por onde** chegar nelas, que
    e `source_row_id` na tabela da L3 e dali `transformation_log`, que ja existe
    desde a F3 com valor original, sistema de origem e regra aplicada.
    """
    if kpi is None:
        return {"resposta": {"trace_id": answer.trace_id},
                "kpi": None, "nota": "consulta recusada antes de resolver o KPI"}

    p = plano_de(kpi.kpi_id)
    trust = answer.trust or {}
    return {
        "resposta": dict(trace_id=answer.trace_id, level=answer.level,
                         value=answer.value, scope=answer.scope,
                         trust=trust.get("status")),
        "kpi": dict(id=kpi.kpi_id, version=kpi.version, owner=kpi.owner,
                    status=kpi.status,
                    certified_at=(kpi.doc.get("certification") or {}).get("approved_at")),
        "definicao": dict(business_definition=kpi.doc.get("business_definition"),
                          formula=kpi.doc.get("formula"),
                          population=kpi.doc.get("population"),
                          filters=kpi.doc.get("filters"),
                          exclusions=kpi.doc.get("exclusions")),
        "regra": dict(checks=list(kpi.doc.get("depends_on_checks") or []),
                      mappings=list(kpi.doc.get("depends_on_mappings") or []),
                      trust_recorte=trust.get("recorte_usado"),
                      perda_por_classe=trust.get("perda_por_classe"),
                      membros_excluidos=[e.get("o_que")
                                         for e in kpi.doc.get("exclusions") or []]),
        "tabela_analitica": dict(
            layer="analytical",
            tabelas=list(p.tabelas) if p else [],
            filtros_fixos=[f.get("regra") for f in kpi.doc.get("filters") or []],
            linhas_consideradas=len(answer.rows),
            l3_run_id=l3_run_id(cfg)),
        "fonte": dict(
            por_onde="source_row_id nas tabelas da L3",
            depois="transformation_log (F3): valor original, sistema de origem, "
                   "regra aplicada",
            e_entao="arquivo bruto em data/raw, imutavel"),
    }
