"""Plano de headcount e atributos demograficos.

ATENCAO (item 3 da aprovacao da F0): todos os parametros demograficos sao
[SINTETICO]. Eles descrevem uma empresa ficticia e nao representam, nem
pretendem representar, a composicao real de nenhuma populacao, pais ou setor.
Nada aqui deve ser citado como estatistica.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from ..config import Config
from .calendar import Calendar, months_between


# --------------------------------------------------------------------------- #
# Plano de headcount
# --------------------------------------------------------------------------- #
def acquisitions(cfg: Config) -> dict[tuple[int, int], int]:
    """Entradas por aquisicao, lidas de config/incidents.yaml.

    Retorna {(ano, mes): quantidade}. Aquisicao nao e contratacao: ela entra
    como degrau no plano de headcount, e nao como crescimento organico
    distribuido ao longo do ano.
    """
    out: dict[tuple[int, int], int] = {}
    for inc in cfg.incidents["incidents"]:
        d = inc.get("date")
        for eff in inc.get("effects", []) or []:
            if eff.get("kind") == "population_inflow" and d is not None:
                out[(d.year, d.month)] = out.get((d.year, d.month), 0) + int(eff["count"])
    return out


def headcount_plan(cfg: Config, cal: Calendar) -> dict[date, int]:
    """Interpola mes a mes as metas anuais de headcount.

    Tres ajustes sobre a interpolacao linear simples:

    1. escala do perfil ativo (dev a 10%, full a 100%);
    2. sazonalidade de varejo nos meses de pico;
    3. degrau de aquisicao: o crescimento trazido por uma aquisicao nao e
       diluido no ano, ele acontece de uma vez no mes do evento. Sem isso o
       plano e a simulacao divergem no mes da aquisicao.
    """
    targets = cfg.generation["headcount"]["targets"]
    scale = cfg.scale
    seasonal_months = set(cfg.generation["employment"]["seasonal_peak_months"])
    uplift = cfg.generation["employment"]["seasonal_uplift"]
    acq = acquisitions(cfg)
    acq_by_year: dict[int, tuple[int, int]] = {y: (mo, n) for (y, mo), n in acq.items()}

    plan: dict[date, int] = {}
    for m in cal.months:
        y = m.year
        prev = targets.get(y - 1, targets[min(targets)])
        cur = targets[y]
        step_month, step_n = acq_by_year.get(y, (None, 0))
        organic_end = cur - step_n
        frac = (m.month - 1) / 12.0
        base = prev + (organic_end - prev) * frac
        if step_month is not None and m.month >= step_month:
            base += step_n
        if m.month in seasonal_months:
            base *= 1 + uplift
        plan[m] = max(1, int(round(base * scale)))
    return plan


def country_shares(cfg: Config, year: int) -> dict[str, float]:
    """Interpola a distribuicao por pais entre share_2016 e share_2026,
    respeitando o ano de entrada de cada pais."""
    out: dict[str, float] = {}
    for c in cfg.countries:
        if year < c["entry_year"]:
            out[c["code"]] = 0.0
            continue
        f = (year - 2016) / (2026 - 2016)
        f = min(max(f, 0.0), 1.0)
        out[c["code"]] = c["share_2016"] + (c["share_2026"] - c["share_2016"]) * f
    total = sum(out.values())
    return {k: v / total for k, v in out.items()}


# --------------------------------------------------------------------------- #
# Demografia  [SINTETICO]
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Demographics:
    gender: str
    race_ethnicity: str | None
    race_declared: bool
    disability_flag: bool | None
    disability_declared: bool
    birth_year: int


def _female_probability(cfg: Config, level_group: str, year: int) -> float:
    d = cfg.generation["demographics"]["gender"]
    base = d["female_share_by_level_group"][level_group]
    trend = d.get("leadership_trend_per_year_from_2021", 0.0)
    if year > 2021 and level_group in ("Manager", "Senior Manager", "Director", "Executive"):
        base += trend * (year - 2021)
    return float(min(max(base, 0.02), 0.95))


def sample_demographics(
    cfg: Config,
    rng: np.random.Generator,
    country: str,
    level_group: str,
    hire_date: date,
) -> Demographics:
    demo = cfg.generation["demographics"]

    # ---- genero ---------------------------------------------------------- #
    p_f = _female_probability(cfg, level_group, hire_date.year)
    residual = demo["gender"]["base_share"]
    p_nb = residual.get("Non-binary", 0.0)
    p_ni = residual.get("Not informed", 0.0)
    p_m = max(0.0, 1.0 - p_f - p_nb - p_ni)
    gender = str(rng.choice(["Female", "Male", "Non-binary", "Not informed"],
                            p=np.array([p_f, p_m, p_nb, p_ni]) / (p_f + p_m + p_nb + p_ni)))

    # ---- raca e cor ------------------------------------------------------ #
    race_start = demo["race_ethnicity"]["available_from"]
    race_declared = False
    race = None
    if hire_date >= race_start:
        not_inf = demo["race_ethnicity"]["not_informed_rate_by_country"][country]
        if rng.random() >= not_inf:
            race_declared = True
            if country == "BR":
                shares = demo["race_ethnicity"]["declared_share_BR"]
                grad = demo["race_ethnicity"]["preta_parda_share_by_level_group_BR"]
                target_pp = grad[level_group]
                base_pp = shares["Preta"] + shares["Parda"]
                # reescala Preta e Parda para o gradiente do nivel, mantendo a
                # proporcao interna entre elas, e redistribui o restante.
                ratio_p = shares["Preta"] / base_pp
                p_preta, p_parda = target_pp * ratio_p, target_pp * (1 - ratio_p)
                rest = 1 - target_pp
                base_rest = 1 - base_pp
                vals = ["Branca", "Preta", "Parda", "Amarela", "Indigena"]
                probs = [
                    shares["Branca"] / base_rest * rest,
                    p_preta,
                    p_parda,
                    shares["Amarela"] / base_rest * rest,
                    shares["Indigena"] / base_rest * rest,
                ]
                probs = np.array(probs) / np.sum(probs)
                race = str(rng.choice(vals, p=probs))
            else:
                vals = [v for v in demo["race_ethnicity"]["values_by_country"][country]
                        if not v.startswith(("Nao informado", "No informado"))]
                race = str(rng.choice(vals))
        else:
            race = "Nao informado" if country == "BR" else "No informado"

    # ---- deficiencia ----------------------------------------------------- #
    disability = None
    disability_declared = False
    if hire_date >= demo["disability"]["available_from"]:
        if rng.random() >= demo["disability"]["not_informed_rate"]:
            disability_declared = True
            disability = bool(rng.random() < demo["disability"]["declared_rate_by_country"][country])

    # ---- ano de nascimento ----------------------------------------------- #
    lo, hi = demo["birth_year"]["hire_age_by_level_group"][level_group]
    age = int(rng.integers(lo, hi + 1))
    birth_year = hire_date.year - age

    return Demographics(
        gender=gender,
        race_ethnicity=race,
        race_declared=race_declared,
        disability_flag=disability,
        disability_declared=disability_declared,
        birth_year=birth_year,
    )


def name_pools(cfg: Config) -> tuple[list[str], list[str]]:
    n = cfg.generation["demographics"]["names"]
    first = [x.strip() for row in n["first"] for x in row.split(",")]
    last = [x.strip() for row in n["last"] for x in row.split(",")]
    return first, last


def sample_name(cfg: Config, rng: np.random.Generator) -> str:
    """Nome sintetico. O pool e pequeno de proposito: homonimo acontece, e e
    isso que torna a resolucao de identidade da F4 um exercicio real."""
    first, last = name_pools(cfg)
    n1 = first[int(rng.integers(0, len(first)))]
    s1 = last[int(rng.integers(0, len(last)))]
    s2 = last[int(rng.integers(0, len(last)))]
    return f"{n1} {s1} {s2}" if s1 != s2 else f"{n1} {s1}"


def sample_employment(cfg: Config, rng: np.random.Generator, segment: str) -> tuple[str, float]:
    emp = cfg.generation["employment"]
    types = [t["type"] for t in emp["types"]]
    probs = np.array([t["share"] for t in emp["types"]], dtype=float)
    probs = probs / probs.sum()
    etype = str(rng.choice(types, p=probs))

    pt_share = emp["part_time_share_by_segment"].get(segment, 0.0)
    if rng.random() < pt_share:
        fte = emp["fte_values"]["part_time"] if rng.random() < 0.7 else emp["fte_values"]["reduced"]
    else:
        fte = emp["fte_values"]["full_time"]
    return etype, float(fte)


def initial_tenure_months(rng: np.random.Generator, n: int) -> np.ndarray:
    """Tempo de casa ja acumulado pela populacao inicial de jan/2016.

    Sem isto toda a empresa teria sido admitida no mesmo mes e a curva de
    hazard por tenure nao faria sentido nos primeiros anos.
    """
    # mistura de exponencial (maioria recente, cauda longa de veteranos)
    t = rng.exponential(scale=34.0, size=n)
    return np.clip(t, 0, 260).astype(int)
