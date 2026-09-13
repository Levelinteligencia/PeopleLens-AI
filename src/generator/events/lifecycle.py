"""Motor de eventos: simula a NOVAORA verdadeira, mes a mes.

O gerador nao escreve tabelas, ele simula vidas. Cada pessoa e uma sequencia de
eventos encadeados, e as tabelas fato sao materializacoes desse log
(`materialize.py`). Isso garante, por construcao, que a camada de verdade seja
internamente coerente: ninguem muda de area depois de desligado, nenhum gestor
e inexistente, nenhum snapshot contradiz as datas de admissao e saida.

F1 gera SOMENTE o ground truth. Nao ha projecao em sistemas-fonte nem injecao
de defeitos: isso e F2.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from ..config import Config
from ..rng import RngBook
from ..world import organization as orgmod
from ..world import population as popmod
from ..world.calendar import Calendar, add_months, end_of_month, months_between
from . import hazard

CANON_RATINGS = [
    "Below Expectations",
    "Developing",
    "Meets Expectations",
    "Exceeds Expectations",
    "Outstanding",
]


# --------------------------------------------------------------------------- #
@dataclass
class Employee:
    employee_id: int
    hire_date: date
    origin: str                      # initial | organic | acquisition_<nome>
    full_name: str
    country: str
    org_key: int
    business_unit: str
    department: str
    sub_department: str
    segment: str
    job_family: str
    job_level: str
    hire_job_level: str
    job_title: str
    location: str
    cost_center: str
    employment_type: str
    fte: float
    gender: str
    race_ethnicity: str | None
    race_declared: bool
    race_declared_at: date | None
    disability_flag: bool | None
    disability_declared: bool
    disability_declared_at: date | None
    birth_year: int
    base_salary: float
    currency: str
    band_mid: float
    manager_id: int | None = None
    manager_effect: float = 1.0
    termination_date: date | None = None
    last_rating: str | None = None
    eng_history: list[float | None] = field(default_factory=list)
    last_promotion: date | None = None
    n_reports: int = 0

    @property
    def active(self) -> bool:
        return self.termination_date is None

    def tenure_months(self, at: date) -> int:
        return max(0, months_between(self.hire_date, at))


@dataclass
class Truth:
    employees: dict[int, Employee]
    events: list[dict]
    snapshots: list[dict]
    terminations: list[dict]
    movements: list[dict]
    compensation: list[dict]
    performance: list[dict]
    learning: list[dict]
    engagement: list[dict]
    requisitions: list[dict]
    applications: list[dict]
    manager_changes: list[dict]
    state_log: list[dict]
    org_units: list[orgmod.OrgUnit]
    salary_bands: list[dict]


# --------------------------------------------------------------------------- #
class World:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.rng = RngBook(cfg.seed)
        self.cal = Calendar(*cfg.period)
        self.org = orgmod.build(cfg)
        self.plan = popmod.headcount_plan(cfg, self.cal)

        self.levels = list(cfg.org["job_levels"])
        self.employees: dict[int, Employee] = {}
        self.active: set[int] = set()
        self._next_id = 1
        self._next_req = 1
        self._next_cand = 1

        self.events: list[dict] = []
        self.snapshots: list[dict] = []
        self.terminations: list[dict] = []
        self.movements: list[dict] = []
        self.compensation: list[dict] = []
        self.performance: list[dict] = []
        self.learning: list[dict] = []
        self.engagement: list[dict] = []
        self.requisitions: list[dict] = []
        self.applications: list[dict] = []
        self.manager_changes: list[dict] = []
        self.state_log: list[dict] = []

        self._locations = orgmod.build_locations(
            cfg, self.org, {c["code"]: int(cfg.generation["headcount"]["targets"][2026] * cfg.scale
                                           * c["share_2026"]) for c in cfg.countries}
        )
        self.salary_bands = self._build_bands()
        self._band_index = {(b["country"], b["job_level"], b["job_family"]): b for b in self.salary_bands}
        self._incidents = self._index_incidents()
        self._deferred: dict[date, list[tuple[dict, dict]]] = {}

    # ------------------------------------------------------------------ setup
    def _build_bands(self) -> list[dict]:
        comp = self.cfg.generation["compensation"]
        bands = comp["bands"]
        spread = bands["spread"]
        prem = bands["job_family_premium"]
        out = []
        for c in self.cfg.countries:
            base = comp["local_base_monthly"][c["code"]]
            for level, mult in bands["level_multiplier"].items():
                for fam in self.cfg.org["job_families"]:
                    mid = base * mult * prem.get(fam, prem["default"])
                    out.append(
                        dict(
                            country=c["code"],
                            job_level=level,
                            job_family=fam,
                            currency=c["currency"],
                            band_min=round(mid * spread["min"], 2),
                            band_mid=round(mid, 2),
                            band_max=round(mid * spread["max"], 2),
                            valid_from=self.cal.months[0],
                            valid_to=None,
                        )
                    )
        return out

    def _index_incidents(self) -> dict[date, list[dict]]:
        idx: dict[date, list[dict]] = {}
        for inc in self.cfg.incidents["incidents"]:
            d = inc.get("date")
            if d is None:
                rng_ = inc.get("date_range")
                d = rng_[0] if rng_ else None
            if d is None:
                continue
            key = date(d.year, d.month, 1)
            idx.setdefault(key, []).append(inc)
        return idx

    # -------------------------------------------------------------- utilidades
    def _units_available(self, country: str, at: date) -> list[orgmod.OrgUnit]:
        bus = self.cfg.org["business_units"]
        out = []
        for u in self.org.by_country(country):
            av = bus[u.business_unit].get("available_from")
            if av is not None and at < av:
                continue
            out.append(u)
        return out

    def _pick_unit(self, rng: np.random.Generator, country: str, at: date) -> orgmod.OrgUnit:
        units = self._units_available(country, at)
        w = np.array([u.weight for u in units], dtype=float)
        w = w / w.sum()
        return units[int(rng.choice(len(units), p=w))]

    def _pick_location(self, rng: np.random.Generator, unit: orgmod.OrgUnit) -> str:
        opts = self._locations[unit.country][unit.business_unit]
        return str(rng.choice(opts))

    def _band(self, country: str, level: str, family: str) -> dict:
        return self._band_index[(country, level, family)]

    def _level_targets(self) -> dict[tuple[str, str], float]:
        return {
            (seg, lv): share
            for seg, dist in self.cfg.org["level_distribution"].items()
            for lv, share in dist.items()
        }

    def _log_state(self, e: "Employee", at: date, reason: str) -> None:
        """Registra o estado completo do colaborador num instante.

        E a partir deste log que o SCD2 de dim_employee e construido em
        materialize.py, com datas exatas em vez de inferencia por snapshot.
        """
        self.state_log.append(dict(
            employee_id=e.employee_id, effective_from=at, change_reason=reason,
            country=e.country, org_key=e.org_key, business_unit=e.business_unit,
            department=e.department, sub_department=e.sub_department, segment=e.segment,
            job_family=e.job_family, job_level=e.job_level,
            job_level_group=self.cfg.level_group(e.job_level), job_title=e.job_title,
            location=e.location, cost_center=e.cost_center, manager_id=e.manager_id,
            employment_type=e.employment_type, fte=e.fte,
            employment_status="Terminated" if reason == "Termination" else "Active",
        ))

    # ----------------------------------------------------------------- gestores
    def _candidates_for_manager(self, emp: Employee) -> list[Employee]:
        rank = self.cfg.level_rank(emp.job_level)
        pools = [
            lambda e: (e.country, e.business_unit, e.department) == (emp.country, emp.business_unit, emp.department),
            lambda e: (e.country, e.business_unit) == (emp.country, emp.business_unit),
            lambda e: e.country == emp.country,
            lambda e: True,
        ]
        for match in pools:
            cands = [
                e for i in self.active
                if (e := self.employees[i]).employee_id != emp.employee_id
                and self.cfg.level_rank(e.job_level) > rank
                and match(e)
            ]
            if cands:
                return cands
        # Ninguem de nivel superior esta ativo: o topo da hierarquia reporta a
        # alguem do mesmo nivel admitido antes. A ordem por data de admissao e
        # estrita, entao nao ha ciclo, e sobra exatamente uma pessoa sem gestor.
        peers = [
            e for i in self.active
            if (e := self.employees[i]).employee_id != emp.employee_id
            and self.cfg.level_rank(e.job_level) == rank
            and (e.hire_date, e.employee_id) < (emp.hire_date, emp.employee_id)
        ]
        return peers

    def _assign_manager(self, emp: Employee, at: date | None = None) -> None:
        cands = self._candidates_for_manager(emp)
        if not cands:
            emp.manager_id = None
            return
        rank = self.cfg.level_rank(emp.job_level)
        cands.sort(key=lambda e: (self.cfg.level_rank(e.job_level) - rank, e.n_reports))
        best = cands[0]
        closest = [e for e in cands if self.cfg.level_rank(e.job_level) == self.cfg.level_rank(best.job_level)]
        chosen = min(closest, key=lambda e: e.n_reports)
        previous = emp.manager_id
        if previous is not None and previous in self.employees:
            self.employees[previous].n_reports -= 1
        emp.manager_id = chosen.employee_id
        chosen.n_reports += 1
        if at is not None and previous != emp.manager_id:
            self.manager_changes.append(dict(employee_id=emp.employee_id, change_date=at,
                                             old_manager_id=previous, new_manager_id=emp.manager_id))
            self._log_state(emp, at, "Manager Change")

    def _reassign_reports(self, manager_id: int, at: date) -> None:
        reports = [i for i in self.active if self.employees[i].manager_id == manager_id]
        for i in reports:
            emp = self.employees[i]
            # _assign_manager cuida de decrementar o gestor anterior e de
            # registrar a mudanca em manager_changes, o que alimenta o SCD2.
            self._assign_manager(emp, at=at)

    # ------------------------------------------------------------------- hiring
    def _new_employee(
        self,
        at: date,
        country: str,
        origin: str,
        rng: np.random.Generator,
        hire_date: date | None = None,
        level: str | None = None,
    ) -> Employee:
        unit = self._pick_unit(rng, country, at)
        skew = self.cfg.generation["career_events"].get("hiring_level_skew")
        lv = level or orgmod.sample_level(self.cfg, rng, unit.segment, skew=skew)
        fam = orgmod.sample_job_family(self.org, rng, unit.department)
        hd = hire_date or at
        group = self.cfg.level_group(lv)
        demo = popmod.sample_demographics(self.cfg, rng, country, group, hd)
        etype, fte = popmod.sample_employment(self.cfg, rng, unit.segment)
        band = self._band(country, lv, fam)
        cr = self.cfg.generation["compensation"]["compa_ratio"]
        ratio = float(np.clip(rng.normal(cr["target_mean"], cr["sigma"]), *cr["clip"]))

        emp = Employee(
            employee_id=self._next_id,
            hire_date=hd,
            origin=origin,
            full_name=popmod.sample_name(self.cfg, rng),
            country=country,
            org_key=unit.org_key,
            business_unit=unit.business_unit,
            department=unit.department,
            sub_department=unit.sub_department,
            segment=unit.segment,
            job_family=fam,
            job_level=lv,
            hire_job_level=lv,
            job_title=orgmod.job_title(self.cfg, fam, lv),
            location=self._pick_location(rng, unit),
            cost_center=unit.cost_center,
            employment_type=etype,
            fte=fte,
            gender=demo.gender,
            race_ethnicity=demo.race_ethnicity,
            race_declared=demo.race_declared,
            race_declared_at=hd if demo.race_ethnicity is not None else None,
            disability_flag=demo.disability_flag,
            disability_declared=demo.disability_declared,
            disability_declared_at=hd if demo.disability_declared else None,
            birth_year=demo.birth_year,
            base_salary=round(band["band_mid"] * ratio, 2),
            currency=band["currency"],
            band_mid=band["band_mid"],
            manager_effect=hazard.draw_manager_effect(self.cfg, rng),
        )
        self._next_id += 1
        self.employees[emp.employee_id] = emp
        self.active.add(emp.employee_id)
        self._assign_manager(emp)
        self.events.append(dict(employee_id=emp.employee_id, event_date=hd,
                                event_type="HIRE" if origin == "organic" else origin.upper(),
                                detail=origin))
        self._log_state(emp, hd, "Hire")
        self.compensation.append(dict(employee_id=emp.employee_id, effective_date=hd,
                                      base_salary=emp.base_salary, currency=emp.currency,
                                      change_reason="Hire", job_level=lv, country=country,
                                      department=emp.department, band_mid=emp.band_mid))
        return emp

    # -------------------------------------------------------------------- setup
    def _seed_population(self) -> None:
        first = self.cal.months[0]
        rng = self.rng.get("seed_population")
        target = self.plan[first]
        shares = popmod.country_shares(self.cfg, first.year)
        tenures = popmod.initial_tenure_months(rng, target)
        i = 0
        for country, share in shares.items():
            n = int(round(target * share))
            for _ in range(n):
                hd = add_months(first, -int(tenures[min(i, len(tenures) - 1)]))
                self._new_employee(first, country, "initial", rng, hire_date=hd)
                i += 1

        # Segunda passada: as primeiras pessoas criadas ficaram sem gestor
        # porque, no instante da criacao, ainda nao existia ninguem de nivel
        # superior. Com a populacao inicial completa, a hierarquia e refeita.
        for eid in sorted(self.active):
            emp = self.employees[eid]
            emp.manager_id = None
            emp.n_reports = 0
        for eid in sorted(self.active, key=lambda x: -self.cfg.level_rank(self.employees[x].job_level)):
            self._assign_manager(self.employees[eid])

        # a atribuicao acima e conceitualmente do instante da admissao, nao uma
        # mudanca posterior: corrige a versao de origem no state_log em vez de
        # criar uma nova versao SCD2
        seeded = set(self.active)
        for row in self.state_log:
            if row["change_reason"] == "Hire" and row["employee_id"] in seeded:
                row["manager_id"] = self.employees[row["employee_id"]].manager_id

    # ------------------------------------------------------------------ eventos
    def _terminations(self, m: date) -> None:
        rng = self.rng.get("terminations", m.isoformat())
        cfgh = self.cfg.generation["termination_hazard"]
        by_segment: dict[str, list[int]] = {}
        for i in self.active:
            by_segment.setdefault(self.employees[i].segment, []).append(i)

        to_end: list[int] = []
        for seg, ids in by_segment.items():
            scores = []
            for i in ids:
                e = self.employees[i]
                lag = cfgh["engagement_factor"]["lag_cycles"]
                eng = e.eng_history[-lag] if len(e.eng_history) >= lag else None
                scores.append(
                    hazard.tenure_factor(self.cfg, e.tenure_months(m))
                    * hazard.performance_factor(self.cfg, e.last_rating)
                    * hazard.level_factor(self.cfg, e.job_level)
                    * hazard.engagement_factor(self.cfg, eng)
                    * hazard.country_factor(self.cfg, e.country)
                    * e.manager_effect
                )
            p = hazard.monthly_probabilities(self.cfg, seg, m.year, np.array(scores))
            draws = rng.random(len(ids))
            to_end.extend([i for i, pi, d in zip(ids, p, draws) if d < pi])

        for i in to_end:
            self._terminate(i, m, rng, forced_type=None)

    def _terminate(self, emp_id: int, m: date, rng: np.random.Generator, forced_type: str | None) -> None:
        emp = self.employees[emp_id]
        # convencao intra-mes: admissao entre os dias 1 e 14, movimentacao no
        # dia 15, desligamento entre 16 e 28. Isso ordena os eventos dentro do
        # mes por construcao e elimina uma classe inteira de incoerencia.
        day = int(rng.integers(16, 29))
        td = date(m.year, m.month, day)
        if td < emp.hire_date:
            td = emp.hire_date
        emp.termination_date = td
        self.active.discard(emp_id)

        mix = self.cfg.generation["termination_mix"]
        if forced_type:
            tmeta = next(t for t in mix["types"] if t["type"] == forced_type)
        else:
            vol = rng.random() < mix["voluntary_share_base"]
            pool = [t for t in mix["types"] if t["voluntary"] == vol] or mix["types"]
            tmeta = pool[int(rng.integers(0, len(pool)))]
        regrettable = bool(rng.random() < tmeta["regrettable_rate"])

        self.terminations.append(dict(
            termination_id=f"TERM{emp_id:07d}",
            employee_id=emp_id, termination_date=td,
            termination_type=tmeta["type"], termination_reason=tmeta["type"],
            voluntary_flag=bool(tmeta["voluntary"]), regrettable_flag=regrettable,
            department=emp.department, business_unit=emp.business_unit,
            sub_department=emp.sub_department, job_family=emp.job_family,
            job_level=emp.job_level, manager_id=emp.manager_id,
            tenure_months=emp.tenure_months(td), country=emp.country, segment=emp.segment,
        ))
        self.events.append(dict(employee_id=emp_id, event_date=td,
                                event_type="TERMINATION", detail=tmeta["type"]))
        self._log_state(emp, td, "Termination")
        if emp.manager_id is not None and emp.manager_id in self.employees:
            self.employees[emp.manager_id].n_reports = max(0, self.employees[emp.manager_id].n_reports - 1)
        if emp.n_reports > 0:
            self._reassign_reports(emp_id, td)

    def _hires(self, m: date) -> None:
        rng = self.rng.get("hires", m.isoformat())
        target = self.plan[m]
        gap = target - len(self.active)
        if gap <= 0:
            return
        shares = popmod.country_shares(self.cfg, m.year)
        freeze = self._hiring_freeze_factor(m)
        n = int(round(gap * freeze))
        codes = list(shares)
        probs = np.array([shares[c] for c in codes])
        for _ in range(n):
            country = codes[int(rng.choice(len(codes), p=probs))]
            day = int(rng.integers(1, 15))
            emp = self._new_employee(m, country, "organic", rng, hire_date=date(m.year, m.month, day))
            self._recruitment_for(emp, rng)

    def _hiring_freeze_factor(self, m: date) -> float:
        for inc in self.cfg.incidents["incidents"]:
            for eff in inc.get("effects", []) or []:
                if eff.get("kind") == "hiring_freeze":
                    a, b = eff["date_range"]
                    if a <= date(m.year, m.month, 1) <= b:
                        return 1.0 - float(eff["intensity"]) * 0.5
        return 1.0

    # ------------------------------------------------------------- recrutamento
    def _recruitment_for(self, emp: Employee, rng: np.random.Generator, filled: bool = True) -> None:
        rec = self.cfg.generation["recruitment"]
        cd = rec["cycle_days"]
        mult = rec["cycle_multiplier_by_level_group"][self.cfg.level_group(emp.job_level)]

        def days(key: str) -> int:
            lo, hi = cd[key]
            return max(0, int(round(rng.integers(lo, hi + 1) * mult)))

        hire_d = emp.hire_date
        offer_d = hire_d - timedelta(days=days("offer_to_hire"))
        intv_d = offer_d - timedelta(days=days("interview_to_offer"))
        scr_d = intv_d - timedelta(days=days("screening_to_interview"))
        app_d = scr_d - timedelta(days=days("application_to_screening"))
        post_d = app_d - timedelta(days=days("posting_to_application"))
        appr_d = post_d - timedelta(days=days("approval_to_posting"))
        open_d = appr_d - timedelta(days=days("opening_to_approval"))

        req_id = f"REQ{self._next_req:07d}"
        self._next_req += 1
        self.requisitions.append(dict(
            requisition_id=req_id, position_id=f"POS{self._next_req:07d}",
            country=emp.country, business_unit=emp.business_unit, department=emp.department,
            sub_department=emp.sub_department, job_family=emp.job_family, job_level=emp.job_level,
            location=emp.location, opening_date=open_d, approval_date=appr_d, posting_date=post_d,
            requisition_status="Filled" if filled else "Cancelled",
            recruiter_id=f"REC{int(rng.integers(1, max(2, int(40 * self.cfg.scale) + 2))):04d}",
            hire_date=hire_d if filled else None,
        ))

        sources = rec["candidate_sources"]
        snames = [s["name"] for s in sources]
        sprob = np.array([s["share"] for s in sources]); sprob = sprob / sprob.sum()
        n_apps = max(1, int(round(rng.normal(rec["applications_per_requisition"]["mean"],
                                             rec["applications_per_requisition"]["sigma"]))))
        conv = rec["funnel_conversion"]
        for k in range(n_apps):
            cid = f"CAND{self._next_cand:08d}"
            self._next_cand += 1
            is_hired = filled and k == 0
            a_date = app_d if is_hired else app_d + timedelta(days=int(rng.integers(-20, 21)))
            src = "Internal Mobility" if is_hired and rng.random() < rec["internal_share_target"] else str(rng.choice(snames, p=sprob))
            if is_hired:
                s_d, i_d, o_d, h_d, acc = scr_d, intv_d, offer_d, hire_d, True
            else:
                s_d = a_date + timedelta(days=days("application_to_screening")) if rng.random() < conv["application_to_screening"] else None
                i_d = s_d + timedelta(days=days("screening_to_interview")) if s_d and rng.random() < conv["screening_to_interview"] else None
                o_d = i_d + timedelta(days=days("interview_to_offer")) if i_d and rng.random() < conv["interview_to_offer"] else None
                acc = bool(o_d and rng.random() < conv["offer_to_acceptance"] and False)  # so o k=0 vira contratacao
                h_d = None
            self.applications.append(dict(
                requisition_id=req_id, candidate_id=cid,
                employee_id=emp.employee_id if is_hired else None,
                application_date=a_date, screening_date=s_d, interview_date=i_d,
                offer_date=o_d, hire_date=h_d, offer_accepted_flag=bool(acc or is_hired),
                candidate_source=src,
                internal_external="Internal" if src == "Internal Mobility" else "External",
            ))

    def _unfilled_requisitions(self, m: date) -> None:
        """Requisicoes abertas que nao viram contratacao (vaga cancelada ou
        congelada). Na verdade do mundo elas existem: nao sao defeito."""
        rng = self.rng.get("unfilled_req", m.isoformat())
        rec = self.cfg.generation["recruitment"]
        base_rate = 1.0 - 1.0 / rec["requisitions_per_hire"]
        year_rate = base_rate
        for inc in self.cfg.incidents["incidents"]:
            for eff in inc.get("effects", []) or []:
                if eff.get("kind") == "requisition_cancellation_rate" and eff.get("year") == m.year:
                    year_rate = float(eff["value"])
        hires_this_month = sum(1 for r in self.requisitions if r["hire_date"] and
                               r["hire_date"].year == m.year and r["hire_date"].month == m.month)
        n = int(round(hires_this_month * year_rate / max(1e-9, 1 - year_rate)))
        if n <= 0 or not self.active:
            return
        pool = list(self.active)
        for _ in range(n):
            proxy = self.employees[pool[int(rng.integers(0, len(pool)))]]
            ghost = Employee(**{**proxy.__dict__, "employee_id": -1,
                                "hire_date": date(m.year, m.month, int(rng.integers(1, 15)))})
            ghost.eng_history = []
            self._recruitment_for(ghost, rng, filled=False)

    # -------------------------------------------------------------- movimentacao
    def _careers(self, m: date) -> None:
        ce = self.cfg.generation["career_events"]
        rng = self.rng.get("careers", m.isoformat())

        if m.month in ce["promotion"]["cycle_months"]:
            self._promotions(m, rng)

        # transferencias e movimentos laterais acontecem ao longo do ano
        for key, mtype in (("transfer", "Transfer"), ("lateral_move", "Lateral Move"), ("demotion", "Demotion")):
            rate = ce[key]["annual_rate"] / 12.0
            for i in list(self.active):
                if rng.random() < rate:
                    self._move(i, m, mtype, rng)

    def _promotions(self, m: date, rng: np.random.Generator) -> None:
        """Ciclo de promocoes.

        Duas mecanicas, ambas necessarias para o resultado ser plausivel:

        1. o peso de performance e normalizado pela media do segmento, de modo
           que a taxa agregada realizada respeita `annual_rate_by_segment` e ao
           mesmo tempo quem esta dentro do gate tem vantagem real;
        2. promocao depende de vaga: nao se promove alem da piramide alvo do
           segmento (com folga de 15%). Sem essa restricao a organizacao
           inverteria ao longo de dez anos.
        """
        ce = self.cfg.generation["career_events"]["promotion"]
        targets = self._level_targets()

        counts: dict[tuple[str, str], int] = {}
        seg_totals: dict[str, int] = {}
        for i in self.active:
            e = self.employees[i]
            counts[(e.segment, e.job_level)] = counts.get((e.segment, e.job_level), 0) + 1
            seg_totals[e.segment] = seg_totals.get(e.segment, 0) + 1

        gate = {str(g).lower().replace(" ", "_") for g in ce["performance_gate"]}

        def weight(e: Employee) -> float:
            key = (e.last_rating or "").lower().replace(" ", "_")
            return 1.0 if key in gate else 0.25

        eligible: dict[str, list[Employee]] = {}
        for i in self.active:
            e = self.employees[i]
            if e.tenure_months(m) >= ce["min_tenure_months"]:
                eligible.setdefault(e.segment, []).append(e)
        mean_w = {seg: float(np.mean([weight(e) for e in lst])) for seg, lst in eligible.items()}

        for seg, lst in eligible.items():
            base = ce["annual_rate_by_segment"][seg] / len(ce["cycle_months"])
            for oi in rng.permutation(len(lst)):
                e = lst[int(oi)]
                rate = base * weight(e) / max(1e-9, mean_w[seg])
                if rng.random() >= rate:
                    continue
                options = ce["paths"].get(e.job_level, {})
                if not options:
                    continue
                names = list(options)
                probs = np.array([options[n] for n in names], dtype=float)
                probs = probs / probs.sum()
                # tenta os destinos na ordem sorteada e para no primeiro que
                # tiver vaga; se nenhum tiver, a pessoa nao e promovida agora
                ranked = sorted(range(len(names)), key=lambda k: -probs[k] * rng.random())
                for k in ranked:
                    nxt = names[k]
                    tol = ce.get("vacancy_tolerance", 1.15)
                    cap = targets.get((seg, nxt), 0.0) * seg_totals[seg] * tol
                    if counts.get((seg, nxt), 0) + 1 > max(1.0, cap):
                        continue
                    counts[(seg, nxt)] = counts.get((seg, nxt), 0) + 1
                    counts[(seg, e.job_level)] = counts.get((seg, e.job_level), 0) - 1
                    self._apply_level_change(e, nxt, m, "Promotion", rng)
                    break

    def _apply_level_change(self, e: Employee, new_level: str, m: date, mtype: str, rng: np.random.Generator) -> None:
        old = dict(department=e.department, sub_department=e.sub_department, job_level=e.job_level,
                   manager_id=e.manager_id, location=e.location)
        e.job_level = new_level
        e.job_title = orgmod.job_title(self.cfg, e.job_family, new_level)
        band = self._band(e.country, new_level, e.job_family)
        e.band_mid = band["band_mid"]
        if mtype == "Promotion":
            lo, hi = self.cfg.generation["compensation"]["promotion_increase"]
            e.base_salary = round(e.base_salary * (1 + rng.uniform(lo, hi)), 2)
            e.last_promotion = date(m.year, m.month, 15)
            self.compensation.append(dict(employee_id=e.employee_id, effective_date=date(m.year, m.month, 15),
                                          base_salary=e.base_salary, currency=e.currency,
                                          change_reason="Promotion", job_level=new_level, country=e.country,
                                          department=e.department, band_mid=e.band_mid))
        self._assign_manager(e, at=date(m.year, m.month, 15))
        self._record_movement(e, m, mtype, old)

    def _move(self, emp_id: int, m: date, mtype: str, rng: np.random.Generator) -> None:
        e = self.employees[emp_id]
        old = dict(department=e.department, sub_department=e.sub_department, job_level=e.job_level,
                   manager_id=e.manager_id, location=e.location)
        if mtype == "Demotion":
            idx = self.levels.index(e.job_level)
            if idx == 0:
                return
            e.job_level = self.levels[idx - 1]
            e.job_title = orgmod.job_title(self.cfg, e.job_family, e.job_level)
        else:
            cross = mtype == "Transfer" and rng.random() < self.cfg.generation["career_events"]["transfer"]["cross_country_share"]
            country = e.country
            if cross:
                codes = [c["code"] for c in self.cfg.countries if c["code"] != e.country and c["entry_year"] <= m.year]
                if codes:
                    country = str(rng.choice(codes))
            unit = self._pick_unit(rng, country, m)
            e.country = unit.country
            e.org_key = unit.org_key
            e.business_unit = unit.business_unit
            e.department = unit.department
            e.sub_department = unit.sub_department
            e.segment = unit.segment
            e.cost_center = unit.cost_center
            e.location = self._pick_location(rng, unit)
            if e.job_family not in self.org.job_family_by_department[unit.department]:
                e.job_family = orgmod.sample_job_family(self.org, rng, unit.department)
                e.job_title = orgmod.job_title(self.cfg, e.job_family, e.job_level)
            band = self._band(e.country, e.job_level, e.job_family)
            e.band_mid = band["band_mid"]
            e.currency = band["currency"]
        self._assign_manager(e, at=date(m.year, m.month, 15))
        self._record_movement(e, m, mtype, old)

    def _record_movement(self, e: Employee, m: date, mtype: str, old: dict) -> None:
        self.movements.append(dict(
            movement_id=f"MOV{len(self.movements) + 1:08d}",
            employee_id=e.employee_id, movement_date=date(m.year, m.month, 15), movement_type=mtype,
            old_department=old["department"], new_department=e.department,
            old_sub_department=old["sub_department"], new_sub_department=e.sub_department,
            old_job_level=old["job_level"], new_job_level=e.job_level,
            old_manager_id=old["manager_id"], new_manager_id=e.manager_id,
            old_location=old["location"], new_location=e.location,
            country=e.country, business_unit=e.business_unit, segment=e.segment,
        ))
        self.events.append(dict(employee_id=e.employee_id, event_date=date(m.year, m.month, 15),
                                event_type=mtype.upper().replace(" ", "_"), detail=e.job_level))
        self._log_state(e, date(m.year, m.month, 15), mtype)

    # ------------------------------------------------------------- remuneracao
    def _merit(self, m: date) -> None:
        comp = self.cfg.generation["compensation"]["merit_cycle"]
        if m.month != comp["month"]:
            return
        rng = self.rng.get("merit", m.isoformat())
        for i in list(self.active):
            e = self.employees[i]
            if e.tenure_months(m) < comp["eligible_min_tenure_months"]:
                continue
            key = (e.last_rating or "Meets Expectations").lower().replace(" ", "_")
            lo, hi = comp["increase_by_performance"].get(key, [0.0, 0.03])
            pct = rng.uniform(lo, hi)
            if pct <= 0:
                continue
            e.base_salary = round(e.base_salary * (1 + pct), 2)
            self.compensation.append(dict(employee_id=e.employee_id, effective_date=date(m.year, m.month, 1),
                                          base_salary=e.base_salary, currency=e.currency,
                                          change_reason="Merit", job_level=e.job_level, country=e.country,
                                          department=e.department, band_mid=e.band_mid))

    # -------------------------------------------------------------- performance
    def _performance_cycle(self, m: date) -> None:
        cfgp = self.cfg.generation["performance"]
        cyc = next((c for c in cfgp["cycles"] if c["valid_from"] <= m.year <= c["valid_to"]), None)
        if cyc is None or m.month not in cyc["months"]:
            return
        scale = next(s for s in cfgp["scales"]
                     if s["valid_from"] <= date(m.year, m.month, 1) and (s["valid_to"] is None or date(m.year, m.month, 1) <= s["valid_to"]))
        rng = self.rng.get("performance", m.isoformat())
        dist = cfgp["rating_distribution"]
        canon = CANON_RATINGS
        probs = np.array([dist[c.lower().replace(" ", "_")] for c in canon]); probs = probs / probs.sum()
        cycle_id = f"{m.year}-{'H1' if m.month <= 6 else 'H2'}" if cyc["frequency"] == "semiannual" else str(m.year)

        for i in list(self.active):
            e = self.employees[i]
            if e.tenure_months(m) < cfgp["eligibility_min_tenure_months"]:
                continue
            k = int(rng.choice(len(canon), p=probs))
            e.last_rating = canon[k]
            self.performance.append(dict(
                employee_id=e.employee_id, review_cycle=cycle_id,
                review_date=date(m.year, m.month, 20),
                performance_rating_recorded=scale["values"][k],
                performance_rating_std=canon[k],
                scale_type=scale["type"],
                potential_rating=str(rng.choice(cfgp["potential_ratings"])),
                promotion_ready_flag=bool(rng.random() < cfgp["promotion_ready_rate"]),
                manager_id=e.manager_id, job_level=e.job_level, country=e.country,
                department=e.department, business_unit=e.business_unit,
            ))

    # ------------------------------------------------------------- aprendizagem
    def _learning(self, m: date) -> None:
        lcfg = self.cfg.generation["learning"]
        if date(m.year, m.month, 1) < lcfg["available_from"]:
            return
        rng = self.rng.get("learning", m.isoformat())
        rate = lcfg["enrollments_per_employee_year"]["mean"] / 12.0
        cats = lcfg["categories"]
        for i in list(self.active):
            e = self.employees[i]
            n = rng.poisson(rate)
            for _ in range(int(n)):
                elig = [c for c in cats
                        if ("segments" not in c or e.segment in c["segments"])
                        and ("level_groups" not in c or self.cfg.level_group(e.job_level) in c["level_groups"])
                        and ("from_year" not in c or m.year >= c["from_year"])]
                if not elig:
                    continue
                c = elig[int(rng.integers(0, len(elig)))]
                lo, hi = c["hours"]
                hours = float(round(rng.uniform(lo, hi), 1))
                comp_rate = lcfg["completion_rate"]["mandatory" if c["mandatory"] else "optional"]
                done = rng.random() < comp_rate
                enroll = max(date(m.year, m.month, int(rng.integers(1, 29))), e.hire_date)
                self.learning.append(dict(
                    employee_id=e.employee_id,
                    course_id=f"CRS-{c['name'][:3].upper()}-{int(rng.integers(1, 40)):03d}",
                    course_category=c["name"], enrollment_date=enroll,
                    completion_date=enroll + timedelta(days=int(rng.integers(3, 70))) if done else None,
                    completion_status="Completed" if done else "In Progress",
                    learning_hours=hours, mandatory_flag=bool(c["mandatory"]),
                    country=e.country, department=e.department, job_level=e.job_level,
                ))

    # --------------------------------------------------------------- engajamento
    def _engagement_cycle(self, m: date) -> None:
        ecfg = self.cfg.generation["engagement"]
        if date(m.year, m.month, 1) < ecfg["available_from"]:
            return
        cyc = next((c for c in ecfg["cycles"] if c["valid_from"] <= m.year <= c["valid_to"]), None)
        if cyc is None or m.month not in cyc["months"]:
            return
        rng = self.rng.get("engagement", m.isoformat())
        sc = ecfg["scores"]
        cycle_id = f"{m.year}-{'H1' if m.month <= 6 else 'H2'}" if cyc["frequency"] == "semiannual" else str(m.year)

        for i in list(self.active):
            e = self.employees[i]
            if e.tenure_months(m) < 3:
                continue
            responded = rng.random() < ecfg["response_rate_by_segment"][e.segment]
            if responded:
                # o efeito de gestor tambem desloca o engajamento: times com
                # maior risco de saida tendem a reportar engajamento menor.
                # Associacao embutida, ver ADR-0015.
                shift = -0.45 * (e.manager_effect - 1.0)
                score = float(np.clip(rng.normal(sc["engagement_mean"] + shift, sc["engagement_sigma"]), 1, 5))
                mscore = float(np.clip(rng.normal(score, 0.6), 1, 5))
                bscore = float(np.clip(rng.normal(score, 0.7), 1, 5))
                enps = 10.0 if score >= sc["enps_promoter_threshold"] else (0.0 if score <= sc["enps_detractor_threshold"] else 5.0)
            else:
                score = mscore = bscore = enps = None
            e.eng_history.append(score)
            self.engagement.append(dict(
                employee_id=e.employee_id, survey_date=date(m.year, m.month, 15), survey_cycle=cycle_id,
                engagement_score=score, eNPS=enps, manager_score=mscore, belonging_score=bscore,
                response_flag=int(responded), country=e.country, department=e.department,
                business_unit=e.business_unit, job_level=e.job_level, manager_id=e.manager_id,
            ))

    # ---------------------------------------------------------------- incidentes
    def _apply_incidents(self, m: date) -> None:
        here = date(m.year, m.month, 1)
        for inc in self._incidents.get(here, []):
            for eff in inc.get("effects", []) or []:
                kind = eff.get("kind")
                # um efeito pode ter data propria, diferente da data do
                # incidente que o contem (por exemplo, o campo de raca e cor
                # so passa a existir um mes depois do inicio da migracao)
                own = eff.get("date")
                if own is not None and date(own.year, own.month, 1) != here:
                    self._deferred.setdefault(date(own.year, own.month, 1), []).append((inc, eff))
                    continue
                if kind == "population_inflow":
                    self._acquisition(m, inc, eff)
                elif kind == "mass_termination":
                    self._mass_termination(m, eff)
                elif kind == "mass_movement":
                    self._mass_movement(m, inc, eff)
                elif kind == "field_appears":
                    self._declaration_campaign(m, inc, eff)

        for inc, eff in self._deferred.pop(here, []):
            if eff.get("kind") == "field_appears":
                self._declaration_campaign(m, inc, eff)

    def _acquisition(self, m: date, inc: dict, eff: dict) -> None:
        rng = self.rng.get("acquisition", inc["id"])
        n = int(round(eff["count"] * self.cfg.scale))
        countries = inc.get("countries", ["BR"])
        tag = "acquisition_" + inc["id"].split("_")[-1].lower()
        for _ in range(n):
            country = str(rng.choice(countries))
            # a populacao adquirida chega com tempo de casa anterior a aquisicao
            prior = int(np.clip(rng.exponential(30), 0, 200))
            hd = add_months(date(m.year, m.month, 1), -prior)
            self._new_employee(m, country, tag, rng, hire_date=hd)

    def _declaration_campaign(self, m: date, inc: dict, eff: dict) -> None:
        """Quando um campo autodeclarado passa a existir, a empresa roda uma
        campanha de autodeclaracao com quem ja esta na casa.

        Sem isso, so quem fosse contratado depois de 2019 teria raca e cor
        preenchidas, e a taxa de declaracao levaria a decada inteira para
        convergir. A nao declaracao continua sendo opcao de primeira classe.
        """
        rng = self.rng.get("declaration_campaign", inc["id"])
        for i in list(self.active):
            e = self.employees[i]
            ref = eff.get("date") or date(m.year, m.month, 1)
            demo = popmod.sample_demographics(
                self.cfg, rng, e.country, self.cfg.level_group(e.job_level), ref,
            )
            if "race_ethnicity" in eff.get("fields", []):
                e.race_ethnicity, e.race_declared = demo.race_ethnicity, demo.race_declared
                e.race_declared_at = ref
            if "disability_flag" in eff.get("fields", []):
                e.disability_flag, e.disability_declared = demo.disability_flag, demo.disability_declared
                e.disability_declared_at = ref if demo.disability_declared else None

    def _mass_termination(self, m: date, eff: dict) -> None:
        rng = self.rng.get("mass_termination", m.isoformat())
        n = int(round(eff["count"] * self.cfg.scale))
        segs = set(eff.get("concentrated_in", [])) if eff.get("concentrated_in") else None
        pool = [i for i in self.active if (segs is None or self.employees[i].segment in segs)]
        if not pool:
            pool = list(self.active)
        chosen = rng.choice(pool, size=min(n, len(pool)), replace=False)
        for i in chosen:
            self._terminate(int(i), m, rng, forced_type=eff.get("termination_type", "Redundancy"))

    def _mass_movement(self, m: date, inc: dict, eff: dict) -> None:
        rng = self.rng.get("mass_movement", inc["id"])
        n = int(round(eff.get("count_approx", 0) * self.cfg.scale))
        pool = list(self.active)
        if not pool:
            return
        chosen = rng.choice(pool, size=min(n, len(pool)), replace=False)
        for i in chosen:
            e = self.employees[int(i)]
            old = dict(department=e.department, sub_department=e.sub_department, job_level=e.job_level,
                       manager_id=e.manager_id, location=e.location)
            unit = self._pick_unit(rng, e.country, m)
            e.org_key, e.business_unit = unit.org_key, unit.business_unit
            e.department, e.sub_department = unit.department, unit.sub_department
            e.segment, e.cost_center = unit.segment, unit.cost_center
            if e.job_family not in self.org.job_family_by_department[unit.department]:
                e.job_family = orgmod.sample_job_family(self.org, rng, unit.department)
                e.job_title = orgmod.job_title(self.cfg, e.job_family, e.job_level)
            self._assign_manager(e, at=date(m.year, m.month, 15))
            self._record_movement(e, m, "Reorganization", old)

    # ------------------------------------------------------------------ snapshot
    def _snapshot(self, m: date) -> None:
        eom = end_of_month(m)
        for i in self.active:
            e = self.employees[i]
            self.snapshots.append(dict(
                employee_id=e.employee_id, snapshot_date=eom, active_flag=1, fte=e.fte,
                country=e.country, business_unit=e.business_unit, department=e.department,
                sub_department=e.sub_department, job_family=e.job_family, job_level=e.job_level,
                job_level_group=self.cfg.level_group(e.job_level), location=e.location,
                manager_id=e.manager_id, employment_type=e.employment_type, org_key=e.org_key,
                segment=e.segment, origin=e.origin,
            ))

    # ---------------------------------------------------------------------- run
    def run(self) -> Truth:
        self._seed_population()
        for m in self.cal.months:
            self._apply_incidents(m)
            self._terminations(m)
            self._hires(m)
            self._unfilled_requisitions(m)
            self._careers(m)
            self._performance_cycle(m)
            self._merit(m)
            self._learning(m)
            self._engagement_cycle(m)
            self._snapshot(m)

        return Truth(
            employees=self.employees, events=self.events, snapshots=self.snapshots,
            terminations=self.terminations, movements=self.movements,
            compensation=self.compensation, performance=self.performance,
            learning=self.learning, engagement=self.engagement,
            requisitions=self.requisitions, applications=self.applications,
            manager_changes=self.manager_changes, state_log=self.state_log,
            org_units=self.org.units, salary_bands=self.salary_bands,
        )
