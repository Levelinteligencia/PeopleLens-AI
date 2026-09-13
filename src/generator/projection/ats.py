"""Projecao no ATS atual (export JSON aninhado, a partir de 2021).

Dois defeitos moram aqui. O D16, requisicao sem contratacao, ja e fato do mundo
e so e registrado. O D17, contratacao sem requisicao valida, e injetado:
contratacao emergencial de loja registrada depois, sem vaga aberta antes.
"""
from __future__ import annotations

import polars as pl

from ..defects import injectors as inj
from ..defects.catalog import Catalog
from .base import Context, write_json

SYS = "ATS_CLOUD"


def project(ctx: Context, cat: Catalog) -> dict[str, int]:
    cfg = ctx.cfg
    sysmeta = ctx.system(SYS)
    _, end = cfg.period
    start = sysmeta["active_from"]
    rng = ctx.rng.get("proj_ats")
    fill = float(sysmeta.get("enterprise_id_fill_rate", 1.0))

    req = ctx.tables["fact_requisition"].filter(pl.col("opening_date") >= start)
    app = ctx.tables["fact_application"]
    emp = ctx.tables["dim_employee"].filter(pl.col("is_current")).select(
        ["employee_id", "full_name", "segment"]).to_dicts()
    names = {e["employee_id"]: e["full_name"] for e in emp}
    segment = {e["employee_id"]: e["segment"] for e in emp}

    by_req: dict[str, list[dict]] = {}
    for a in app.to_dicts():
        by_req.setdefault(a["requisition_id"], []).append(a)

    # D17: contratacao emergencial de loja sem requisicao valida
    reqs = req.to_dicts()
    dropped: set[str] = set()
    for r in reqs:
        if r["requisition_status"] != "Filled":
            continue
        cand = by_req.get(r["requisition_id"], [])
        hired = next((c for c in cand if c["employee_id"] is not None), None)
        if hired and segment.get(hired["employee_id"]) == "retail_ops" and ctx.hit(cat, "D17", SYS, "requisition"):
            dropped.add(r["requisition_id"])
            ctx.ledger.record("D17", SYS, "requisition", r["requisition_id"], None,
                              "requisicao existe na verdade", "ausente no ATS")

    records, n_app = [], 0
    for r in reqs:
        if r["requisition_id"] in dropped:
            continue
        if r["requisition_status"] != "Filled":
            ctx.ledger.record("D16", SYS, "requisition", r["requisition_id"], "requisition_status",
                              "sem contratacao", r["requisition_status"])
        cands = []
        for a in by_req.get(r["requisition_id"], []):
            n_app += 1
            eid = a["employee_id"]
            if eid is not None and rng.random() > fill:
                ctx.ledger.record("D05", SYS, "application", a["candidate_id"], "employee_id", eid, None)
                eid = None
            nome = names.get(a["employee_id"]) or f"Candidato {a['candidate_id'][-5:]}"
            dom = str(rng.choice(cfg.generation["demographics"]["names"]["personal_email_domains"]))
            cands.append({
                "candidate_id": a["candidate_id"],
                "candidate_name": nome,
                "candidate_email": nome.lower().replace(" ", ".") + "@" + dom,
                "employee_id": eid,
                "application_date": a["application_date"],
                "screening_date": a["screening_date"], "interview_date": a["interview_date"],
                "offer_date": a["offer_date"], "hire_date": a["hire_date"],
                "offer_accepted": bool(a["offer_accepted_flag"]),
                "source": a["candidate_source"], "type": a["internal_external"],
            })
        records.append({
            "requisition_id": r["requisition_id"], "position_id": r["position_id"],
            "status": r["requisition_status"], "recruiter_id": r["recruiter_id"],
            "org": {"country": r["country"], "business_unit": r["business_unit"],
                    "department": r["department"], "sub_department": r["sub_department"],
                    "job_family": r["job_family"], "job_level": r["job_level"],
                    "location": r["location"]},
            "dates": {"opening_date": r["opening_date"], "approval_date": r["approval_date"],
                      "posting_date": r["posting_date"], "hire_date": r["hire_date"]},
            "candidates": cands,
        })

    write_json(ctx.out_dir(SYS, "requisition", end), records, system=SYS, ingestion=end)
    return {"requisition": len(records), "application": n_app}
