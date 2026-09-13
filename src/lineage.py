"""Lineage de transformacao.

Duas granularidades, porque servem a perguntas diferentes:

- **objeto**: qual camada veio de qual, com que transformacao e em que execucao.
  Responde "de onde vem esta tabela".
- **valor**: qual valor original virou qual valor novo, em que sistema, por qual
  regra. Responde "de onde veio ESTE numero", que e a exigencia da secao 22 da
  Especificacao e a razao de existir da camada.

A regra do projeto (F3, item da Sam): nenhuma correcao silenciosa. Todo valor
transformado passa por aqui, com valor original, sistema de origem e regra
aplicada. Se nao esta no log, nao pode ter mudado.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import polars as pl


@dataclass
class Lineage:
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    objects: list[dict] = field(default_factory=list)
    values: list[dict] = field(default_factory=list)

    # ------------------------------------------------------------- objetos
    def object(self, object_type: str, object_name: str,
               parent_type: str, parent_name: str, transformation: str, rows: int | None = None) -> None:
        self.objects.append(dict(
            lineage_id=f"{self.run_id}-{len(self.objects) + 1:05d}",
            object_type=object_type, object_name=object_name,
            parent_object_type=parent_type, parent_object_name=parent_name,
            transformation=transformation, rows=rows,
            run_id=self.run_id, created_at=datetime.utcnow().isoformat(timespec="seconds"),
        ))

    # -------------------------------------------------------------- valores
    def value(self, layer: str, source_system: str, dataset: str, row_id: str,
              field_name: str, original_value, new_value, rule_id: str) -> None:
        self.values.append(dict(
            layer=layer, source_system=source_system, dataset=dataset, row_id=row_id,
            field=field_name,
            original_value=None if original_value is None else str(original_value),
            new_value=None if new_value is None else str(new_value),
            rule_id=rule_id, run_id=self.run_id,
        ))

    # ---------------------------------------------------------------- saida
    def frames(self) -> dict[str, pl.DataFrame]:
        return {
            "data_lineage": pl.DataFrame(self.objects, infer_schema_length=None) if self.objects else pl.DataFrame(),
            "transformation_log": pl.DataFrame(self.values, infer_schema_length=None) if self.values else pl.DataFrame(),
        }

    def write(self, root: Path) -> None:
        base = root / "data" / "processed" / "metadata"
        base.mkdir(parents=True, exist_ok=True)
        for name, df in self.frames().items():
            if not df.is_empty():
                df.write_parquet(base / f"{name}.parquet", compression="zstd")

    def summary(self) -> dict:
        by_rule: dict[str, int] = {}
        for v in self.values:
            by_rule[v["rule_id"]] = by_rule.get(v["rule_id"], 0) + 1
        return {"run_id": self.run_id, "objects": len(self.objects),
                "value_transformations": len(self.values), "by_rule": by_rule}
