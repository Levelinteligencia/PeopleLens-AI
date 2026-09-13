"""Validacoes de coerencia da camada de verdade.

A camada de verdade e o gabarito do projeto (ADR-0001). Se ela estiver
incoerente, toda a medicao posterior do pipeline perde sentido. Por isso as
checagens aqui sao estruturais e sem tolerancia: qualquer falha quebra a F1.

Estas NAO sao as regras de Data Quality do projeto (essas vem na F5, sobre os
dados sujos). Aqui verificamos que a verdade e internamente consistente, que e
uma coisa diferente e mais forte.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import polars as pl

from .config import Config


@dataclass
class Check:
    check_id: str
    name: str
    passed: bool
    detail: str = ""
    severity: str = "BLOCKER"


def _ok(cid: str, name: str, cond: bool, detail: str = "", severity: str = "BLOCKER") -> Check:
    return Check(cid, name, bool(cond), detail, severity)


def run_all(cfg: Config, t: dict[str, pl.DataFrame]) -> list[Check]:
    checks: list[Check] = []
    emp = t["dim_employee"]
    snap = t["fact_headcount_snapshot"]

    # ----------------------------------------------------------------- SCD2
    per_emp = emp.group_by("employee_id").agg(pl.col("is_current").sum().alias("n_current"))
    bad = per_emp.filter(pl.col("n_current") != 1)
    checks.append(_ok("V01", "dim_employee tem exatamente um is_current por employee_id",
                      bad.height == 0, f"{bad.height} employee_id fora da regra"))

    ordered = emp.sort(["employee_id", "effective_from"])
    nxt = ordered.select(["employee_id", "effective_from"]).shift(-1)
    joined = ordered.with_columns([
        nxt["employee_id"].alias("next_emp"),
        nxt["effective_from"].alias("next_from"),
    ])
    overlap = joined.filter(
        (pl.col("next_emp") == pl.col("employee_id"))
        & (pl.col("effective_to").is_not_null())
        & (pl.col("effective_to") >= pl.col("next_from"))
    )
    checks.append(_ok("V02", "SCD2 sem sobreposicao de vigencia",
                      overlap.height == 0, f"{overlap.height} versoes sobrepostas"))

    gap = joined.filter(
        (pl.col("next_emp") == pl.col("employee_id"))
        & (pl.col("effective_to").is_not_null())
        & ((pl.col("next_from") - pl.col("effective_to")).dt.total_days() != 1)
    )
    checks.append(_ok("V03", "SCD2 sem buraco entre versoes",
                      gap.height == 0, f"{gap.height} lacunas"))

    first = emp.sort(["employee_id", "effective_from"]).group_by("employee_id").first()
    bad_first = first.filter(pl.col("effective_from") != pl.col("hire_date"))
    checks.append(_ok("V04", "primeira versao do SCD2 comeca na data de admissao",
                      bad_first.height == 0, f"{bad_first.height} divergencias"))

    # ------------------------------------------------------------- datas base
    bad_dates = emp.filter(
        pl.col("termination_date").is_not_null() & (pl.col("termination_date") < pl.col("hire_date"))
    )
    checks.append(_ok("V05", "termination_date nunca anterior a hire_date",
                      bad_dates.height == 0, f"{bad_dates.height} registros"))

    _, end = cfg.period
    future = emp.filter(pl.col("hire_date") > end)
    checks.append(_ok("V06", "nenhuma admissao depois do fim da serie",
                      future.height == 0, f"{future.height} registros"))

    # -------------------------------------------------------- linha de reporte
    ids = set(emp["employee_id"].unique().to_list())
    mgr = emp.filter(pl.col("manager_id").is_not_null())["manager_id"].unique().to_list()
    orphans = [m for m in mgr if m not in ids]
    checks.append(_ok("V07", "nenhum manager_id orfao na camada de verdade",
                      len(orphans) == 0, f"{len(orphans)} gestores inexistentes"))

    cur = emp.filter(pl.col("is_current") & (pl.col("employment_status") == "Active"))
    parent = dict(zip(cur["employee_id"].to_list(), cur["manager_id"].to_list()))
    cycles = 0
    for start in parent:
        seen, node = set(), start
        while node is not None and node in parent:
            if node in seen:
                cycles += 1
                break
            seen.add(node)
            node = parent[node]
    checks.append(_ok("V08", "nenhum ciclo na linha de reporte", cycles == 0, f"{cycles} ciclos"))

    roots = cur.filter(pl.col("manager_id").is_null())
    checks.append(_ok("V09", "exatamente uma pessoa ativa sem gestor (topo da hierarquia)",
                      roots.height == 1, f"{roots.height} pessoas sem gestor"))

    # Invariante real: alguem so fica sem gestor se, naquele instante, nao
    # existir nenhuma pessoa ativa de nivel superior. Em populacao pequena
    # (perfil smoke) o topo da hierarquia nao e necessariamente D3, entao
    # comparar com o nivel mais alto do catalogo daria falso positivo.
    no_mgr = emp.filter(pl.col("manager_id").is_null()).select(
        ["employee_id", "effective_from", "job_level"]
    ).to_dicts()
    windows = emp.select(["employee_id", "job_level", "effective_from", "effective_to"]).to_dicts()
    violations = 0
    for r in no_mgr:
        at, rank = r["effective_from"], cfg.level_rank(r["job_level"])
        higher = any(
            w["employee_id"] != r["employee_id"]
            and w["effective_from"] <= at
            and (w["effective_to"] is None or at <= w["effective_to"])
            and cfg.level_rank(w["job_level"]) > rank
            for w in windows
        )
        violations += int(higher)
    checks.append(_ok("V09b", "so fica sem gestor quem nao tem ninguem de nivel superior ativo",
                      violations == 0, f"{violations} versoes com gestor possivel e nao atribuido"))

    # ------------------------------------------------------------- snapshots
    hire = dict(zip(emp["employee_id"].to_list(), emp["hire_date"].to_list()))
    term = dict(zip(emp["employee_id"].to_list(), emp["termination_date"].to_list()))
    s = snap.select(["employee_id", "snapshot_date"]).to_dicts()
    before = sum(1 for r in s if r["snapshot_date"] < hire[r["employee_id"]])
    after = sum(1 for r in s if term[r["employee_id"]] and r["snapshot_date"] > term[r["employee_id"]])
    checks.append(_ok("V10", "snapshot nunca antes da admissao", before == 0, f"{before} linhas"))
    checks.append(_ok("V11", "snapshot nunca depois do desligamento", after == 0, f"{after} linhas"))

    dup = snap.group_by(["employee_id", "snapshot_date"]).len().filter(pl.col("len") > 1)
    checks.append(_ok("V12", "snapshot sem duplicidade por employee_id e mes",
                      dup.height == 0, f"{dup.height} duplicatas"))

    # --------------------------------------------------- integridade das FKs
    for name, key in [("fact_termination", "employee_id"), ("fact_movement", "employee_id"),
                      ("fact_compensation", "employee_id"), ("fact_performance", "employee_id"),
                      ("fact_learning", "employee_id"), ("fact_engagement", "employee_id")]:
        df = t[name]
        miss = set(df[key].unique().to_list()) - ids
        checks.append(_ok(f"V13.{name}", f"{name} sem employee_id inexistente",
                          len(miss) == 0, f"{len(miss)} ids"))

    org_keys = set(t["dim_organization"]["org_key"].to_list())
    miss_org = set(snap["org_key"].unique().to_list()) - org_keys
    checks.append(_ok("V14", "snapshot sem org_key inexistente", len(miss_org) == 0, f"{len(miss_org)} chaves"))

    # ------------------------------------------------ eventos versus saida
    for name, col in [("fact_movement", "movement_date"), ("fact_compensation", "effective_date"),
                      ("fact_performance", "review_date"), ("fact_learning", "enrollment_date"),
                      ("fact_engagement", "survey_date")]:
        df = t[name].select(["employee_id", col]).to_dicts()
        late = sum(1 for r in df if term[r["employee_id"]] and r[col] > term[r["employee_id"]])
        early = sum(1 for r in df if r[col] < hire[r["employee_id"]])
        checks.append(_ok(f"V15.{name}", f"{name} sem evento fora do vinculo",
                          late == 0 and early == 0, f"{early} antes da admissao, {late} depois da saida"))

    # ---------------------------------------------------------- unicidade
    uniq = [("fact_termination", ["termination_id"]), ("fact_movement", ["movement_id"]),
            ("fact_requisition", ["requisition_id"]),
            ("fact_application", ["requisition_id", "candidate_id"]),
            ("dim_employee", ["employee_key"]), ("dim_organization", ["org_key"])]
    for name, keys in uniq:
        d = t[name].group_by(keys).len().filter(pl.col("len") > 1)
        checks.append(_ok(f"V16.{name}", f"{name} com chave unica {keys}",
                          d.height == 0, f"{d.height} duplicatas"))

    # ------------------------------------------------------------ promocoes
    mv = t["fact_movement"].filter(pl.col("movement_type") == "Promotion")
    ranks = {lv: cfg.level_rank(lv) for lv in cfg.org["job_levels"]}
    bad_prom = sum(1 for r in mv.select(["old_job_level", "new_job_level"]).to_dicts()
                   if ranks[r["new_job_level"]] <= ranks[r["old_job_level"]])
    checks.append(_ok("V17", "promocao sempre eleva o nivel", bad_prom == 0, f"{bad_prom} promocoes invalidas"))

    dem = t["fact_movement"].filter(pl.col("movement_type") == "Demotion")
    bad_dem = sum(1 for r in dem.select(["old_job_level", "new_job_level"]).to_dicts()
                  if ranks[r["new_job_level"]] >= ranks[r["old_job_level"]])
    checks.append(_ok("V18", "rebaixamento sempre reduz o nivel", bad_dem == 0, f"{bad_dem} invalidos"))

    # --------------------------------------------------------- engajamento
    eng = t["fact_engagement"]
    bad_eng = eng.filter((pl.col("response_flag") == 0) & pl.col("engagement_score").is_not_null())
    checks.append(_ok("V19", "nao respondente tem score nulo, nunca zero",
                      bad_eng.height == 0, f"{bad_eng.height} linhas"))
    bad_eng2 = eng.filter((pl.col("response_flag") == 1) & pl.col("engagement_score").is_null())
    checks.append(_ok("V20", "respondente sempre tem score", bad_eng2.height == 0, f"{bad_eng2.height} linhas"))

    # --------------------------------------------------------- performance
    perf = t["fact_performance"]
    scales = cfg.generation["performance"]["scales"]
    bad_scale = 0
    for r in perf.select(["review_date", "performance_rating_recorded"]).to_dicts():
        sc = next(s_ for s_ in scales
                  if s_["valid_from"] <= r["review_date"] and (s_["valid_to"] is None or r["review_date"] <= s_["valid_to"]))
        if r["performance_rating_recorded"] not in sc["values"]:
            bad_scale += 1
    checks.append(_ok("V21", "escala de performance correta para o periodo",
                      bad_scale == 0, f"{bad_scale} avaliacoes fora da escala vigente"))

    # ---------------------------------------------------------- aprendizagem
    lrn = t["fact_learning"]
    lstart = cfg.generation["learning"]["available_from"]
    early_l = lrn.filter(pl.col("enrollment_date") < lstart)
    checks.append(_ok("V22", "aprendizagem so existe apos a entrada do LMS",
                      early_l.height == 0, f"{early_l.height} matriculas antes de {lstart}"))

    # ------------------------------------------------------------ estrutura
    mkt_from = cfg.org["business_units"]["Marketplace"].get("available_from")
    if mkt_from:
        early_mkt = snap.filter((pl.col("business_unit") == "Marketplace") & (pl.col("snapshot_date") < mkt_from))
        checks.append(_ok("V23", "Marketplace nao existe antes da aquisicao de 2022",
                          early_mkt.height == 0, f"{early_mkt.height} linhas"))

    # ------------------------------------------------------------ remuneracao
    comp = t["fact_compensation"]
    nonpos = comp.filter(pl.col("base_salary") <= 0)
    checks.append(_ok("V24", "nenhum salario nulo ou negativo", nonpos.height == 0, f"{nonpos.height} linhas"))

    # ----------------------------------------------------------- recrutamento
    app = t["fact_application"]
    bad_app = app.filter(pl.col("hire_date").is_not_null() & (pl.col("offer_accepted_flag") == False))  # noqa: E712
    checks.append(_ok("V25", "candidatura com admissao implica oferta aceita",
                      bad_app.height == 0, f"{bad_app.height} linhas"))
    req = t["fact_requisition"]
    filled = req.filter(pl.col("requisition_status") == "Filled")
    bad_req = filled.filter(pl.col("hire_date").is_null())
    checks.append(_ok("V26", "requisicao preenchida sempre tem data de admissao",
                      bad_req.height == 0, f"{bad_req.height} linhas"))
    neg_cycle = req.filter(pl.col("hire_date").is_not_null() & (pl.col("hire_date") < pl.col("opening_date")))
    checks.append(_ok("V27", "admissao nunca anterior a abertura da requisicao",
                      neg_cycle.height == 0, f"{neg_cycle.height} linhas"))

    # ------------------------------------------------------------- headcount
    tol = cfg.generation["headcount"]["tolerance"]
    from .world.population import headcount_plan
    from .world.calendar import Calendar, end_of_month
    plan = headcount_plan(cfg, Calendar(*cfg.period))
    real = dict(snap.group_by("snapshot_date").len().iter_rows())
    tot_real = tot_plan = 0
    worst, worst_m, worst_allowed = 0.0, None, 0.0
    for m, target in plan.items():
        got = real.get(end_of_month(m), 0)
        tot_real += got
        tot_plan += target
        dev = abs(got - target) / max(1, target)
        # a tolerancia por mes acompanha o ruido amostral: com populacao
        # pequena (perfil smoke) um desvio relativo maior e esperado e nao
        # indica erro de simulacao
        allowed = max(tol, 3.0 / max(1.0, target ** 0.5))
        if dev - allowed > worst - worst_allowed:
            worst, worst_m, worst_allowed = dev, m, allowed
    checks.append(_ok("V28", "headcount mensal dentro da tolerancia ajustada ao ruido amostral",
                      worst <= worst_allowed,
                      f"maior desvio {worst:.1%} em {worst_m} (permitido {worst_allowed:.1%})",
                      severity="CRITICAL"))

    dev_total = abs(tot_real - tot_plan) / tot_plan
    checks.append(_ok("V28b", f"headcount acumulado dentro de {tol:.0%} do plano",
                      dev_total <= tol, f"desvio acumulado {dev_total:.2%}", severity="CRITICAL"))

    # -------------------------------------------- aquisicoes nao sao contratacoes
    acq_ids = set(emp.filter(pl.col("origin").str.starts_with("acquisition"))["employee_id"].to_list())
    hired_via_req = set(app.filter(pl.col("employee_id").is_not_null())["employee_id"].to_list())
    overlap_acq = acq_ids & hired_via_req
    checks.append(_ok("V29", "pessoa vinda de aquisicao nunca aparece como contratacao",
                      len(overlap_acq) == 0, f"{len(overlap_acq)} pessoas"))

    checks.extend(_demographic_coherence(cfg, t))
    return checks


def _demographic_coherence(cfg: Config, t: dict[str, pl.DataFrame]) -> list[Check]:
    """Coerencia interna da demografia (pedido da Sam na aprovacao da F1, item 3).

    Nao verifica se os parametros sao realistas, porque eles sao [SINTETICO] por
    decisao (ver docs/demographics.md). Verifica se o mundo gerado e internamente
    consistente com o que a propria configuracao declara: gradiente por nivel,
    taxa de nao declaracao, ausencia de imputacao e evolucao temporal.
    """
    out: list[Check] = []
    demo = cfg.generation["demographics"]
    emp = t["dim_employee"].filter(pl.col("is_current"))
    snap = t["fact_headcount_snapshot"].with_columns(pl.col("snapshot_date").dt.year().alias("year"))
    j = snap.join(emp.select(["employee_id", "gender", "race_ethnicity", "race_declared",
                              "race_declared_at", "birth_year", "hire_date"]),
                  on="employee_id", how="left")

    # Shares demograficos sao calculados sobre PESSOAS DISTINTAS, nunca sobre
    # pessoa-mes: uma unica diretora presente por 80 meses contaria 80 vezes e
    # transformaria ruido amostral em tendencia.
    people = emp  # dim_employee ja filtrado por is_current: uma linha por pessoa
    buckets = {
        "base":  ["Entry", "Professional"],
        "meio":  ["Senior Professional", "Manager"],
        "topo":  ["Senior Manager", "Director", "Executive"],
    }

    def _share(df: pl.DataFrame, expr: pl.Expr) -> tuple[float, int]:
        if df.height == 0:
            return (0.0, 0)
        return (df.filter(expr).height / df.height, df.height)

    # ---- gradiente de genero: base > meio > topo ----
    g = {k: _share(people.filter(pl.col("job_level_group").is_in(v)), pl.col("gender") == "Female")
         for k, v in buckets.items()}
    okg = g["base"][0] >= g["meio"][0] >= g["topo"][0]
    out.append(_ok("V30", "share feminino cai da base para o topo da hierarquia",
                   okg, f"base {g['base'][0]:.1%} (n={g['base'][1]}), meio {g['meio'][0]:.1%} "
                        f"(n={g['meio'][1]}), topo {g['topo'][0]:.1%} (n={g['topo'][1]})",
                   severity="CRITICAL"))

    # ---- sem inversao relevante entre grupos com populacao suficiente ----
    order = ["Entry", "Professional", "Senior Professional", "Manager", "Senior Manager", "Director", "Executive"]
    shares = []
    for grp in order:
        sub = people.filter(pl.col("job_level_group") == grp)
        if sub.height >= 200:          # abaixo disso o share e ruido, nao gradiente
            shares.append((grp, sub.filter(pl.col("gender") == "Female").height / sub.height))
    inversions = sum(1 for i in range(len(shares) - 1) if shares[i + 1][1] > shares[i][1] + 0.08)
    out.append(_ok("V30b", "sem inversao relevante no gradiente de genero entre niveis com n suficiente",
                   inversions == 0, f"{inversions} inversoes: {[(a, round(b, 3)) for a, b in shares]}",
                   severity="CRITICAL"))

    # ---- gradiente de raca e cor no Brasil: base > meio > topo ----
    br_people = people.filter((pl.col("country") == "BR") & pl.col("race_declared"))
    r = {k: _share(br_people.filter(pl.col("job_level_group").is_in(v)),
                   pl.col("race_ethnicity").is_in(["Preta", "Parda"]))
         for k, v in buckets.items()}
    okr = r["base"][0] >= r["meio"][0] >= r["topo"][0]
    out.append(_ok("V31", "share de pessoas pretas e pardas cai da base para o topo no BR",
                   okr, f"base {r['base'][0]:.1%} (n={r['base'][1]}), meio {r['meio'][0]:.1%} "
                        f"(n={r['meio'][1]}), topo {r['topo'][0]:.1%} (n={r['topo'][1]})",
                   severity="CRITICAL"))

    # ---- taxa de nao declaracao por pais, dentro da tolerancia ----
    # Tambem sobre pessoas distintas, e com tolerancia que acompanha o ruido
    # amostral: no perfil smoke um pais pequeno tem poucas dezenas de pessoas.
    start_race = demo["race_ethnicity"]["available_from"]
    devs, violations = [], 0
    for country, target in demo["race_ethnicity"]["not_informed_rate_by_country"].items():
        base = people.filter((pl.col("country") == country) & (pl.col("hire_date") >= start_race))
        if base.height < 30:
            continue
        realized = 1 - base.filter(pl.col("race_declared")).height / base.height
        allowed = max(0.06, 2.5 / (base.height ** 0.5))
        devs.append((country, round(realized, 3), target, base.height, round(allowed, 3)))
        violations += int(abs(realized - target) > allowed)
    out.append(_ok("V32", "taxa de nao declaracao de raca e cor proxima do configurado por pais",
                   violations == 0,
                   f"{violations} paises fora: {[(c, r, t_, n) for c, r, t_, n, _ in devs]}",
                   severity="CRITICAL"))

    # ---- nunca imputar: quem nao declarou nao tem valor concreto ----
    br_values = set(demo["race_ethnicity"]["declared_share_BR"])
    bad = emp.filter((~pl.col("race_declared")) & pl.col("race_ethnicity").is_in(list(br_values)))
    out.append(_ok("V33", "quem nao declarou nunca recebe valor de raca e cor imputado",
                   bad.height == 0, f"{bad.height} registros imputados"))

    # ---- o campo nao existe antes da data de disponibilidade ----
    start = demo["race_ethnicity"]["available_from"]
    early = emp.filter(pl.col("race_declared_at").is_not_null() & (pl.col("race_declared_at") < start))
    out.append(_ok("V34", "nenhuma declaracao de raca e cor antes de o campo existir",
                   early.height == 0, f"{early.height} registros antes de {start}"))

    # ---- evolucao temporal da lideranca segue a tendencia configurada ----
    lead_groups = ["Manager", "Senior Manager", "Director", "Executive"]
    trend = demo["gender"].get("leadership_trend_per_year_from_2021", 0.0)
    series = []
    for year in sorted(j["year"].unique().to_list()):
        sub = j.filter((pl.col("year") == year) & pl.col("job_level_group").is_in(lead_groups))
        if sub.height >= 30:
            series.append((year, sub.filter(pl.col("gender") == "Female").height / sub.height))
    # a tendencia configurada e pequena (cerca de 1,2 p.p. por ano) e atinge so
    # quem entra na lideranca, entao a serie anual e ruidosa. Comparamos medias
    # de tres anos nas pontas e tratamos como WARNING: e tendencia estatistica,
    # nao invariante estrutural.
    post = [v for y, v in series if y >= 2021]
    if len(post) >= 4:
        grew = sum(post[-3:]) / 3 - sum(post[:3]) / 3
    else:
        grew = (post[-1] - post[0]) if len(post) >= 2 else 0.0
    out.append(_ok("V35", "share feminino na lideranca nao anda contra a tendencia configurada",
                   (trend <= 0) or (grew > -0.01),
                   f"variacao de {grew:+.1%} entre as pontas da serie pos-2021", severity="WARNING"))

    # ---- idade coerente com a faixa de admissao do nivel ----
    # a faixa etaria e a do nivel NA ADMISSAO, nao a do nivel atual: quem entrou
    # como Entry aos 19 e hoje e Manager continua tendo entrado aos 19
    ages = demo["birth_year"]["hire_age_by_level_group"]
    bad_age = 0
    for r in emp.select(["birth_year", "hire_date", "hire_job_level_group"]).to_dicts():
        lo, hi = ages[r["hire_job_level_group"]]
        age = r["hire_date"].year - r["birth_year"]
        if not (lo - 1 <= age <= hi + 1):
            bad_age += 1
    out.append(_ok("V36", "idade na admissao dentro da faixa configurada para o nivel",
                   bad_age == 0, f"{bad_age} registros fora da faixa"))

    # ---- coerencia entre populacao e liderança: nenhum grupo desaparece ----
    genders = set(emp["gender"].unique().to_list())
    lead = emp.filter(pl.col("job_level_group").is_in(lead_groups))
    missing = {g for g in genders if g in ("Female", "Male") and lead.filter(pl.col("gender") == g).height == 0}
    out.append(_ok("V37", "nenhum genero presente na forca de trabalho some da lideranca",
                   not missing, f"ausentes na lideranca: {sorted(missing)}"))

    return out


def summary(checks: list[Check]) -> tuple[int, int]:
    passed = sum(1 for c in checks if c.passed)
    return passed, len(checks)


def blocking(checks: list[Check]) -> list[Check]:
    """Falhas que impedem a fase de fechar.

    WARNING nao bloqueia: sinaliza tendencia estatistica que pode nao se
    realizar numa amostra pequena. Continua sendo reportada sempre, para que
    nao vire falha silenciosa.
    """
    return [c for c in checks if not c.passed and c.severity in ("BLOCKER", "CRITICAL")]
