"""Infraestrutura da projecao (passo B do ADR-0001).

A projecao le a camada de verdade e escreve o que cada sistema-fonte "viu",
no formato nativo daquele sistema e com os defeitos que ele carrega.

Duas regras que valem para todos os modulos de projecao:

1. a verdade nunca e alterada, so lida;
2. todo defeito injetado e registrado no **ledger**, com valor verdadeiro e
   valor gravado. O ledger e o gabarito da F2: e contra ele que se mede se o
   pipeline recuperou a realidade.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import polars as pl

from ..config import Config
from ..rng import RngBook


# --------------------------------------------------------------------------- #
@dataclass
class Ledger:
    """Registro de tudo que foi deliberadamente corrompido.

    Alem dos acertos, o ledger conta as TENTATIVAS: quantos registros foram
    oferecidos a cada defeito e qual era a taxa esperada naquele momento. Sem
    isso nao da para medir calibragem de forma honesta, porque a taxa esperada
    varia com o escopo temporal, com os picos por incidente e com o pais.
    """

    rows: list[dict] = field(default_factory=list)
    attempts: list[dict] = field(default_factory=list)

    def record(self, defect_id: str, system: str, dataset: str, record_key: str,
               field_name: str | None, truth_value: Any, raw_value: Any) -> None:
        self.rows.append(dict(
            defect_id=defect_id, source_system=system, dataset=dataset,
            record_key=str(record_key), field=field_name,
            truth_value=None if truth_value is None else str(truth_value),
            raw_value=None if raw_value is None else str(raw_value),
        ))

    def to_frame(self) -> pl.DataFrame:
        return pl.DataFrame(self.rows, infer_schema_length=None) if self.rows else pl.DataFrame(
            schema={"defect_id": pl.Utf8, "source_system": pl.Utf8, "dataset": pl.Utf8,
                    "record_key": pl.Utf8, "field": pl.Utf8, "truth_value": pl.Utf8,
                    "raw_value": pl.Utf8}
        )

    def attempt(self, defect_id: str, system: str, dataset: str, expected: float) -> None:
        self.attempts.append(dict(defect_id=defect_id, source_system=system,
                                  dataset=dataset, expected_rate=expected))

    def count(self, defect_id: str) -> int:
        return sum(1 for r in self.rows if r["defect_id"] == defect_id)

    def calibration(self) -> list[dict]:
        """Taxa esperada versus realizada, por defeito, sistema e dataset."""
        agg: dict[tuple, dict] = {}
        for a in self.attempts:
            k = (a["defect_id"], a["source_system"], a["dataset"])
            g = agg.setdefault(k, {"n": 0, "exp": 0.0, "hits": 0})
            g["n"] += 1
            g["exp"] += a["expected_rate"]
        for r in self.rows:
            k = (r["defect_id"], r["source_system"], r["dataset"])
            if k in agg:
                agg[k]["hits"] += 1
        out = []
        for (did, sysname, ds), g in sorted(agg.items()):
            if g["n"] == 0:
                continue
            out.append(dict(defect_id=did, source_system=sysname, dataset=ds,
                            eligible=g["n"], hits=g["hits"],
                            expected_rate=round(g["exp"] / g["n"], 5),
                            realized_rate=round(g["hits"] / g["n"], 5)))
        return out


@dataclass
class Context:
    cfg: Config
    tables: dict[str, pl.DataFrame]
    rng: RngBook
    ledger: Ledger
    root: Path

    def system(self, code: str) -> dict:
        return self.cfg.sources["systems"][code]

    def hit(self, cat, defect_id: str, system: str, dataset: str,
            when: date | None = None, country: str | None = None) -> bool:
        """Oferece um registro ao defeito e contabiliza a tentativa."""
        d = cat[defect_id]
        expected = d.effective_rate(when, country) if d.in_scope(when, country) else 0.0
        self.ledger.attempt(defect_id, system, dataset, expected)
        return bool(self.rng.get("defect_draw", f"{defect_id}|{system}|{dataset}").random() < expected)

    def out_dir(self, system: str, dataset: str, ingestion: date) -> Path:
        p = self.root / "data" / "raw" / system / dataset / f"ingestion_date={ingestion.isoformat()}"
        p.mkdir(parents=True, exist_ok=True)
        return p


# --------------------------------------------------------------------------- #
# Escritores, um por formato nativo
# --------------------------------------------------------------------------- #
TECH_COLS = ["_source_file", "_row_number", "_ingested_at", "_source_system"]


def _with_technical(rows: list[dict], system: str, filename: str, ingestion: date) -> list[dict]:
    """Colunas tecnicas da landing zone.

    Sao elas que permitem responder "de onde veio esse numero" ate a linha do
    arquivo original, que e o ultimo degrau do lineage (Technical Design 12.3).
    """
    out = []
    for i, r in enumerate(rows, start=1):
        r = dict(r)
        r["_source_file"] = filename
        r["_row_number"] = i
        r["_ingested_at"] = ingestion.isoformat()
        r["_source_system"] = system
        out.append(r)
    return out


def write_csv(path: Path, rows: list[dict], *, encoding: str, delimiter: str,
              system: str, ingestion: date, filename: str = "part-000.csv") -> Path:
    rows = _with_technical(rows, system, filename, ingestion)
    target = path / filename
    cols = list(rows[0].keys()) if rows else []
    with open(target, "w", encoding=encoding, errors="replace", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter=delimiter, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})
    return target


def write_json(path: Path, records: list[dict], *, system: str, ingestion: date,
               filename: str = "part-000.json") -> Path:
    target = path / filename
    payload = {
        "_meta": {"source_system": system, "ingested_at": ingestion.isoformat(), "file": filename},
        "records": records,
    }
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, default=str)
    return target


def write_parquet(path: Path, rows: list[dict], *, system: str, ingestion: date,
                  filename: str = "part-000.parquet") -> Path:
    rows = _with_technical(rows, system, filename, ingestion)
    target = path / filename
    pl.DataFrame(rows, infer_schema_length=None).write_parquet(target, compression="zstd")
    return target


def write_xlsx(path: Path, rows: list[dict], *, system: str, ingestion: date,
               sheet: str = "Planilha1", filename: str = "part-000.xlsx") -> Path:
    from openpyxl import Workbook

    rows = _with_technical(rows, system, filename, ingestion)
    target = path / filename
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    if rows:
        cols = list(rows[0].keys())
        ws.append(cols)
        for r in rows:
            ws.append([r.get(c) for c in cols])
    wb.save(target)
    return target
