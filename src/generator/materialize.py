"""Materializacao do log de eventos em tabelas da camada de verdade.

O gerador simula vidas; este modulo transforma esse log nas tabelas que o
projeto usa. Escreve Parquet em `data/synthetic/truth/` (ADR-0009).

IMPORTANTE: esta e a camada de VERDADE (ADR-0001). Ela nunca e lida pelo
pipeline, so por `tests/truth/` e pelo notebook de avaliacao.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import polars as pl

from .config import Config
from .events.lifecycle import Truth

TRUTH_DIR = "data/synthetic/truth"


# --------------------------------------------------------------------------- #
def build_dim_employee(cfg: Config, truth: Truth) -> pl.DataFrame:
    """SCD2 construido a partir do state_log, com datas exatas.

    Cada mudanca de area, nivel, gestor ou local fecha a versao anterior e abre
    uma nova. Nao ha inferencia por snapshot: o log registra o estado completo
    no instante da mudanca.
    """
    rows = sorted(truth.state_log, key=lambda r: (r["employee_id"], r["effective_from"]))
    # dedupe por (employee_id, data): vence a ultima mudanca do dia
    dedup: dict[tuple[int, date], dict] = {}
    for r in rows:
        dedup[(r["employee_id"], r["effective_from"])] = r
    rows = sorted(dedup.values(), key=lambda r: (r["employee_id"], r["effective_from"]))

    out: list[dict] = []
    key = 0
    for i, r in enumerate(rows):
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        same = nxt is not None and nxt["employee_id"] == r["employee_id"]
        key += 1
        emp = truth.employees[r["employee_id"]]
        effective_to = (nxt["effective_from"] - timedelta(days=1)) if same else None
        out.append(
            dict(
                employee_key=key,
                employee_id=r["employee_id"],
                full_name=emp.full_name,
                country=r["country"],
                org_key=r["org_key"],
                business_unit=r["business_unit"],
                department=r["department"],
                sub_department=r["sub_department"],
                segment=r["segment"],
                job_family=r["job_family"],
                job_level=r["job_level"],
                job_level_group=r["job_level_group"],
                job_title=r["job_title"],
                location=r["location"],
                cost_center=r["cost_center"],
                manager_id=r["manager_id"],
                employment_type=r["employment_type"],
                employment_status=r["employment_status"],
                fte=r["fte"],
                gender=emp.gender,
                race_ethnicity=emp.race_ethnicity,
                race_declared=emp.race_declared,
                race_declared_at=emp.race_declared_at,
                disability_flag=emp.disability_flag,
                disability_declared=emp.disability_declared,
                disability_declared_at=emp.disability_declared_at,
                birth_year=emp.birth_year,
                hire_job_level=emp.hire_job_level,
                hire_job_level_group=cfg.level_group(emp.hire_job_level),
                origin=emp.origin,
                hire_date=emp.hire_date,
                termination_date=emp.termination_date,
                effective_from=r["effective_from"],
                effective_to=effective_to,
                is_current=not same,
                change_reason=r["change_reason"],
            )
        )
    return pl.DataFrame(out, infer_schema_length=None)


def build_dim_organization(cfg: Config, truth: Truth) -> pl.DataFrame:
    bus = cfg.org["business_units"]
    rows = []
    for u in truth.org_units:
        av = bus[u.business_unit].get("available_from")
        rows.append(
            dict(
                org_key=u.org_key,
                country=u.country,
                business_unit=u.business_unit,
                department=u.department,
                sub_department=u.sub_department,
                segment=u.segment,
                cost_center=u.cost_center,
                hc_weight=u.weight,
                valid_from=av or u.valid_from,
                valid_to=u.valid_to,
                is_current=True,
            )
        )
    return pl.DataFrame(rows)


def _df(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()


def build_all(cfg: Config, truth: Truth) -> dict[str, pl.DataFrame]:
    tables: dict[str, pl.DataFrame] = {
        "dim_employee": build_dim_employee(cfg, truth),
        "dim_organization": build_dim_organization(cfg, truth),
        "ref_salary_band": _df(truth.salary_bands),
        "fact_headcount_snapshot": _df(truth.snapshots),
        "fact_termination": _df(truth.terminations),
        "fact_movement": _df(truth.movements),
        "fact_compensation": _df(truth.compensation),
        "fact_performance": _df(truth.performance),
        "fact_learning": _df(truth.learning),
        "fact_engagement": _df(truth.engagement),
        "fact_requisition": _df(truth.requisitions),
        "fact_application": _df(truth.applications),
        "employee_event_log": _df(truth.events),
    }
    return tables


# --------------------------------------------------------------------------- #
def write(cfg: Config, tables: dict[str, pl.DataFrame], out_dir: str | Path | None = None) -> dict:
    """Escreve Parquet e o manifesto com hash e contagem por dataset.

    O manifesto e a prova de que a regeneracao a partir do seed e fiel
    (Technical Design R9, ADR-0001).
    """
    root = Path(out_dir) if out_dir else cfg.root / TRUTH_DIR
    root.mkdir(parents=True, exist_ok=True)

    partitioned = {"fact_headcount_snapshot": "snapshot_date",
                   "fact_learning": "enrollment_date",
                   "fact_application": "application_date"}

    manifest = {
        "seed": cfg.seed,
        "profile": cfg.profile,
        "scale": cfg.scale,
        "layer": "truth",
        "phase": "F1",
        "config_hash": config_hash(cfg),
        "datasets": {},
    }

    for name, df in tables.items():
        if df.is_empty():
            continue
        if name in partitioned and partitioned[name] in df.columns:
            col = partitioned[name]
            df = df.with_columns(pl.col(col).dt.year().alias("year"))
            for (year,), part in df.group_by(["year"], maintain_order=True):
                d = root / name / f"year={year}"
                d.mkdir(parents=True, exist_ok=True)
                part.drop("year").write_parquet(d / "part-000.parquet", compression="zstd")
            df = df.drop("year")
        else:
            d = root / name
            d.mkdir(parents=True, exist_ok=True)
            df.write_parquet(d / "part-000.parquet", compression="zstd")

        manifest["datasets"][name] = {
            "rows": df.height,
            "columns": df.width,
            "sha256": frame_hash(df),
        }

    with open(root / "manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False, default=str)
    return manifest


def frame_hash(df: pl.DataFrame) -> str:
    """Hash estavel do conteudo, sem depender de pyarrow nem de pandas.

    Usa o CSV nativo do Polars sobre a tabela inteira ordenada pelas colunas
    de identidade, para que o mesmo seed produza sempre o mesmo hash.
    """
    h = hashlib.sha256()
    h.update(",".join(df.columns).encode())
    h.update(str(df.height).encode())
    h.update(df.write_csv().encode())
    return h.hexdigest()[:16]


def config_hash(cfg: Config) -> str:
    payload = json.dumps(
        {"generation": cfg.generation, "incidents": cfg.incidents, "sources": cfg.sources},
        sort_keys=True, default=str,
    ).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def write_samples(cfg: Config, tables: dict[str, pl.DataFrame], n: int = 1000) -> Path:
    """Amostra versionavel no Git (ADR-0014, `data/samples/`)."""
    d = cfg.root / "data" / "samples" / "truth"
    d.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        if df.is_empty():
            continue
        df.head(n).write_csv(d / f"{name}.csv")
    return d
