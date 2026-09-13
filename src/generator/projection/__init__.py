"""Passo B do ADR-0001: projecao da verdade nos sistemas-fonte.

Onda 1 (ADR-0002): HRIS_LEGACY, HRIS_CORE, PAYROLL_BR, ATS_CLOUD e
VIVAMARKET_LEGACY. Os sete sistemas da onda 2 entram depois da F5.
"""
from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from ..config import Config
from ..defects.catalog import Catalog
from ..rng import RngBook
from . import acquisition, ats, hris, payroll
from .base import Context, Ledger

WAVE_1 = ["HRIS_LEGACY", "HRIS_CORE", "PAYROLL_BR", "ATS_CLOUD", "VIVAMARKET_LEGACY"]


def run(cfg: Config, tables: dict[str, pl.DataFrame]) -> tuple[Ledger, dict]:
    ctx = Context(cfg=cfg, tables=tables, rng=RngBook(cfg.seed + 1),
                  ledger=Ledger(), root=Path(cfg.root))
    cat = Catalog(cfg)

    counts: dict[str, dict[str, int]] = {}
    counts["HRIS_LEGACY"] = hris.project_legacy(ctx, cat)
    counts["HRIS_CORE"] = hris.project_core(ctx, cat)
    counts["PAYROLL_BR"] = payroll.project(ctx, cat)
    counts["ATS_CLOUD"] = ats.project(ctx, cat)
    counts["VIVAMARKET_LEGACY"] = acquisition.project(ctx, cat)

    ledger_dir = Path(cfg.root) / "data" / "synthetic" / "truth" / "defect_ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    ctx.ledger.to_frame().write_parquet(ledger_dir / "part-000.parquet", compression="zstd")

    manifest = {
        "phase": "F2", "layer": "raw", "wave": 1, "seed": cfg.seed,
        "profile": cfg.profile, "scale": cfg.scale,
        "rates_status": cfg.defects["meta"].get("rates_status"),
        "systems": counts,
        "ledger_rows": len(ctx.ledger.rows),
    }
    with open(Path(cfg.root) / "data" / "raw" / "manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False, default=str)
    return ctx.ledger, manifest
