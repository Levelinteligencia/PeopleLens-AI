"""Projecao na folha de pagamento do Brasil.

O ponto desta projecao nao e o salario, e a DIVERGENCIA DE POPULACAO. A folha
tem definicao propria de "ativo": inclui terceiros e estagiarios de agencia que
nao existem no HRIS, e exclui afastados de longa duracao. Essa diferenca e o
defeito D11 e alimenta o check de reconciliacao DQ_RECON_001.
"""
from __future__ import annotations

from datetime import date

import polars as pl

from ..defects import injectors as inj
from ..defects.catalog import Catalog
from .base import Context, write_csv

SYS = "PAYROLL_BR"


def project(ctx: Context, cat: Catalog) -> dict[str, int]:
    cfg = ctx.cfg
    sysmeta = ctx.system(SYS)
    fmt = sysmeta["date_format"]
    _, end = cfg.period
    start = sysmeta["active_from"]
    rng = ctx.rng.get("proj_payroll")
    d11 = cat["D11"]

    snap = ctx.tables["fact_headcount_snapshot"].filter(
        (pl.col("country") == "BR") & (pl.col("snapshot_date") >= start))
    comp = ctx.tables["fact_compensation"].filter(pl.col("country") == "BR")
    last_salary: dict[int, float] = {}
    for c in comp.sort("effective_date").to_dicts():
        last_salary[c["employee_id"]] = c["base_salary"]

    rows: list[dict] = []
    by_month: dict[date, list[dict]] = {}
    for s in snap.to_dicts():
        by_month.setdefault(s["snapshot_date"], []).append(s)

    extra_id = 700000
    for m, people in sorted(by_month.items()):
        divergencia = d11.effective_rate(m)
        # A taxa configurada em D11 e a divergencia LIQUIDA de headcount entre
        # HRIS e folha, porque e assim que o check de reconciliacao a mede.
        # Inclusoes e exclusoes sao calibradas para que a diferenca liquida
        # fique na faixa, e nao para que cada perna fique.
        n_out = int(round(len(people) * divergencia * 0.30))
        drop_idx = set(rng.choice(len(people), size=min(n_out, len(people)), replace=False).tolist()) if n_out else set()
        n_in = int(round(len(people) * divergencia * 1.30))

        for i, s in enumerate(people):
            if i in drop_idx:
                ctx.ledger.record("D11", SYS, "payroll_headcount_snapshot",
                                  f"{s['employee_id']}|{m}", "situacao", "ativo no HRIS", "ausente na folha")
                continue
            moeda = "BRL"
            if ctx.hit(cat, "D14", SYS, "payroll_headcount_snapshot", when=m):
                ctx.ledger.record("D14", SYS, "payroll_headcount_snapshot",
                                  f"{s['employee_id']}|{m}", "moeda", "BRL", None)
                moeda = None
            rows.append({
                "matricula_folha": f"F{s['employee_id']:07d}",
                "dt_competencia": inj.format_date(m, fmt),
                "situacao": "ATIVO", "centro_custo": None,
                "valor_base": inj.decimal_br(last_salary.get(s["employee_id"], 0.0)),
                "moeda": moeda, "vinculo": "CLT", "pais": "BR",
            })
        for _ in range(n_in):
            extra_id += 1
            rows.append({
                "matricula_folha": f"T{extra_id:07d}",
                "dt_competencia": inj.format_date(m, fmt),
                "situacao": "ATIVO", "centro_custo": None,
                "valor_base": inj.decimal_br(float(rng.uniform(1800, 6000))),
                "moeda": "BRL",
                "vinculo": str(rng.choice(["TERCEIRO", "ESTAGIO_AGENCIA", "AVISO_PREVIO"])),
                "pais": "BR",
            })
            ctx.ledger.record("D11", SYS, "payroll_headcount_snapshot",
                              f"T{extra_id:07d}|{m}", "matricula_folha", "nao existe no HRIS", "presente na folha")

    write_csv(ctx.out_dir(SYS, "payroll_headcount_snapshot", end), rows,
              encoding=sysmeta["encoding"], delimiter=sysmeta["delimiter"], system=SYS, ingestion=end)

    crows = []
    for c in comp.to_dicts():
        moeda = "BRL"
        if ctx.hit(cat, "D14", SYS, "compensation", when=c["effective_date"]):
            ctx.ledger.record("D14", SYS, "compensation",
                              f"{c['employee_id']}|{c['effective_date']}", "moeda", "BRL", None)
            moeda = None
        crows.append({
            "matricula_folha": f"F{c['employee_id']:07d}",
            "dt_vigencia": inj.format_date(c["effective_date"], fmt),
            "salario_base": inj.decimal_br(c["base_salary"]),
            "moeda": moeda, "periodicidade": "MENSAL", "motivo": c["change_reason"],
        })
    write_csv(ctx.out_dir(SYS, "compensation", end), crows,
              encoding=sysmeta["encoding"], delimiter=sysmeta["delimiter"], system=SYS, ingestion=end)

    return {"payroll_headcount_snapshot": len(rows), "compensation": len(crows)}
