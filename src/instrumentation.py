"""Instrumentacao de tempo de execucao.

Decisao da Sam na aprovacao da F3, item 4: manter o lineage em granularidade de
valor, cujo custo hoje e aceitavel, e **instrumentar** para que uma eventual
otimizacao futura seja decidida por evidencia e nao por intuicao.

O que se mede: tempo por etapa, tempo por dataset dentro da etapa, linhas
processadas e valores transformados. O que se deriva: microssegundos por linha e
por valor, que e a unidade que permite projetar o custo no volume completo sem
precisar roda-lo.
"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import polars as pl


@dataclass
class Timer:
    run_id: str
    profile: str
    scale: float
    marks: list[dict] = field(default_factory=list)

    @contextmanager
    def stage(self, stage: str, dataset: str | None = None, rows: int = 0):
        t0 = time.perf_counter()
        state = {"values": 0}
        try:
            yield state
        finally:
            dt = time.perf_counter() - t0
            self.marks.append(dict(
                run_id=self.run_id, profile=self.profile, scale=self.scale,
                stage=stage, dataset=dataset, seconds=round(dt, 4),
                rows=rows, values=state.get("values", 0),
                us_per_row=round(dt * 1e6 / rows, 2) if rows else None,
                us_per_value=round(dt * 1e6 / state["values"], 2) if state.get("values") else None,
                measured_at=datetime.utcnow().isoformat(timespec="seconds"),
            ))

    def frame(self) -> pl.DataFrame:
        return pl.DataFrame(self.marks, infer_schema_length=None) if self.marks else pl.DataFrame()

    def by_stage(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for m in self.marks:
            g = out.setdefault(m["stage"], {"seconds": 0.0, "rows": 0, "values": 0, "datasets": 0})
            g["seconds"] += m["seconds"]
            g["rows"] += m["rows"]
            g["values"] += m["values"]
            g["datasets"] += 1 if m["dataset"] else 0
        for g in out.values():
            g["seconds"] = round(g["seconds"], 3)
            g["us_per_row"] = round(g["seconds"] * 1e6 / g["rows"], 2) if g["rows"] else None
        return out

    def projection(self, target_scale: float = 1.0) -> dict:
        """Projeta o custo no volume completo, a partir do medido.

        Projecao linear e uma aproximacao: vale para as etapas que percorrem
        linha a linha, e subestima as que tem custo por dataset. Serve para
        decidir se ha problema, nao para prometer um numero.
        """
        fator = target_scale / self.scale if self.scale else 1.0
        total = sum(m["seconds"] for m in self.marks)
        return {
            "escala_medida": self.scale, "escala_projetada": target_scale, "fator": round(fator, 1),
            "segundos_medidos": round(total, 1),
            "segundos_projetados": round(total * fator, 1),
            "minutos_projetados": round(total * fator / 60, 1),
            "ressalva": "projecao linear; vale para etapas linha a linha e subestima custo fixo por dataset",
        }

    def write(self, root: Path) -> Path | None:
        df = self.frame()
        if df.is_empty():
            return None
        base = Path(root) / "data" / "processed" / "metadata"
        base.mkdir(parents=True, exist_ok=True)
        target = base / "execution_timing.parquet"
        # acumula historico entre execucoes, para que a decisao futura tenha serie
        if target.exists():
            df = pl.concat([pl.read_parquet(target), df], how="vertical_relaxed")
        df.write_parquet(target, compression="zstd")
        return target
