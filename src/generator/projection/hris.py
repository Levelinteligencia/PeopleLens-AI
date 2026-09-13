"""Projecao nos dois HRIS: o legado nacional e o corporativo global."""
from __future__ import annotations

from datetime import date

import polars as pl

from ..defects import injectors as inj
from ..defects.catalog import Catalog
from .base import Context, write_csv, write_parquet

LEGACY = "HRIS_LEGACY"
CORE = "HRIS_CORE"


def _window(cfg, code) -> tuple[date, date]:
    s = cfg.sources["systems"][code]
    _, end = cfg.period
    return s["active_from"], s["active_to"] or end


# --------------------------------------------------------------------------- #
def project_legacy(ctx: Context, cat: Catalog) -> dict[str, int]:
    cfg = ctx.cfg
    start, end = _window(cfg, LEGACY)
    sysmeta = ctx.system(LEGACY)
    fmt = sysmeta["date_format"]
    countries = sysmeta["countries"]
    rng = ctx.rng.get("proj_legacy")

    emp = ctx.tables["dim_employee"].filter(pl.col("is_current"))
    known = emp["employee_id"].to_list()

    # D07 vale para 100% das datas do sistema: e propriedade do formato, nao
    # sorteio por registro. Fica um registro por dataset no ledger.
    for ds in ("employee_master", "headcount_snapshot", "movement"):
        ctx.ledger.record("D07", LEGACY, ds, "-", "todas as datas", "ISO 8601", fmt)

    # D22 tem contagem absoluta, nao taxa: sorteamos quantos vinculos viram
    # cadastro novo em vez de reabertura.
    d22_alvo = cat["D22"].absolute_count(cfg.scale) or 0

    # -------- employee_master --------
    pop = emp.filter(pl.col("country").is_in(countries) & (pl.col("hire_date") <= end)
                     & (pl.col("termination_date").is_null() | (pl.col("termination_date") >= start)))
    rows, dups = [], []
    for e in pop.to_dicts():
        key = e["employee_id"]
        dept = e["department"]
        if ctx.hit(cat, "D04", LEGACY, "employee_master"):
            novo = inj.department_alias(rng, dept)
            if novo != dept:
                ctx.ledger.record("D04", LEGACY, "employee_master", key, "DEPARTAMENTO", dept, novo)
                dept = novo

        adm = inj.format_date(e["hire_date"], fmt)
        if ctx.hit(cat, "D08", LEGACY, "employee_master"):
            ruim = inj.impossible_date(rng, e["hire_date"], fmt)
            ctx.ledger.record("D08", LEGACY, "employee_master", key, "DT_ADMISSAO", adm, ruim)
            adm = ruim

        gestor = e["manager_id"]
        if ctx.hit(cat, "D09", LEGACY, "employee_master", when=e["hire_date"]):
            falso = inj.orphan_manager_id(rng, known)
            ctx.ledger.record("D09", LEGACY, "employee_master", key, "GESTOR", gestor, falso)
            gestor = falso

        nome = inj.mojibake(e["full_name"])
        if nome != e["full_name"]:
            ctx.ledger.record("D23", LEGACY, "employee_master", key, "NOME", e["full_name"], nome)

        sexo = inj.LEGACY_GENDER.get(e["gender"], "")
        ctx.ledger.record("D01", LEGACY, "employee_master", key, "SEXO", e["gender"], sexo)

        row = {
            "MATRICULA": key, "NOME": nome, "SEXO": sexo,
            "DT_ADMISSAO": adm,
            "DT_DEMISSAO": inj.format_date(e["termination_date"], fmt) if e["termination_date"] and e["termination_date"] <= end else None,
            "SITUACAO": "ATIVO" if (e["termination_date"] is None or e["termination_date"] > end) else "DEMITIDO",
            "DEPARTAMENTO": inj.mojibake(dept), "CARGO": inj.mojibake(e["job_title"]),
            "NIVEL": e["job_level"], "GESTOR": gestor,
            "CENTRO_CUSTO": e["cost_center"], "LOCAL": e["location"], "PAIS": e["country"],
            "TIPO_CONTRATO": e["employment_type"], "JORNADA": e["fte"],
        }
        rows.append(row)
        # D22: recontratacao vira cadastro novo em vez de reabrir o vinculo
        if (e["termination_date"] and e["termination_date"] <= end
                and len(dups) < d22_alvo and rng.random() < 0.5):
            novo_key = 800000 + key
            dup = inj.duplicate_row(row, novo_key, "MATRICULA")
            dup["DT_DEMISSAO"] = None
            dup["SITUACAO"] = "ATIVO"
            ctx.ledger.record("D22", LEGACY, "employee_master", novo_key, "MATRICULA", key, novo_key)
            dups.append(dup)
    rows.extend(dups)
    ctx.ledger.record("D02", LEGACY, "employee_master", "-", "race_ethnicity", "campo existe na verdade", "coluna ausente no sistema")
    write_csv(ctx.out_dir(LEGACY, "employee_master", end), rows,
              encoding=sysmeta["encoding"], delimiter=sysmeta["delimiter"], system=LEGACY, ingestion=end)

    # -------- headcount_snapshot --------
    snap = ctx.tables["fact_headcount_snapshot"].filter(
        pl.col("country").is_in(countries) & (pl.col("snapshot_date") >= start) & (pl.col("snapshot_date") <= end)
    )
    srows = []
    for s in snap.to_dicts():
        dept = s["department"]
        if ctx.hit(cat, "D04", LEGACY, "headcount_snapshot"):
            novo = inj.department_alias(rng, dept)
            if novo != dept:
                ctx.ledger.record("D04", LEGACY, "headcount_snapshot",
                                  f"{s['employee_id']}|{s['snapshot_date']}", "DEPARTAMENTO", dept, novo)
                dept = novo
        gestor = s["manager_id"]
        if ctx.hit(cat, "D09", LEGACY, "headcount_snapshot", when=s["snapshot_date"]):
            gestor = inj.orphan_manager_id(rng, known)
            ctx.ledger.record("D09", LEGACY, "headcount_snapshot",
                              f"{s['employee_id']}|{s['snapshot_date']}", "GESTOR", s["manager_id"], gestor)
        srows.append({
            "MATRICULA": s["employee_id"],
            "DT_REFERENCIA": inj.format_date(s["snapshot_date"], fmt),
            "SITUACAO": "ATIVO", "DEPARTAMENTO": inj.mojibake(dept),
            "NIVEL": s["job_level"], "GESTOR": gestor, "PAIS": s["country"],
            "JORNADA": inj.decimal_br(s["fte"]),
        })
    write_csv(ctx.out_dir(LEGACY, "headcount_snapshot", end), srows,
              encoding=sysmeta["encoding"], delimiter=sysmeta["delimiter"], system=LEGACY, ingestion=end)

    # -------- movement --------
    mov = ctx.tables["fact_movement"].filter(
        (pl.col("movement_date") >= start) & (pl.col("movement_date") <= end) & pl.col("country").is_in(countries)
    )
    mrows = [{
        "MATRICULA": m["employee_id"], "DT_MOVIMENTO": inj.format_date(m["movement_date"], fmt),
        "TIPO": {"Promotion": "PROMOCAO", "Transfer": "TRANSFERENCIA", "Lateral Move": "MOV LATERAL",
                 "Demotion": "REBAIXAMENTO", "Reorganization": "REESTRUTURACAO"}.get(m["movement_type"], m["movement_type"]),
        "DEPTO_ANTERIOR": inj.mojibake(m["old_department"]), "DEPTO_NOVO": inj.mojibake(m["new_department"]),
        "NIVEL_ANTERIOR": m["old_job_level"], "NIVEL_NOVO": m["new_job_level"],
    } for m in mov.to_dicts()]
    write_csv(ctx.out_dir(LEGACY, "movement", end), mrows,
              encoding=sysmeta["encoding"], delimiter=sysmeta["delimiter"], system=LEGACY, ingestion=end)

    return {"employee_master": len(rows), "headcount_snapshot": len(srows), "movement": len(mrows)}


# --------------------------------------------------------------------------- #
def project_core(ctx: Context, cat: Catalog) -> dict[str, int]:
    cfg = ctx.cfg
    start, end = _window(cfg, CORE)
    sysmeta = ctx.system(CORE)
    fmt = sysmeta["date_format"]
    rng = ctx.rng.get("proj_core")
    overlap = cat["D01"].spec["scope"]["date_range"]

    emp = ctx.tables["dim_employee"].filter(pl.col("is_current"))
    known = emp["employee_id"].to_list()
    all_countries = [c["code"] for c in cfg.countries]

    pop = emp.filter((pl.col("hire_date") <= end) &
                     (pl.col("termination_date").is_null() | (pl.col("termination_date") >= start)))
    rows = []
    for e in pop.to_dicts():
        key = e["employee_id"]
        # D01: durante a janela de sobreposicao o dominio antigo ainda chega
        gender = e["gender"]
        ref = max(e["hire_date"], start)
        if overlap[0] <= ref <= overlap[1]:
            gender = inj.LEGACY_GENDER.get(e["gender"], "")
            ctx.ledger.record("D01", CORE, "employee_master", key, "gender", e["gender"], gender)

        country = e["country"]
        if ctx.hit(cat, "D19", CORE, "employee_master"):
            country = inj.swap_country(rng, country, all_countries)
            ctx.ledger.record("D19", CORE, "employee_master", key, "country", e["country"], country)

        manager = e["manager_id"]
        if ctx.hit(cat, "D09", CORE, "employee_master", when=ref):
            manager = inj.orphan_manager_id(rng, known)
            ctx.ledger.record("D09", CORE, "employee_master", key, "manager_id", e["manager_id"], manager)

        # D03 nao e injetado: a nao declaracao ja e fato do mundo. Fica
        # registrada como observada para que o gabarito conheca o caso.
        if e["race_declared"] is False and e["race_declared_at"] is not None:
            ctx.ledger.record("D03", CORE, "employee_master", key, "race_ethnicity",
                              "nao declarado", e["race_ethnicity"])

        rows.append({
            "employee_id": key, "source_employee_id": f"WD{key:07d}", "full_name": e["full_name"],
            "gender": gender,
            "race_ethnicity": e["race_ethnicity"] if e["race_declared_at"] else None,
            "disability_flag": e["disability_flag"],
            "hire_date": inj.format_date(e["hire_date"], fmt),
            "termination_date": inj.format_date(e["termination_date"], fmt) if e["termination_date"] and e["termination_date"] <= end else None,
            "employment_status": "Active" if (e["termination_date"] is None or e["termination_date"] > end) else "Terminated",
            "business_unit": e["business_unit"], "department": e["department"],
            "sub_department": e["sub_department"], "job_family": e["job_family"],
            "job_level": e["job_level"], "job_title": e["job_title"],
            "manager_id": manager, "cost_center": e["cost_center"], "location": e["location"],
            "country": country, "employment_type": e["employment_type"], "fte": e["fte"],
        })
    write_csv(ctx.out_dir(CORE, "employee_master", end), rows,
              encoding=sysmeta["encoding"], delimiter=sysmeta["delimiter"], system=CORE, ingestion=end)

    # -------- headcount_snapshot em parquet --------
    snap = ctx.tables["fact_headcount_snapshot"].filter(
        (pl.col("snapshot_date") >= start) & (pl.col("snapshot_date") <= end))
    srows = []
    for s in snap.to_dicts():
        manager = s["manager_id"]
        if ctx.hit(cat, "D09", CORE, "headcount_snapshot", when=s["snapshot_date"]):
            manager = inj.orphan_manager_id(rng, known)
            ctx.ledger.record("D09", CORE, "headcount_snapshot",
                              f"{s['employee_id']}|{s['snapshot_date']}", "manager_id", s["manager_id"], manager)
        srows.append({k: s[k] for k in ("employee_id", "snapshot_date", "active_flag", "fte", "country",
                                        "business_unit", "department", "sub_department", "job_family",
                                        "job_level", "location", "employment_type")} | {"manager_id": manager})
    write_parquet(ctx.out_dir(CORE, "headcount_snapshot", end), srows, system=CORE, ingestion=end)

    # -------- performance --------
    perf = ctx.tables["fact_performance"].filter((pl.col("review_date") >= start))
    prows = [{
        "employee_id": p["employee_id"], "review_cycle": p["review_cycle"],
        "review_date": inj.format_date(p["review_date"], fmt),
        "performance_rating": p["performance_rating_recorded"],
        "potential_rating": p["potential_rating"],
        "promotion_ready_flag": p["promotion_ready_flag"], "manager_id": p["manager_id"],
    } for p in perf.to_dicts()]
    ctx.ledger.record("D_DEFINITION_DRIFT", CORE, "performance", "-", "performance_rating",
                      "escala canonica de 5 pontos", "1 a 5 ate 2020, textual a partir de 2021")
    write_csv(ctx.out_dir(CORE, "performance", end), prows,
              encoding=sysmeta["encoding"], delimiter=sysmeta["delimiter"], system=CORE, ingestion=end)

    # -------- movement --------
    mov = ctx.tables["fact_movement"].filter(pl.col("movement_date") >= start)
    mrows = [{
        "employee_id": m["employee_id"], "movement_date": inj.format_date(m["movement_date"], fmt),
        "movement_type": m["movement_type"], "old_department": m["old_department"],
        "new_department": m["new_department"], "old_job_level": m["old_job_level"],
        "new_job_level": m["new_job_level"], "old_manager_id": m["old_manager_id"],
        "new_manager_id": m["new_manager_id"], "old_location": m["old_location"],
        "new_location": m["new_location"],
    } for m in mov.to_dicts()]
    write_csv(ctx.out_dir(CORE, "movement", end), mrows,
              encoding=sysmeta["encoding"], delimiter=sysmeta["delimiter"], system=CORE, ingestion=end)

    return {"employee_master": len(rows), "headcount_snapshot": len(srows),
            "performance": len(prows), "movement": len(mrows)}
