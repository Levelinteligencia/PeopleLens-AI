"""Construcao da estrutura organizacional da NOVAORA.

Tudo aqui e derivado de config/generation.yaml. Nenhum nome de area, familia
ou cargo esta escrito neste arquivo: se precisar mudar a estrutura, muda o
YAML (exigencia da Sam na aprovacao da F0, item 2).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np

from ..config import Config


@dataclass(frozen=True)
class OrgUnit:
    org_key: int
    country: str
    business_unit: str
    department: str
    sub_department: str
    segment: str
    cost_center: str
    weight: float          # peso relativo de headcount dentro do pais
    valid_from: date
    valid_to: date | None = None


@dataclass
class Organization:
    units: list[OrgUnit]
    job_family_by_department: dict[str, list[str]]
    locations_by_unit: dict[int, list[str]] = field(default_factory=dict)

    def by_country(self, country: str) -> list[OrgUnit]:
        return [u for u in self.units if u.country == country]

    def get(self, org_key: int) -> OrgUnit:
        return self._index[org_key]

    def __post_init__(self) -> None:
        self._index = {u.org_key: u for u in self.units}


def _bu_weights(cfg: Config) -> dict[str, float]:
    """Distribui o hc_share de cada segmento entre as business units daquele
    segmento, proporcionalmente ao numero de departamentos de cada uma."""
    org = cfg.org
    segs = cfg.segments
    by_segment: dict[str, list[str]] = {}
    for bu, meta in org["business_units"].items():
        by_segment.setdefault(meta["segment"], []).append(bu)

    weights: dict[str, float] = {}
    for seg, bus in by_segment.items():
        sizes = {bu: len(org["business_units"][bu]["departments"]) for bu in bus}
        total = sum(sizes.values())
        for bu in bus:
            weights[bu] = segs[seg]["hc_share"] * sizes[bu] / total
    return weights


def build(cfg: Config) -> Organization:
    org = cfg.org
    start, _ = cfg.period
    bu_w = _bu_weights(cfg)
    presence = org["country_bu_presence"]
    bu_codes = org["cost_center"]["bu_codes"]
    cc_pattern = org["cost_center"]["pattern"]

    units: list[OrgUnit] = []
    key = 0
    for country in [c["code"] for c in cfg.countries]:
        raw: list[tuple] = []
        for bu, meta in org["business_units"].items():
            pres = presence[country][bu]
            if pres <= 0:
                continue
            departments = list(meta["departments"].items())
            for dept_idx, (dept, dmeta) in enumerate(departments, start=1):
                subs = dmeta["sub_departments"]
                for sub in subs:
                    # peso: share da BU x presenca no pais, dividido igualmente
                    # entre departamentos e sub departamentos
                    w = bu_w[bu] * pres / (len(departments) * len(subs))
                    raw.append((bu, meta["segment"], dept, dept_idx, sub, w))

        total_w = sum(r[5] for r in raw)
        for bu, seg, dept, dept_idx, sub, w in raw:
            key += 1
            units.append(
                OrgUnit(
                    org_key=key,
                    country=country,
                    business_unit=bu,
                    department=dept,
                    sub_department=sub,
                    segment=seg,
                    cost_center=cc_pattern.format(
                        country=country, bu_code=bu_codes[bu], dept_index=dept_idx
                    ),
                    weight=w / total_w,
                    valid_from=start,
                )
            )

    return Organization(units=units, job_family_by_department=org["job_family_by_department"])


def build_locations(cfg: Config, organization: Organization, hc_by_country: dict[str, int]) -> dict[str, dict[str, list[str]]]:
    """Locais por pais e business unit, com quantidade escalada pelo headcount.

    Retorna {country: {business_unit: [location, ...]}}.
    """
    rules = cfg.org["locations"]
    pattern = rules["pattern"]
    out: dict[str, dict[str, list[str]]] = {}
    for country, hc in hc_by_country.items():
        out[country] = {}
        for bu, rule in rules["rule_by_business_unit"].items():
            per = rule["per_n_employees"]
            n = rules["min_units"] if per == 0 else max(rules["min_units"], round(hc / per))
            out[country][bu] = [
                pattern.format(prefix=rule["prefix"], country=country, index=i)
                for i in range(1, int(n) + 1)
            ]
    return out


def job_title(cfg: Config, job_family: str, job_level: str) -> str:
    rule = cfg.org["job_title_rule"]
    seniority = rule["seniority_by_level"][job_level]
    return rule["pattern"].format(seniority=seniority, job_family_singular=job_family)


def sample_level(cfg: Config, rng: np.random.Generator, segment: str, skew: dict | float | None = None) -> str:
    """Sorteia o nivel de um colaborador.

    `skew` aplica o vies de contratacao externa: a empresa contrata
    proporcionalmente mais na base do que a piramide alvo, e as posicoes
    seniores restantes sao preenchidas por promocao interna. Sem esse vies a
    piramide nasceria ja no alvo e nao haveria vaga para promover.
    """
    dist = cfg.org["level_distribution"][segment]
    levels = list(dist)
    p = np.array([dist[lv] for lv in levels], dtype=float)
    if skew is not None:
        factor = float(skew["factor"]) if isinstance(skew, dict) else float(skew)
        floor = float(skew.get("floor", 0.0)) if isinstance(skew, dict) else 0.0
        ranks = np.arange(len(levels), dtype=float)
        p = p * np.maximum(factor ** ranks, floor)
    p = p / p.sum()          # normaliza o arredondamento do YAML e o vies
    return str(rng.choice(levels, p=p))


def sample_job_family(organization: Organization, rng: np.random.Generator, department: str) -> str:
    options = organization.job_family_by_department[department]
    return str(rng.choice(options))
