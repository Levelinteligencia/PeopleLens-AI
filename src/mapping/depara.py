"""Camada de DE/PARA e fila de excecoes.

O coracao do projeto, e a regra e uma so (principio 5 da Especificacao,
Technical Design R4):

    **nada e corrigido automaticamente.**

Confianca alta melhora a SUGESTAO que o humano vai aprovar, e nunca autoriza a
aplicacao. O motivo e o custo assimetrico: um valor nao mapeado e visivel, entra
na fila, derruba o trust score e sai do numerador. Um valor mapeado errado e
invisivel, entra na conta com cara de dado bom e nao deixa rastro.

Arquitetura (ADR-0009):
- mapeamento APROVADO: CSV versionado em `data/reference/`, o Git e a trilha;
- fila de excecoes: SQLite em `data/governance/`, porque tem escrita.
"""
from __future__ import annotations

import csv
import sqlite3
import unicodedata
from datetime import datetime
from . import similarity
from pathlib import Path

import polars as pl

from generator.config import Config

UNMAPPED = "UNMAPPED"
GOV_DB = "data/governance/peoplelens_gov.db"

# campo padronizado -> arquivo de referencia
FIELDS = {
    "gender": "ref_gender_mapping",
    "country": "ref_country_mapping",
    "job_level": "ref_job_level_mapping",
    "department": "ref_department_mapping",
    "performance_rating": "ref_performance_rating_mapping",
}

# Especificacao por dataset: de qual coluna sai cada campo padronizado, e qual
# coluna da a DATA DE REFERENCIA do registro.
#
# A data importa porque mapeamento tem vigencia. `3` em performance_rating
# significa "Meets Expectations" ate 2020 e nao significa nada a partir de 2021,
# quando a escala virou textual. Aplicar o mapa sem olhar a data reescreveria a
# historia (defeito D_DEFINITION_DRIFT).
DATASET_SPEC: dict[str, dict] = {
    "HRIS_LEGACY.employee_master": {
        "date": "DT_ADMISSAO__iso",
        "fields": {"SEXO": "gender", "PAIS": "country", "NIVEL": "job_level", "DEPARTAMENTO": "department"},
    },
    "HRIS_LEGACY.headcount_snapshot": {
        "date": "DT_REFERENCIA__iso",
        "fields": {"PAIS": "country", "NIVEL": "job_level", "DEPARTAMENTO": "department"},
    },
    "HRIS_CORE.employee_master": {
        "date": "hire_date__iso",
        "fields": {"gender": "gender", "country": "country", "job_level": "job_level", "department": "department"},
    },
    "HRIS_CORE.headcount_snapshot": {
        "date": "snapshot_date__iso",
        "fields": {"country": "country", "job_level": "job_level", "department": "department"},
    },
    "HRIS_CORE.performance": {
        "date": "review_date__iso",
        "fields": {"performance_rating": "performance_rating"},
    },
    "VIVAMARKET_LEGACY.employee_master": {
        "date": "DT_ADM__iso",
        "fields": {"SEXO": "gender", "PAIS": "country", "NIVEL": "job_level", "DEPTO": "department"},
    },
    "PAYROLL_BR.payroll_headcount_snapshot": {
        "date": "dt_competencia__iso",
        "fields": {"pais": "country"},
    },
    "ATS_CLOUD.requisition": {
        "date": "opening_date__iso",
        "fields": {"org_country": "country", "org_job_level": "job_level", "org_department": "department"},
    },
}

# --------------------------------------------------------------------------- #
def _norm(v: str) -> str:
    """Chave de comparacao: sem acento, sem caixa, sem pontuacao de borda.

    Usada APENAS para procurar candidato. O valor original e o que vai para a
    fila de excecoes, porque e ele que o humano precisa ver.
    """
    s = unicodedata.normalize("NFKD", v or "").encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace(".", " ").replace("&", " e ").split())


def load_approved(cfg: Config) -> dict[str, dict[str, list[dict]]]:
    """Mapeamentos APROVADOS, indexados por chave normalizada.

    O valor e uma LISTA porque o mesmo valor de origem pode ter traducoes
    diferentes em janelas de vigencia diferentes. Guardar so a ultima
    apagaria a historia.
    """
    base = Path(cfg.root) / "data" / "reference"
    out: dict[str, dict[str, list[dict]]] = {}
    for field, fname in FIELDS.items():
        path = base / f"{fname}.csv"
        table: dict[str, list[dict]] = {}
        if path.exists():
            with open(path, encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    if r["mapping_status"] != "APPROVED":
                        continue
                    table.setdefault(_norm(r["source_value"]), []).append(r)
        out[field] = table
    return out


def lookup(table: dict[str, list[dict]], value: str, ref_date: str | None) -> dict | None:
    """Encontra o mapeamento vigente na data de referencia do registro.

    Sem data, so vale mapeamento sem vigencia fechada. Isso e conservador de
    proposito: na duvida sobre quando o registro aconteceu, nao se aplica um
    mapa que vale so num periodo.
    """
    candidatos = table.get(_norm(value))
    if not candidatos:
        return None
    for r in candidatos:
        vf, vt = (r.get("valid_from") or ""), (r.get("valid_to") or "")
        if ref_date is None:
            if not vt:
                return r
            continue
        if vf and ref_date < vf:
            continue
        if vt and ref_date > vt:
            continue
        return r
    return None


def suggest(value: str, approved: dict[str, list[dict]]) -> tuple[str | None, float, str]:
    """Sugere o valor padrao mais provavel, e diz por qual criterio.

    Sugerir nao e aplicar. Mas sugestao ruim tem custo: uma fila de excecoes com
    candidatos obviamente errados e uma fila que ninguem trabalha, e isso
    aumenta a pressao para aprovar em bloco. O criterio vencedor vai junto para
    que quem decide saiba se o candidato veio de sigla, prefixo, tokens ou
    similaridade de caractere.
    """
    alvos = {r[0]["source_value"]: r[0]["standard_value"] for r in approved.values()} if False else {}
    for chave, rows in approved.items():
        alvos[rows[0]["source_value"]] = rows[0]["standard_value"]
    ranked = similarity.rank(value, alvos, top=1)
    if not ranked:
        return None, 0.0, "nenhum"
    c = ranked[0]
    return c.value, round(c.score, 3), c.method


# --------------------------------------------------------------------------- #
class ExceptionQueue:
    """Fila de excecoes de mapeamento, em SQLite (ADR-0009)."""

    def __init__(self, root: Path) -> None:
        self.path = Path(root) / GOV_DB
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS mapping_exceptions (
                exception_id     TEXT PRIMARY KEY,
                source_system    TEXT NOT NULL,
                source_field     TEXT NOT NULL,
                source_value     TEXT NOT NULL,
                suggested_value  TEXT,
                confidence_score REAL,
                suggestion_method TEXT,
                occurrence_count INTEGER NOT NULL,
                first_seen       TEXT,
                last_seen        TEXT,
                status           TEXT NOT NULL,
                resolution       TEXT,
                resolved_by      TEXT,
                resolved_at      TEXT
            )""")
        self.conn.commit()

    def upsert(self, system: str, field: str, value: str, suggested: str | None,
               confidence: float, n: int, when: str, method: str = "") -> None:
        eid = f"{system}|{field}|{value}"
        cur = self.conn.execute("SELECT occurrence_count, first_seen, status FROM mapping_exceptions WHERE exception_id=?", (eid,))
        row = cur.fetchone()
        if row:
            self.conn.execute(
                "UPDATE mapping_exceptions SET occurrence_count=?, last_seen=?, suggested_value=?, "
                "confidence_score=?, suggestion_method=? WHERE exception_id=?",
                (row[0] + n, when, suggested, confidence, method, eid))
        else:
            self.conn.execute(
                "INSERT INTO mapping_exceptions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (eid, system, field, value, suggested, confidence, method, n, when, when,
                 "OPEN", None, None, None))
        self.conn.commit()

    def frame(self) -> pl.DataFrame:
        cur = self.conn.execute("SELECT * FROM mapping_exceptions ORDER BY occurrence_count DESC")
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()

    def reset(self) -> None:
        """Prepara a fila para uma nova execucao SEM apagar decisao de governanca.

        Apagar a tabela inteira, que era o comportamento da F3, perderia o
        estado de governanca: um valor REJECTED voltaria a aparecer como OPEN
        na execucao seguinte, e rejeitar viraria sinonimo de esquecer. O
        historico em `resolution_log` sobreviveria, mas a fila mentiria.

        Entao: excecoes ainda OPEN somem, porque vao ser recontadas do zero;
        as que tem decisao humana (UNDER_REVIEW, APPROVED, REJECTED) ficam,
        com a contagem zerada para que a nova execucao recomece a contar.
        """
        self.conn.execute("DELETE FROM mapping_exceptions WHERE status='OPEN'")
        self.conn.execute("UPDATE mapping_exceptions SET occurrence_count=0")
        self.conn.commit()

    def open_frame(self) -> pl.DataFrame:
        f = self.frame()
        return f if f.is_empty() else f.filter(pl.col("status") == "OPEN")


# --------------------------------------------------------------------------- #
def apply_all(cfg: Config, std: dict[tuple[str, str], pl.DataFrame], lineage,
              queue: ExceptionQueue) -> tuple[dict[tuple[str, str], pl.DataFrame], dict]:
    approved = load_approved(cfg)
    when = datetime.utcnow().isoformat(timespec="seconds")
    stats = {f: {"mapped": 0, "unmapped": 0, "distinct_unmapped": set()} for f in FIELDS}
    out: dict[tuple[str, str], pl.DataFrame] = {}

    for (system, dataset), df in std.items():
        spec = DATASET_SPEC.get(f"{system}.{dataset}")
        if not spec:
            out[(system, dataset)] = df
            continue
        cols = spec["fields"]
        date_col = spec.get("date")
        frame = df
        datas = (frame[date_col].to_list() if date_col and date_col in frame.columns
                 else [None] * frame.height)
        pendentes: dict[tuple[str, str], int] = {}
        for src_col, field in cols.items():
            if src_col not in frame.columns:
                continue
            table = approved[field]
            novo, rules_hit = [], []
            for rid, raw, ref_date in zip(frame["_row_id"].to_list(), frame[src_col].to_list(), datas):
                if raw is None:
                    novo.append(None)
                    rules_hit.append(None)
                    continue
                hit = lookup(table, raw, ref_date)
                if hit:
                    novo.append(hit["standard_value"])
                    rules_hit.append(hit["mapping_id"])
                    stats[field]["mapped"] += 1
                    if hit["standard_value"] != raw:
                        lineage.value("L2", system, dataset, rid, src_col, raw,
                                      hit["standard_value"], f"DEPARA:{hit['mapping_id']}")
                else:
                    novo.append(UNMAPPED)
                    rules_hit.append(None)
                    stats[field]["unmapped"] += 1
                    stats[field]["distinct_unmapped"].add(raw)
                    pendentes[(field, raw)] = pendentes.get((field, raw), 0) + 1
                    lineage.value("L2", system, dataset, rid, src_col, raw, UNMAPPED, "DEPARA:UNMAPPED")
            frame = frame.with_columns([
                pl.Series(f"std_{field}", novo, dtype=pl.Utf8),
                pl.Series(f"std_{field}__mapping_id", rules_hit, dtype=pl.Utf8),
            ])

        for (field, raw), n in pendentes.items():
            sug, conf, metodo = suggest(raw, approved[field])
            queue.upsert(system, field, raw, sug, conf, n, when, metodo)

        out[(system, dataset)] = frame
        lineage.object("dataset", f"conformed.{system}.{dataset}", "dataset",
                       f"standardized.{system}.{dataset}",
                       "aplicacao de DE/PARA aprovado; desconhecido vira UNMAPPED e vai para excecao",
                       rows=frame.height)

    resumo = {f: {"mapped": v["mapped"], "unmapped": v["unmapped"],
                  "distinct_unmapped": len(v["distinct_unmapped"]),
                  "unmapped_rate": round(v["unmapped"] / max(1, v["mapped"] + v["unmapped"]), 4)}
              for f, v in stats.items()}
    return out, resumo
