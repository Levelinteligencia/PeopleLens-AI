"""Carga e validacao dos arquivos de configuracao declarativa.

Principio (ADR-0001, Technical Design R8): nenhuma regra do mundo NOVAORA vive
em codigo. Este modulo apenas le os YAML de config/ e expoe acesso tipado.
Se um valor nao esta no YAML, ele nao existe.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Config:
    generation: dict[str, Any]
    sources: dict[str, Any]
    incidents: dict[str, Any]
    defects: dict[str, Any]
    root: Path

    # ---------------------------------------------------------------- atalhos
    @property
    def seed(self) -> int:
        return int(self.generation["reproducibility"]["master_seed"])

    @property
    def profile(self) -> str:
        return self.generation["reproducibility"]["active_profile"]

    @property
    def scale(self) -> float:
        prof = self.generation["reproducibility"]["scale_profiles"][self.profile]
        return float(prof["factor"])

    @property
    def period(self) -> tuple[date, date]:
        p = self.generation["company"]["analysis_period"]
        return p["start"], p["end"]

    @property
    def segments(self) -> dict[str, dict]:
        return {s["id"]: s for s in self.generation["segments"]}

    @property
    def countries(self) -> list[dict]:
        return self.generation["countries"]

    @property
    def org(self) -> dict:
        return self.generation["organization"]

    def level_rank(self, level: str) -> int:
        """Ordem hierarquica global. Usada para promocao e linha de reporte."""
        order = list(self.org["job_levels"].keys())
        return order.index(level)

    def level_group(self, level: str) -> str:
        return self.org["job_levels"][level]["group"]


def load(root: Path | str | None = None) -> Config:
    root = Path(root) if root else _project_root()
    cfg_dir = root / "config"

    def read(name: str) -> dict:
        with open(cfg_dir / name, encoding="utf-8") as fh:
            return yaml.safe_load(fh)

    cfg = Config(
        generation=read("generation.yaml"),
        sources=read("sources.yaml"),
        incidents=read("incidents.yaml"),
        defects=read("defects.yaml"),
        root=root,
    )
    validate(cfg)
    return cfg


def validate(cfg: Config) -> None:
    """Falha cedo e com mensagem clara. Config errada e o pior bug possivel,
    porque produz um universo plausivel e errado."""
    errs: list[str] = []

    shares = sum(s["hc_share"] for s in cfg.generation["segments"])
    if abs(shares - 1.0) > 0.001:
        errs.append(f"soma de hc_share dos segmentos = {shares}, esperado 1.0")

    c26 = sum(c["share_2026"] for c in cfg.countries)
    if abs(c26 - 1.0) > 0.001:
        errs.append(f"soma de share_2026 dos paises = {c26}, esperado 1.0")

    org = cfg.org
    levels = set(org["job_levels"])
    for seg, dist in org["level_distribution"].items():
        if set(dist) != levels:
            errs.append(f"level_distribution[{seg}] nao cobre exatamente os job_levels")
        tot = sum(dist.values())
        if abs(tot - 1.0) > 0.01:
            errs.append(f"level_distribution[{seg}] soma {tot:.4f}, fora de 1.0 +/- 0.01")

    departments = {d for bu in org["business_units"].values() for d in bu["departments"]}
    missing = departments - set(org["job_family_by_department"])
    if missing:
        errs.append(f"departments sem job_family_by_department: {sorted(missing)}")

    families = set(org["job_families"])
    bad = {f for v in org["job_family_by_department"].values() for f in v if f not in families}
    if bad:
        errs.append(f"job families referenciadas e inexistentes: {sorted(bad)}")

    codes = {c["code"] for c in cfg.countries}
    if set(org["country_bu_presence"]) != codes:
        errs.append("country_bu_presence nao cobre exatamente os paises declarados")

    bus = set(org["business_units"])
    for code, pres in org["country_bu_presence"].items():
        if set(pres) != bus:
            errs.append(f"country_bu_presence[{code}] nao cobre exatamente as business units")

    seg_ids = set(cfg.segments)
    for bu, meta in org["business_units"].items():
        if meta["segment"] not in seg_ids:
            errs.append(f"business unit {bu} referencia segmento inexistente: {meta['segment']}")

    for level in levels:
        if level not in org["job_title_rule"]["seniority_by_level"]:
            errs.append(f"job_level {level} sem seniority em job_title_rule")

    if errs:
        raise ValueError("configuracao invalida:\n  - " + "\n  - ".join(errs))
