"""Comparacao entre a camada de verdade e o resultado do pipeline.

Este modulo e a razao de existir do ADR-0001. Ele mede quanto da realidade o
pipeline recuperou, e onde perdeu, usando o gabarito que nenhum projeto de
portfolio tem.

Regra de isolamento: a verdade e lida SO aqui e em `tests/`. Nenhum modulo do
pipeline importa este arquivo, e este arquivo nao escreve em nenhuma camada de
dados; ele produz apenas um relatorio.

Leitura correta dos numeros: a F3 **nao corrige** nada. O que se mede aqui e
quanto da verdade ficou recuperavel depois de padronizacao e DE/PARA, e quanto
segue bloqueado esperando decisao humana. Um numero baixo em VivaMarket nao e
falha do pipeline, e o comportamento projetado no ADR-0004.
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

from generator.config import Config

TRUTH = "data/synthetic/truth"


def load_truth(cfg: Config) -> dict[str, pl.DataFrame]:
    base = Path(cfg.root) / TRUTH
    out: dict[str, pl.DataFrame] = {}
    for name in ("dim_employee", "fact_headcount_snapshot", "defect_ledger"):
        d = base / name
        if not d.exists():
            continue
        parts = sorted(d.rglob("*.parquet"))
        if parts:
            out[name] = pl.concat([pl.read_parquet(p) for p in parts], how="vertical_relaxed")
    return out


def _recovery(conf: pl.DataFrame, id_col: str, std_col: str,
              truth_current: pl.DataFrame, truth_col: str) -> dict:
    if conf is None or std_col not in conf.columns:
        return {}
    sub = conf.select([id_col, std_col]).drop_nulls()
    sub = sub.with_columns(pl.col(id_col).cast(pl.Int64, strict=False).alias("_eid")).drop_nulls("_eid")
    j = sub.join(truth_current.select(["employee_id", truth_col]), left_on="_eid", right_on="employee_id", how="inner")
    if j.is_empty():
        return {"comparados": 0}
    igual = j.filter(pl.col(std_col) == pl.col(truth_col)).height
    unmapped = j.filter(pl.col(std_col) == "UNMAPPED").height
    return {
        "comparados": j.height,
        "recuperados": igual,
        "taxa_recuperacao": round(igual / j.height, 4),
        "unmapped": unmapped,
        "taxa_unmapped": round(unmapped / j.height, 4),
        "divergentes": j.height - igual - unmapped,
    }


def compare(cfg: Config, conformed: dict[tuple[str, str], pl.DataFrame],
            analytical: dict[tuple[str, str], pl.DataFrame], xref: pl.DataFrame) -> dict:
    truth = load_truth(cfg)
    if "dim_employee" not in truth:
        return {"erro": "camada de verdade ausente; rode a F1 antes"}

    cur = truth["dim_employee"].filter(pl.col("is_current"))
    out: dict = {}

    # ------------------------------------------------- campos padronizados
    leg = conformed.get(("HRIS_LEGACY", "employee_master"))
    core = conformed.get(("HRIS_CORE", "employee_master"))
    out["campos"] = {
        "HRIS_LEGACY.gender": _recovery(leg, "MATRICULA", "std_gender", cur, "gender"),
        "HRIS_LEGACY.department": _recovery(leg, "MATRICULA", "std_department", cur, "department"),
        "HRIS_LEGACY.job_level": _recovery(leg, "MATRICULA", "std_job_level", cur, "job_level"),
        "HRIS_CORE.department": _recovery(core, "employee_id", "std_department", cur, "department"),
        "HRIS_CORE.country": _recovery(core, "employee_id", "std_country", cur, "country"),
    }

    # ------------------------------------------- aquisicao, via gabarito
    # A VivaMarket nao tem employee_id (defeito D05). Para MEDIR, usamos o
    # ledger, que e gabarito e nao pipeline: o pipeline continua sem saber.
    viva = conformed.get(("VIVAMARKET_LEGACY", "employee_master"))
    if viva is not None and "defect_ledger" in truth:
        led = truth["defect_ledger"].filter(
            (pl.col("defect_id") == "D05") & (pl.col("source_system") == "VIVAMARKET_LEGACY"))
        mapa = led.select([pl.col("record_key").alias("COD_FUNC"),
                           pl.col("truth_value").cast(pl.Int64, strict=False).alias("_eid")])
        j = viva.select(["COD_FUNC", "std_job_level", "std_gender", "std_department"]).join(
            mapa, on="COD_FUNC", how="inner").join(
            cur.select(["employee_id", "job_level", "gender", "department"]),
            left_on="_eid", right_on="employee_id", how="inner")
        if not j.is_empty():
            out["aquisicao_vivamarket"] = {
                "comparados": j.height,
                "job_level_recuperado": round(j.filter(pl.col("std_job_level") == pl.col("job_level")).height / j.height, 4),
                "job_level_unmapped": round(j.filter(pl.col("std_job_level") == "UNMAPPED").height / j.height, 4),
                "gender_recuperado": round(j.filter(pl.col("std_gender") == pl.col("gender")).height / j.height, 4),
                "department_recuperado": round(j.filter(pl.col("std_department") == pl.col("department")).height / j.height, 4),
            }

    # ----------------------------------------------------------- headcount
    snap_truth = truth.get("fact_headcount_snapshot")
    snap_conf = analytical.get(("HRIS_CORE", "headcount_snapshot"))
    if snap_truth is not None and snap_conf is not None and "snapshot_date__iso" in snap_conf.columns:
        t = (snap_truth.with_columns(pl.col("snapshot_date").cast(pl.Utf8).str.slice(0, 7).alias("mes"))
             .group_by("mes").len().rename({"len": "verdade"}))
        c = (snap_conf.filter(pl.col("snapshot_date__iso").is_not_null())
             .with_columns(pl.col("snapshot_date__iso").str.slice(0, 7).alias("mes"))
             .group_by("mes").len().rename({"len": "pipeline"}))
        # cast explicito: contagem vem como u32 e a subtracao negativa daria
        # underflow silencioso, virando um numero gigante em vez de negativo
        j = (t.join(c, on="mes", how="inner")
             .with_columns([pl.col("verdade").cast(pl.Int64), pl.col("pipeline").cast(pl.Int64)])
             .with_columns(((pl.col("pipeline") - pl.col("verdade")) / pl.col("verdade")).alias("desvio")))
        if not j.is_empty():
            out["headcount"] = {
                "meses_comparados": j.height,
                "desvio_medio_abs": round(float(j["desvio"].abs().mean()), 5),
                "desvio_max_abs": round(float(j["desvio"].abs().max()), 5),
                "pior_mes": j.sort(pl.col("desvio").abs(), descending=True).head(1).to_dicts()[0],
            }

    # ------------------------------------------------------------ gestores
    if core is not None and "manager_id" in core.columns:
        ids = set(core["employee_id"].drop_nulls().to_list())
        orf = core.filter(pl.col("manager_id").is_not_null() & ~pl.col("manager_id").is_in(list(ids)))
        out["gestores"] = {
            "registros": core.height,
            "orfaos_remanescentes": orf.height,
            "taxa": round(orf.height / core.height, 5) if core.height else 0.0,
            "nota": "a F3 nao corrige; orfao permanece e alimenta o check DQ_REF_001",
        }

    # ------------------------------------------------------------ identidade
    if xref is not None and not xref.is_empty():
        viva_x = xref.filter(pl.col("source_system") == "VIVAMARKET_LEGACY")
        out["identidade_aquisicao"] = {
            "registros": viva_x.height,
            "resolvidos_automaticamente": viva_x.filter(pl.col("match_status") == "RESOLVED").height,
            "para_revisao_humana": viva_x.filter(pl.col("match_status") == "MANUAL_REVIEW").height,
            "ambiguos": viva_x.filter(pl.col("match_status") == "AMBIGUOUS").height,
            "nota": "zero resolucao automatica e o comportamento projetado no ADR-0004, nao uma falha",
        }
    return out
