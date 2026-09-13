"""Metricas descritivas da camada de verdade.

Nota importante sobre o que este modulo NAO e: estes numeros sao a descricao do
mundo simulado, nao KPIs certificados. A camada semantica governada, com
contrato, lineage e trust score, so existe na F7. Aqui o objetivo e outro:
verificar se a NOVAORA gerada e plausivel, e registrar o gabarito contra o qual
o pipeline sera medido a partir da F2.

Todos os valores sao FATO sobre o dataset (ADR-0015, nivel FATO). Nenhuma
interpretacao e nenhuma afirmacao causal.
"""
from __future__ import annotations

from datetime import date

import polars as pl

from .config import Config


def _year_months(cfg: Config, year: int) -> int:
    _, end = cfg.period
    return 12 if year < end.year else end.month


def compute(cfg: Config, t: dict[str, pl.DataFrame]) -> dict:
    emp = t["dim_employee"].filter(pl.col("is_current"))
    snap = t["fact_headcount_snapshot"]
    term = t["fact_termination"]
    mov = t["fact_movement"]
    app = t["fact_application"]
    req = t["fact_requisition"]
    eng = t["fact_engagement"]
    lrn = t["fact_learning"]
    comp = t["fact_compensation"]

    snap = snap.with_columns(pl.col("snapshot_date").dt.year().alias("year"))
    term = term.with_columns(pl.col("termination_date").dt.year().alias("year"))
    mov = mov.with_columns(pl.col("movement_date").dt.year().alias("year"))

    out: dict = {"scale": cfg.scale, "profile": cfg.profile, "seed": cfg.seed}

    # ------------------------------------------------------------- headcount
    hc_year = {}
    for year in sorted(snap["year"].unique().to_list()):
        sub = snap.filter(pl.col("year") == year)
        months = _year_months(cfg, year)
        avg = sub.height / months
        last = sub.filter(pl.col("snapshot_date") == sub["snapshot_date"].max()).height
        hc_year[year] = {"avg": round(avg, 1), "eoy": last}
    out["headcount_by_year"] = hc_year

    last_date = snap["snapshot_date"].max()
    out["headcount_by_country_final"] = dict(
        snap.filter(pl.col("snapshot_date") == last_date).group_by("country").len().sort("country").iter_rows()
    )
    out["headcount_by_segment_final"] = dict(
        snap.filter(pl.col("snapshot_date") == last_date).group_by("segment").len().sort("segment").iter_rows()
    )
    out["level_distribution_final"] = {
        lv: round(n / snap.filter(pl.col("snapshot_date") == last_date).height, 4)
        for lv, n in snap.filter(pl.col("snapshot_date") == last_date)
        .group_by("job_level").len().iter_rows()
    }

    # -------------------------------------------------------------- turnover
    turnover = {}
    for year, meta in hc_year.items():
        t_year = term.filter(pl.col("year") == year)
        n = t_year.height
        vol = t_year.filter(pl.col("voluntary_flag")).height
        reg = t_year.filter(pl.col("regrettable_flag")).height
        annualize = 12 / _year_months(cfg, year)
        turnover[year] = {
            "terminations": n,
            "rate": round(n / meta["avg"] * annualize, 4),
            "voluntary_rate": round(vol / meta["avg"] * annualize, 4),
            "involuntary_rate": round((n - vol) / meta["avg"] * annualize, 4),
            "regrettable_share": round(reg / n, 4) if n else None,
        }
    out["turnover_by_year"] = turnover

    seg_turn = {}
    for seg in sorted(term["segment"].unique().to_list()):
        n = term.filter(pl.col("segment") == seg).height
        avg = snap.filter(pl.col("segment") == seg).height / snap["snapshot_date"].n_unique()
        seg_turn[seg] = {
            "realized_annual_rate": round(n / avg / (snap["snapshot_date"].n_unique() / 12), 4),
            "configured_base_rate": cfg.segments[seg]["turnover_base"],
        }
    out["turnover_by_segment"] = seg_turn

    # ------------------------------------------------------- carreira e mobilidade
    career = {}
    for year, meta in hc_year.items():
        m_year = mov.filter(pl.col("year") == year)
        annualize = 12 / _year_months(cfg, year)
        promo = m_year.filter(pl.col("movement_type") == "Promotion").height
        mobility = m_year.filter(pl.col("movement_type").is_in(["Transfer", "Lateral Move"])).height
        reorg = m_year.filter(pl.col("movement_type") == "Reorganization").height
        career[year] = {
            "promotion_rate": round(promo / meta["avg"] * annualize, 4),
            "internal_mobility_rate": round(mobility / meta["avg"] * annualize, 4),
            "reorganization_movements": reorg,
        }
    out["career_by_year"] = career
    out["promotion_propensity_configured"] = cfg.generation["career_events"]["promotion"]["annual_rate_by_segment"]

    # ------------------------------------------------------------------ DEI
    dei = {}
    lead_groups = ["Manager", "Senior Manager", "Director", "Executive"]
    snap_j = snap.join(
        t["dim_employee"].filter(pl.col("is_current")).select(["employee_id", "gender", "race_ethnicity", "race_declared", "race_declared_at"]),
        on="employee_id", how="left",
    )
    for year in sorted(snap["year"].unique().to_list()):
        sub = snap_j.filter(pl.col("year") == year)
        lead = sub.filter(pl.col("job_level_group").is_in(lead_groups))
        total_f = sub.filter(pl.col("gender") == "Female").height
        lead_f = lead.filter(pl.col("gender") == "Female").height
        # a declaracao so conta a partir da data em que o campo passou a
        # existir para aquela pessoa: antes disso nao e dado faltante, e
        # ausencia de campo (defeito D02)
        declared = sub.filter(
            pl.col("race_declared")
            & pl.col("race_declared_at").is_not_null()
            & (pl.col("race_declared_at") <= pl.col("snapshot_date"))
        ).height
        dei[year] = {
            "female_share_workforce": round(total_f / sub.height, 4) if sub.height else None,
            "female_share_leadership": round(lead_f / lead.height, 4) if lead.height else None,
            "race_declaration_rate": round(declared / sub.height, 4) if sub.height else None,
        }
    out["dei_by_year"] = dei

    # --------------------------------------------------------- recrutamento
    filled = req.filter(pl.col("requisition_status") == "Filled").with_columns(
        (pl.col("hire_date") - pl.col("opening_date")).dt.total_days().alias("time_to_fill")
    )
    hired_app = app.filter(pl.col("hire_date").is_not_null()).with_columns(
        (pl.col("hire_date") - pl.col("application_date")).dt.total_days().alias("time_to_hire")
    )
    offers = app.filter(pl.col("offer_date").is_not_null())
    out["recruitment"] = {
        "requisitions": req.height,
        "requisitions_filled": filled.height,
        "requisitions_unfilled_share": round(1 - filled.height / req.height, 4) if req.height else None,
        "applications": app.height,
        "applications_per_requisition": round(app.height / req.height, 2) if req.height else None,
        "time_to_fill_days_mean": round(float(filled["time_to_fill"].mean()), 1),
        "time_to_fill_days_median": float(filled["time_to_fill"].median()),
        "time_to_hire_days_mean": round(float(hired_app["time_to_hire"].mean()), 1),
        "time_to_hire_days_median": float(hired_app["time_to_hire"].median()),
        "offer_acceptance_rate": round(offers.filter(pl.col("offer_accepted_flag")).height / offers.height, 4) if offers.height else None,
        "internal_share": round(app.filter(pl.col("internal_external") == "Internal").height / app.height, 4) if app.height else None,
    }
    ttf_by_group = (
        filled.join(t["dim_employee"].filter(pl.col("is_current")).select(["employee_id", "job_level_group"]).unique(),
                    left_on="job_level", right_on="job_level_group", how="left")
    )
    out["recruitment"]["time_to_fill_by_level"] = {
        lv: round(float(v), 1) for lv, v in
        filled.group_by("job_level").agg(pl.col("time_to_fill").mean()).sort("job_level").iter_rows()
    }

    # ---------------------------------------------------------- engajamento
    resp = eng.filter(pl.col("response_flag") == 1)
    out["engagement"] = {
        "surveys": eng.height,
        "response_rate": round(resp.height / eng.height, 4) if eng.height else None,
        "engagement_score_mean": round(float(resp["engagement_score"].mean()), 3),
        "non_respondents_with_score": eng.filter((pl.col("response_flag") == 0) & pl.col("engagement_score").is_not_null()).height,
    }

    # --------------------------------------------------------- aprendizagem
    out["learning"] = {
        "enrollments": lrn.height,
        "completion_rate_mandatory": round(
            lrn.filter(pl.col("mandatory_flag") & (pl.col("completion_status") == "Completed")).height
            / max(1, lrn.filter(pl.col("mandatory_flag")).height), 4),
        "completion_rate_optional": round(
            lrn.filter(~pl.col("mandatory_flag") & (pl.col("completion_status") == "Completed")).height
            / max(1, lrn.filter(~pl.col("mandatory_flag")).height), 4),
        "hours_total": round(float(lrn["learning_hours"].sum()), 1),
    }

    # ----------------------------------------------------------- remuneracao
    comp_last = comp.sort("effective_date").group_by("employee_id").last()
    comp_last = comp_last.with_columns((pl.col("base_salary") / pl.col("band_mid")).alias("compa_ratio_calc"))
    out["compensation"] = {
        "records": comp.height,
        "compa_ratio_mean": round(float(comp_last["compa_ratio_calc"].mean()), 4),
        "compa_ratio_p10": round(float(comp_last["compa_ratio_calc"].quantile(0.10)), 4),
        "compa_ratio_p90": round(float(comp_last["compa_ratio_calc"].quantile(0.90)), 4),
        "by_country_currency": dict(comp.group_by("country").agg(pl.col("currency").first()).sort("country").iter_rows()),
    }

    # ------------------------------------------------------------- origens
    out["population"] = {
        "historical_individuals": t["dim_employee"]["employee_id"].n_unique(),
        "by_origin": dict(emp.group_by("origin").len().sort("origin").iter_rows()),
        "scd2_versions": t["dim_employee"].height,
        "versions_per_employee": round(t["dim_employee"].height / t["dim_employee"]["employee_id"].n_unique(), 2),
    }
    return out


# --------------------------------------------------------------------------- #
def to_markdown(cfg: Config, m: dict, checks: list | None = None) -> str:
    L: list[str] = []
    L.append("# PeopleLens, F1: metricas da camada de verdade\n")
    L.append(f"Perfil `{m['profile']}` (escala {m['scale']:.0%}), seed `{m['seed']}`.\n")
    L.append("> Estes numeros descrevem o mundo simulado. Nao sao KPIs certificados: ")
    L.append("> a camada semantica governada so existe na F7.\n")

    L.append("\n## Headcount e turnover\n")
    L.append("| Ano | HC medio | HC fim | Deslig. | Turnover | Voluntario | Involuntario |")
    L.append("|---|---|---|---|---|---|---|")
    for y, hc in m["headcount_by_year"].items():
        tv = m["turnover_by_year"][y]
        L.append(f"| {y} | {hc['avg']:.0f} | {hc['eoy']} | {tv['terminations']} | "
                 f"{tv['rate']:.1%} | {tv['voluntary_rate']:.1%} | {tv['involuntary_rate']:.1%} |")

    L.append("\n## Turnover por segmento\n")
    L.append("| Segmento | Realizado | Configurado (base) |")
    L.append("|---|---|---|")
    for seg, v in m["turnover_by_segment"].items():
        L.append(f"| {seg} | {v['realized_annual_rate']:.1%} | {v['configured_base_rate']:.1%} |")

    L.append("\n## Carreira\n")
    L.append("| Ano | Taxa de promocao | Mobilidade interna | Movimentos por reorg |")
    L.append("|---|---|---|---|")
    for y, v in m["career_by_year"].items():
        L.append(f"| {y} | {v['promotion_rate']:.1%} | {v['internal_mobility_rate']:.1%} | {v['reorganization_movements']} |")

    L.append("\n## DEI\n")
    L.append("> Parametros sinteticos. Nao representam nenhuma populacao real.\n")
    L.append("| Ano | Mulheres no total | Mulheres em lideranca | Taxa de declaracao de raca e cor |")
    L.append("|---|---|---|---|")
    for y, v in m["dei_by_year"].items():
        f1 = f"{v['female_share_workforce']:.1%}" if v["female_share_workforce"] is not None else "n/d"
        f2 = f"{v['female_share_leadership']:.1%}" if v["female_share_leadership"] is not None else "n/d"
        f3 = f"{v['race_declaration_rate']:.1%}" if v["race_declaration_rate"] is not None else "n/d"
        L.append(f"| {y} | {f1} | {f2} | {f3} |")

    r = m["recruitment"]
    L.append("\n## Recrutamento\n")
    L.append(f"- requisicoes: {r['requisitions']}, preenchidas {r['requisitions_filled']} "
             f"({1 - r['requisitions_unfilled_share']:.0%})")
    L.append(f"- candidaturas: {r['applications']} ({r['applications_per_requisition']} por requisicao)")
    L.append(f"- Time to Fill: media {r['time_to_fill_days_mean']} dias, mediana {r['time_to_fill_days_median']:.0f}")
    L.append(f"- Time to Hire: media {r['time_to_hire_days_mean']} dias, mediana {r['time_to_hire_days_median']:.0f}")
    L.append(f"- Offer Acceptance Rate: {r['offer_acceptance_rate']:.1%}")

    e = m["engagement"]
    L.append("\n## Engajamento, aprendizagem e remuneracao\n")
    L.append(f"- pesquisas: {e['surveys']}, taxa de resposta {e['response_rate']:.1%}, "
             f"score medio {e['engagement_score_mean']}")
    L.append(f"- nao respondentes com score preenchido: {e['non_respondents_with_score']} (deve ser 0 na verdade)")
    lr = m["learning"]
    L.append(f"- matriculas: {lr['enrollments']}, conclusao obrigatoria {lr['completion_rate_mandatory']:.1%}, "
             f"opcional {lr['completion_rate_optional']:.1%}")
    c = m["compensation"]
    L.append(f"- compa-ratio recalculado: media {c['compa_ratio_mean']}, "
             f"p10 {c['compa_ratio_p10']}, p90 {c['compa_ratio_p90']}")

    p = m["population"]
    L.append("\n## Populacao\n")
    L.append(f"- individuos historicos: {p['historical_individuals']}")
    L.append(f"- versoes SCD2: {p['scd2_versions']} ({p['versions_per_employee']} por pessoa)")
    L.append(f"- por origem: {p['by_origin']}")

    if checks:
        ok = sum(1 for c_ in checks if c_.passed)
        L.append(f"\n## Validacoes de coerencia\n\n{ok} de {len(checks)} passaram.\n")
        L.append("| ID | Verificacao | Resultado |")
        L.append("|---|---|---|")
        for c_ in checks:
            L.append(f"| {c_.check_id} | {c_.name} | {'OK' if c_.passed else 'FALHOU: ' + c_.detail} |")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- #
# Relatorio da camada RAW (F2)
# --------------------------------------------------------------------------- #
def raw_to_markdown(cfg: Config, manifest: dict, ledger, checks: list | None = None) -> str:
    led = ledger.to_frame()
    L: list[str] = []
    L.append("# PeopleLens, F2: projecao nos sistemas-fonte\n")
    L.append(f"Perfil `{manifest['profile']}` (escala {manifest['scale']:.0%}), seed `{manifest['seed']}`, "
             f"onda {manifest['wave']}.\n")
    L.append("> A camada de verdade nao foi alterada. O RAW e projecao dela, com os defeitos\n"
             "> declarados em `config/defects.yaml`. As taxas estao "
             f"**{manifest['rates_status']}** (ADR-0008, Parte B).\n")

    L.append("\n## Volumes por sistema\n")
    L.append("| Sistema | Dataset | Linhas | Formato |")
    L.append("|---|---|---|---|")
    for sysname, datasets in manifest["systems"].items():
        fmt = cfg.sources["systems"][sysname]["format"]
        for ds, n in datasets.items():
            L.append(f"| {sysname} | {ds} | {n:,} | {fmt} |".replace(",", "."))

    L.append("\n## Defeitos injetados\n")
    if led.height:
        by = led.group_by("defect_id").len().sort("len", descending=True)
        cat_by_id = {d["id"]: d for d in cfg.defects["defects"]}
        L.append("| Defeito | Nome | Dimensao | Ocorrencias |")
        L.append("|---|---|---|---|")
        for did, n in by.iter_rows():
            spec = cat_by_id.get(did, {})
            L.append(f"| {did} | {spec.get('name', '')} | {spec.get('dimension', '')} | {n:,} |".replace(",", "."))
        L.append(f"\nTotal: **{led.height:,} ocorrencias** registradas no ledger.".replace(",", "."))

        todos = {d["id"] for d in cfg.defects["defects"]}
        ativos = set(led["defect_id"].unique().to_list())
        L.append(f"\nCobertura: {len(ativos)} de {len(todos)} defeitos do catalogo estao ativos na onda 1. "
                 f"Os demais dependem de sistemas da onda 2: {sorted(todos - ativos)}.")

    L.append("\n## Calibragem: esperado versus realizado\n")
    L.append("> Base da decisao D8 Parte B. O ledger conta quantos registros foram\n"
             "> **oferecidos** a cada defeito e qual era a taxa esperada em cada oferta,\n"
             "> ja considerando escopo temporal, picos por incidente e taxa por pais.\n")
    L.append("| Defeito | Sistema.dataset | Elegiveis | Esperado | Realizado | Desvio |")
    L.append("|---|---|---|---|---|---|")
    for c in ledger.calibration():
        if c["expected_rate"] <= 0:
            continue
        dev = c["realized_rate"] - c["expected_rate"]
        L.append(f"| {c['defect_id']} | {c['source_system']}.{c['dataset']} | {c['eligible']:,} | "
                 f"{c['expected_rate']:.2%} | {c['realized_rate']:.2%} | {dev:+.2%} |".replace(",", "."))

    if checks:
        ok = sum(1 for c in checks if c.passed)
        L.append(f"\n## Validacoes da camada RAW\n\n{ok} de {len(checks)} passaram.\n")
        L.append("| ID | Verificacao | Resultado |")
        L.append("|---|---|---|")
        for c in checks:
            status = "OK" if c.passed else ("FALHOU: " + c.detail if c.severity in ("BLOCKER", "CRITICAL") else "AVISO: " + c.detail)
            L.append(f"| {c.check_id} | {c.name} | {status} |")
    return "\n".join(L) + "\n"
