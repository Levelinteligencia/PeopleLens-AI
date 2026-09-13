"""Projecao no sistema legado da VivaMarket (carga unica de ago/2022).

Este e o sistema com pior qualidade da onda 1, de proposito. Ele carrega sete
defeitos ao mesmo tempo e e a principal fonte de trabalho para a camada de
DE/PARA e para a resolucao de identidade (ADR-0004).

Sobre o formato: `sources.yaml` declara xlsx com encoding latin-1. Planilha nao
tem encoding de arquivo. O que acontece de verdade, e o que e reproduzido aqui,
e o dano chegar ja gravado nos VALORES, vindo da exportacao do sistema de
origem. O arquivo e xlsx legitimo com texto corrompido dentro.
"""
from __future__ import annotations

import polars as pl

from ..defects import injectors as inj
from ..defects.catalog import Catalog
from .base import Context, write_xlsx

SYS = "VIVAMARKET_LEGACY"


def project(ctx: Context, cat: Catalog) -> dict[str, int]:
    cfg = ctx.cfg
    sysmeta = ctx.system(SYS)
    fmt = sysmeta["date_format"]
    load_date = sysmeta["active_from"]
    rng = ctx.rng.get("proj_vivamarket")

    emp = ctx.tables["dim_employee"].filter(pl.col("is_current"))
    pop = emp.filter(pl.col("origin") == "acquisition_vivamarket")
    outros = emp.filter(pl.col("origin") != "acquisition_vivamarket")["employee_id"].to_list()

    level_map = inj.vivamarket_level_map(list(cfg.org["job_levels"]))
    scale = sysmeta["job_level_scale"]
    d06_total = cat["D06"].absolute_count(cfg.scale) or 0
    collide = set(rng.choice(pop["employee_id"].to_list(),
                             size=min(d06_total, pop.height), replace=False).tolist()) if pop.height else set()

    comp = ctx.tables["fact_compensation"]
    salario = {c["employee_id"]: c["base_salary"] for c in comp.sort("effective_date").to_dicts()}
    moeda = {c["employee_id"]: c["currency"] for c in comp.sort("effective_date").to_dicts()}

    ctx.ledger.record("D07", SYS, "employee_master", "-", "todas as datas", "ISO 8601", fmt)

    rows = []
    for e in pop.to_dicts():
        key = e["employee_id"]
        # D05: o sistema nao conhece o employee_id corporativo
        cod = 10000 + (key % 90000)
        if key in collide:
            cod = int(inj.colliding_id(rng, outros)) if outros else cod
            ctx.ledger.record("D06", SYS, "employee_master", cod, "COD_FUNC", key, cod)
        ctx.ledger.record("D05", SYS, "employee_master", cod, "employee_id", key, None)

        adm = inj.format_date(e["hire_date"], fmt)
        if ctx.hit(cat, "D08", SYS, "employee_master"):
            ruim = inj.impossible_date(rng, e["hire_date"], fmt)
            ctx.ledger.record("D08", SYS, "employee_master", cod, "DT_ADM", adm, ruim)
            adm = ruim

        gestor = e["manager_id"]
        if ctx.hit(cat, "D09", SYS, "employee_master", when=load_date):
            gestor = inj.orphan_manager_id(rng, [])
            ctx.ledger.record("D09", SYS, "employee_master", cod, "GESTOR", e["manager_id"], gestor)

        nivel = inj.foreign_level(e["job_level"], scale, level_map)
        ctx.ledger.record("D12", SYS, "employee_master", cod, "NIVEL", e["job_level"], nivel)

        nome = inj.mojibake(e["full_name"])
        if nome != e["full_name"]:
            ctx.ledger.record("D23", SYS, "employee_master", cod, "NOME", e["full_name"], nome)
        depto = inj.mojibake(inj.department_alias(rng, e["department"]))
        if depto != e["department"]:
            ctx.ledger.record("D04", SYS, "employee_master", cod, "DEPTO", e["department"], depto)

        sexo = inj.VIVA_GENDER.get(e["gender"], "")
        ctx.ledger.record("D01", SYS, "employee_master", cod, "SEXO", e["gender"], sexo)

        rows.append({
            "COD_FUNC": cod, "NOME": nome, "SEXO": sexo, "DT_ADM": adm,
            "DEPTO": depto, "NIVEL": nivel, "GESTOR": gestor,
            "SALARIO": salario.get(key), "MOEDA": moeda.get(key),
            "LOCAL": e["location"], "PAIS": e["country"], "SITUACAO": "A",
        })

    write_xlsx(ctx.out_dir(SYS, "employee_master", load_date), rows,
               system=SYS, ingestion=load_date, sheet="FUNCIONARIOS")
    return {"employee_master": len(rows)}
