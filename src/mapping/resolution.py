"""Resolucao governada de excecoes de mapeamento e de identidade (F4).

Duas filas, uma governanca. O ciclo de vida e o mesmo e os estados sao os da
Especificacao, secao 17:

    OPEN -> UNDER_REVIEW -> APPROVED | REJECTED

Regras que este modulo faz valer, e que existem para impedir exatamente o
atalho que todo mundo toma:

1. **nenhuma promocao automatica.** Nao existe funcao que aprove por limiar de
   confianca. Toda aprovacao exige `standard_value` explicito, um responsavel e
   uma justificativa. Sugestao de confianca 0,98 e sugestao;
2. **aprovar escreve no arquivo de referencia versionado** (ADR-0009), nao no
   banco. O historico do Git e a trilha de auditoria, e `approved_by` passa a
   ter rastro externo verificavel;
3. **toda transicao fica no log**, inclusive as rejeicoes. Saber o que foi
   recusado e por que vale tanto quanto saber o que foi aprovado;
4. **rejeitar nao apaga.** A excecao continua na fila com status REJECTED, e se
   o valor voltar a aparecer a contagem sobe. Rejeicao nao e esquecimento.
"""
from __future__ import annotations

import csv
import sqlite3
from datetime import datetime
from pathlib import Path

import polars as pl

from generator.config import Config
from .depara import FIELDS, GOV_DB, _norm

STATES = ("OPEN", "UNDER_REVIEW", "APPROVED", "REJECTED")
HEADER = ["mapping_id", "source_system", "source_field", "source_value", "standard_value",
          "mapping_status", "confidence_score", "valid_from", "valid_to", "approved_by", "approved_at"]


class GovernanceError(RuntimeError):
    pass


class Governance:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.root = Path(cfg.root)
        self.conn = sqlite3.connect(self.root / GOV_DB)
        self._ensure()

    def _ensure(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS resolution_log (
                log_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                queue         TEXT NOT NULL,
                item_id       TEXT NOT NULL,
                from_status   TEXT,
                to_status     TEXT NOT NULL,
                decided_value TEXT,
                rationale     TEXT NOT NULL,
                decided_by    TEXT NOT NULL,
                decided_at    TEXT NOT NULL,
                promoted_to   TEXT
            )""")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS identity_decisions (
                decision_id      TEXT PRIMARY KEY,
                source_system    TEXT NOT NULL,
                source_employee_id TEXT NOT NULL,
                candidate_employee_id INTEGER,
                match_method     TEXT,
                match_confidence REAL,
                status           TEXT NOT NULL,
                decided_employee_id INTEGER,
                rationale        TEXT,
                decided_by       TEXT,
                decided_at       TEXT,
                first_seen       TEXT,
                last_seen        TEXT
            )""")
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(identity_decisions)")}
        if "last_run_id" not in cols:
            self.conn.execute("ALTER TABLE identity_decisions ADD COLUMN last_run_id TEXT")
        self.conn.commit()

    # ------------------------------------------------------------------ log
    def _log(self, queue: str, item_id: str, frm: str | None, to: str,
             value: str | None, rationale: str, by: str, promoted_to: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO resolution_log (queue,item_id,from_status,to_status,decided_value,"
            "rationale,decided_by,decided_at,promoted_to) VALUES (?,?,?,?,?,?,?,?,?)",
            (queue, item_id, frm, to, value, rationale, by,
             datetime.utcnow().isoformat(timespec="seconds"), promoted_to))
        self.conn.commit()

    def log(self) -> pl.DataFrame:
        cur = self.conn.execute("SELECT * FROM resolution_log ORDER BY log_id")
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()

    # ------------------------------------------- fila de excecoes de mapeamento
    def _exception(self, exception_id: str) -> dict:
        cur = self.conn.execute("SELECT * FROM mapping_exceptions WHERE exception_id=?", (exception_id,))
        row = cur.fetchone()
        if not row:
            raise GovernanceError(f"excecao inexistente: {exception_id}")
        return dict(zip([d[0] for d in cur.description], row))

    def under_review(self, exception_id: str, by: str, rationale: str) -> None:
        e = self._exception(exception_id)
        if e["status"] != "OPEN":
            raise GovernanceError(f"so excecao OPEN vai para revisao; {exception_id} esta {e['status']}")
        self.conn.execute("UPDATE mapping_exceptions SET status='UNDER_REVIEW' WHERE exception_id=?", (exception_id,))
        self.conn.commit()
        self._log("mapping", exception_id, e["status"], "UNDER_REVIEW", None, rationale, by)

    def approve(self, exception_id: str, standard_value: str, by: str, rationale: str,
                valid_from: str = "", valid_to: str = "") -> Path:
        """Aprova uma excecao e promove o mapeamento para o arquivo de referencia.

        Exige `standard_value` explicito de proposito: nao existe caminho em que
        o sistema escolha o valor por conta propria. A sugestao do pipeline pode
        ser usada como ponto de partida, e quem aprova declara o que aprovou.
        """
        if not standard_value or not standard_value.strip():
            raise GovernanceError("aprovacao exige standard_value explicito")
        if not rationale or len(rationale.strip()) < 10:
            raise GovernanceError("aprovacao exige justificativa")
        e = self._exception(exception_id)
        if e["status"] in ("APPROVED", "REJECTED"):
            raise GovernanceError(f"{exception_id} ja esta {e['status']}")

        path = self._promote(e["source_field"], e["source_value"], standard_value, by,
                             valid_from=valid_from, valid_to=valid_to)
        self.conn.execute(
            "UPDATE mapping_exceptions SET status='APPROVED', resolution=?, resolved_by=?, resolved_at=? "
            "WHERE exception_id=?",
            (standard_value, by, datetime.utcnow().isoformat(timespec="seconds"), exception_id))
        self.conn.commit()
        self._log("mapping", exception_id, e["status"], "APPROVED", standard_value, rationale, by,
                  promoted_to=str(path.relative_to(self.root)))
        return path

    def reject(self, exception_id: str, by: str, rationale: str) -> None:
        if not rationale or len(rationale.strip()) < 10:
            raise GovernanceError("rejeicao exige justificativa")
        e = self._exception(exception_id)
        if e["status"] in ("APPROVED", "REJECTED"):
            raise GovernanceError(f"{exception_id} ja esta {e['status']}")
        self.conn.execute(
            "UPDATE mapping_exceptions SET status='REJECTED', resolution=?, resolved_by=?, resolved_at=? "
            "WHERE exception_id=?",
            ("rejeitado", by, datetime.utcnow().isoformat(timespec="seconds"), exception_id))
        self.conn.commit()
        self._log("mapping", exception_id, e["status"], "REJECTED", None, rationale, by)

    # ------------------------------------------------------------- promocao
    def _promote(self, field: str, source_value: str, standard_value: str, by: str,
                 valid_from: str = "", valid_to: str = "") -> Path:
        """Escreve o mapeamento aprovado no CSV versionado.

        Idempotente: se ja existir linha APPROVED para o mesmo valor de origem
        na mesma vigencia, nao duplica.
        """
        fname = FIELDS.get(field)
        if not fname:
            raise GovernanceError(f"campo sem arquivo de referencia: {field}")
        path = self.root / "data" / "reference" / f"{fname}.csv"
        rows: list[dict] = []
        if path.exists():
            with open(path, encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
        for r in rows:
            if (_norm(r["source_value"]) == _norm(source_value)
                    and r["mapping_status"] == "APPROVED"
                    and (r.get("valid_from") or "") == valid_from
                    and (r.get("valid_to") or "") == valid_to):
                return path
        prefix = fname.upper()
        seq = sum(1 for r in rows if r["mapping_id"].startswith(prefix)) + 1
        rows.append({
            "mapping_id": f"{prefix}-{seq:04d}", "source_system": "*", "source_field": field,
            "source_value": source_value, "standard_value": standard_value,
            "mapping_status": "APPROVED", "confidence_score": "1.0",
            "valid_from": valid_from, "valid_to": valid_to,
            "approved_by": by, "approved_at": datetime.utcnow().date().isoformat(),
        })
        with open(path, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=HEADER)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in HEADER})
        return path

    def deprecate(self, field: str, source_value: str, by: str, rationale: str) -> Path:
        """Marca um mapeamento aprovado como DEPRECATED, sem apaga-lo.

        Usado quando a organizacao muda o significado de um valor. O historico
        precisa continuar legivel: series antigas foram calculadas com o mapa
        antigo, e apagar a linha tornaria isso irreconstruivel.
        """
        fname = FIELDS[field]
        path = self.root / "data" / "reference" / f"{fname}.csv"
        with open(path, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        achou = False
        for r in rows:
            if _norm(r["source_value"]) == _norm(source_value) and r["mapping_status"] == "APPROVED":
                r["mapping_status"] = "DEPRECATED"
                achou = True
        if not achou:
            raise GovernanceError(f"nenhum mapeamento APPROVED para {field}={source_value}")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=HEADER)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in HEADER})
        self._log("mapping", f"{field}|{source_value}", "APPROVED", "DEPRECATED", None, rationale, by,
                  promoted_to=str(path.relative_to(self.root)))
        return path

    # --------------------------------------------------- fila de identidade
    def load_identity_queue(self, xref: pl.DataFrame, run_id: str = "") -> int:
        """Carrega para a fila os casos que a resolucao automatica NAO decidiu.

        RESOLVED nao entra: ja foi decidido por identificador exato. O que entra
        e MANUAL_REVIEW e AMBIGUOUS, que sao precisamente os casos em que o
        ADR-0004 proibe o sistema de decidir sozinho.

        Cada caso guarda o `run_id` da ultima execucao em que foi observado. A
        fila e cumulativa de proposito, porque apagar um caso pendente seria
        perder uma decisao em aberto, mas cumulativa sem marca de observacao e
        uma fila que cresce com residuo de execucoes que nao existem mais. Com
        a marca, `identity_stale` separa o que ainda esta na base do que sobrou.
        """
        now = datetime.utcnow().isoformat(timespec="seconds")
        pendentes = xref.filter(pl.col("match_status").is_in(["MANUAL_REVIEW", "AMBIGUOUS"]))
        n = 0
        for r in pendentes.to_dicts():
            did = f"{r['source_system']}|{r['source_employee_id']}"
            cur = self.conn.execute("SELECT status FROM identity_decisions WHERE decision_id=?", (did,))
            row = cur.fetchone()
            if row:
                self.conn.execute(
                    "UPDATE identity_decisions SET last_seen=?, last_run_id=? WHERE decision_id=?",
                    (now, run_id, did))
            else:
                self.conn.execute(
                    "INSERT INTO identity_decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (did, r["source_system"], str(r["source_employee_id"]), r["employee_id"],
                     r["match_method"], r["match_confidence"], "OPEN", None, None, None, None,
                     now, now, run_id))
                n += 1
        self.conn.commit()
        return n

    def identity_stale(self, run_id: str) -> pl.DataFrame:
        """Casos ainda OPEN que a execucao atual NAO observou.

        Nao sao apagados. Um caso pode sumir por motivo legitimo (a pessoa saiu
        do recorte) ou por motivo ilegitimo (a execucao anterior era de outro
        universo, como o achado 1 da F3). Os dois merecem visibilidade, e
        nenhum dos dois merece delecao silenciosa.
        """
        cur = self.conn.execute(
            "SELECT * FROM identity_decisions WHERE status='OPEN' AND "
            "(last_run_id IS NULL OR last_run_id<>?)", (run_id,))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()

    def decide_identity(self, decision_id: str, employee_id: int | None, by: str, rationale: str) -> None:
        """Decide um caso de identidade. `employee_id=None` significa
        "nao corresponde a ninguem", que e uma decisao legitima e frequente:
        terceiro de agencia na folha nao tem contraparte no HRIS."""
        if not rationale or len(rationale.strip()) < 10:
            raise GovernanceError("decisao de identidade exige justificativa")
        cur = self.conn.execute("SELECT status FROM identity_decisions WHERE decision_id=?", (decision_id,))
        row = cur.fetchone()
        if not row:
            raise GovernanceError(f"decisao inexistente: {decision_id}")
        if row[0] != "OPEN":
            raise GovernanceError(f"{decision_id} ja esta {row[0]}")
        status = "APPROVED" if employee_id is not None else "REJECTED"
        self.conn.execute(
            "UPDATE identity_decisions SET status=?, decided_employee_id=?, rationale=?, decided_by=?, "
            "decided_at=? WHERE decision_id=?",
            (status, employee_id, rationale, by, datetime.utcnow().isoformat(timespec="seconds"), decision_id))
        self.conn.commit()
        self._log("identity", decision_id, "OPEN", status,
                  str(employee_id) if employee_id is not None else None, rationale, by)

    def identity_queue(self) -> pl.DataFrame:
        cur = self.conn.execute("SELECT * FROM identity_decisions ORDER BY match_confidence DESC")
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()

    # ------------------------------------------------------------------ resumo
    def summary(self, run_id: str = "") -> dict:
        def counts(table: str, col: str = "status") -> dict:
            cur = self.conn.execute(f"SELECT {col}, COUNT(*) FROM {table} GROUP BY {col}")
            return {k: v for k, v in cur.fetchall()}
        out = {
            "mapping_exceptions": counts("mapping_exceptions"),
            "identity_decisions": counts("identity_decisions"),
            "resolution_log": self.log().height,
        }
        # so faz sentido perguntar "o que esta execucao nao observou" quando ha
        # uma execucao; sem run_id o numero seria a fila inteira, o que engana
        if run_id:
            out["identidade_nao_observada_nesta_execucao"] = self.identity_stale(run_id).height
        return out
