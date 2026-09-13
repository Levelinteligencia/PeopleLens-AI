"""Acesso ao catalogo de defeitos.

O catalogo vive em `config/defects.yaml` e a estrutura dele esta aprovada
(ADR-0008, Parte A). As TAXAS sao provisorias e serao calibradas ao final da
F2, entao nenhum modulo de projecao pode conter numero de taxa: todos leem
daqui.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from ..config import Config


@dataclass(frozen=True)
class Defect:
    spec: dict

    @property
    def id(self) -> str:
        return self.spec["id"]

    @property
    def dimension(self) -> str:
        return self.spec.get("dimension", "")

    @property
    def kind(self) -> str:
        return self.spec.get("kind", "semantic")

    def systems(self) -> list[str]:
        return self.spec.get("source_systems", [])

    def applies_to_system(self, system: str) -> bool:
        return system in self.systems()

    def in_scope(self, when: date | None, country: str | None = None) -> bool:
        scope = self.spec.get("scope") or {}
        if when is not None and "date_range" in scope:
            a, b = scope["date_range"]
            if not (a <= when <= b):
                return False
        if country is not None and "countries" in scope:
            if country not in scope["countries"]:
                return False
        return True

    def rate(self, country: str | None = None) -> float:
        """Taxa provisoria. Pode ser escalar, por pais ou faixa."""
        if country and "rate_by_country" in self.spec:
            return float(self.spec["rate_by_country"].get(country, 0.0))
        if "rate_range" in self.spec:
            lo, hi = self.spec["rate_range"]
            return float((lo + hi) / 2)
        r = self.spec.get("rate")
        return float(r) if r is not None else 0.0

    def absolute_count(self, scale: float = 1.0) -> int | None:
        scope = self.spec.get("scope") or {}
        if self.spec.get("rate_type") == "absolute" and "absolute_count" in scope:
            return max(1, int(round(scope["absolute_count"] * scale)))
        return None

    def peak_rate(self, when: date) -> float | None:
        for p in self.spec.get("rate_peaks", []) or []:
            if "date_range" in p:
                a, b = p["date_range"]
                if a <= when <= b:
                    return float(p["rate"])
            if "year" in p and p["year"] == when.year:
                return float(p["rate"])
        return None

    def effective_rate(self, when: date | None = None, country: str | None = None) -> float:
        if when is not None:
            peak = self.peak_rate(when)
            if peak is not None:
                return peak
        return self.rate(country)


class Catalog:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._by_id = {d["id"]: Defect(d) for d in cfg.defects["defects"]}

    def __getitem__(self, defect_id: str) -> Defect:
        return self._by_id[defect_id]

    def __contains__(self, defect_id: str) -> bool:
        return defect_id in self._by_id

    def for_system(self, system: str) -> list[Defect]:
        return [d for d in self._by_id.values() if d.applies_to_system(system)]

    @property
    def rates_frozen(self) -> bool:
        return self.cfg.defects["meta"].get("rates_status") == "FROZEN"

    def hit(self, rng: np.random.Generator, defect_id: str,
            when: date | None = None, country: str | None = None) -> bool:
        """Sorteia se este registro sofre o defeito."""
        d = self._by_id[defect_id]
        if not d.in_scope(when, country):
            return False
        return bool(rng.random() < d.effective_rate(when, country))
