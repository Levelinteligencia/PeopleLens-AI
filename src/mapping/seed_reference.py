"""Gera as tabelas de DE/PARA APROVADAS iniciais.

ADR-0009: mapeamento aprovado e conhecimento curado e vive em CSV versionado no
Git, para que o historico de commits seja a trilha de auditoria. Este script
escreve a semente uma vez; dali em diante, a manutencao e por pull request.

Duas ausencias sao PROPOSITAIS e nao devem ser "corrigidas":

- `N4` e `N5` da VivaMarket nao tem mapeamento aprovado, porque sao
  genuinamente ambiguos (N4 cobre IC4 e M1, N5 cobre IC5 e M2). Eles precisam
  cair na fila de excecoes e esperar decisao humana (ADR-0004 e principio 5).
- varios apelidos de departamento ficam de fora, para que a fila de excecoes
  do primeiro processamento tenha conteudo de verdade.
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from generator.config import Config

# Vigencia ABERTA por padrao. Um apelido de departamento nao tem data de
# nascimento: `RH` sempre significou People. Fechar a vigencia em 2016-01-01
# faria o mapa ignorar quem foi admitido antes disso, e a NOVAORA tem gente
# admitida desde 2004 na populacao inicial. Vigencia fechada fica reservada
# para mudanca real de significado, como a escala de performance em 2021.
APPROVED = dict(mapping_status="APPROVED", confidence_score=1.0,
                valid_from="", valid_to="", approved_by="people-analytics",
                approved_at="2026-09-11")

GENDER = {
    "Male": "Male", "Female": "Female", "Non-binary": "Non-binary", "Not informed": "Not informed",
    "M": "Male", "F": "Female",
    "MASC": "Male", "FEM": "Female",
    # "OUTRO" (VivaMarket) fica de fora de proposito: vai para excecao
}

COUNTRY = {"BR": "BR", "AR": "AR", "CL": "CL", "CO": "CO", "MX": "MX",
           "Brasil": "BR", "Argentina": "AR", "Chile": "CL", "Colombia": "CO", "Mexico": "MX"}

JOB_LEVEL_EXTRA = {"N1": "IC1", "N2": "IC2", "N3": "IC3", "N6": "M3", "N7": "M5"}
# N4 e N5 ausentes de proposito: ambiguidade real, decisao humana

DEPARTMENT_EXTRA = {
    "RH": "People", "Recursos Humanos": "People",
    "Financeiro": "Finance", "Juridico": "Legal", "Jurídico": "Legal",
    "TI": "Engineering", "Tecnologia": "Engineering",
    "SAC": "Customer Service", "Atendimento": "Customer Service",
    "Logistica": "Logistics", "Logística": "Logistics",
    "CD": "Distribution Centers", "MKT": "Marketing",
    "Lojas": "Store Operations",
}

# Mapeamento TEMPORAL: a escala de performance mudou em 2021 (incidente
# INC_2021_PERF_SCALE). `3` significa "Meets Expectations" ate 2020 e nao
# significa nada depois. Este e o caso que obriga o DE/PARA a ter vigencia:
# aplicar o mapa sem olhar a data reescreveria a historia.
PERFORMANCE_LEGACY = {"1": "Below Expectations", "2": "Developing", "3": "Meets Expectations",
                      "4": "Exceeds Expectations", "5": "Outstanding"}
PERFORMANCE_CURRENT = {v: v for v in PERFORMANCE_LEGACY.values()}

HEADER = ["mapping_id", "source_system", "source_field", "source_value", "standard_value",
          "mapping_status", "confidence_score", "valid_from", "valid_to", "approved_by", "approved_at"]


def _write(path: Path, name: str, field: str, pairs: dict[str, str]) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    target = path / f"{name}.csv"
    with open(target, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=HEADER)
        w.writeheader()
        for i, (src, std) in enumerate(sorted(pairs.items()), start=1):
            w.writerow({"mapping_id": f"{name.upper()}-{i:04d}", "source_system": "*",
                        "source_field": field, "source_value": src, "standard_value": std, **APPROVED})
    return target


def _write_temporal(path: Path, name: str, field: str,
                    windows: list[tuple[str, str, dict[str, str]]]) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    target = path / f"{name}.csv"
    i = 0
    with open(target, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=HEADER)
        w.writeheader()
        for valid_from, valid_to, pairs in windows:
            for src, std in sorted(pairs.items()):
                i += 1
                row = {**APPROVED, "valid_from": valid_from, "valid_to": valid_to}
                w.writerow({"mapping_id": f"{name.upper()}-{i:04d}", "source_system": "*",
                            "source_field": field, "source_value": src, "standard_value": std, **row})
    return target


def seed(cfg: Config) -> dict[str, Path]:
    base = Path(cfg.root) / "data" / "reference"
    levels = {lv: lv for lv in cfg.org["job_levels"]}
    departments = {d: d for bu in cfg.org["business_units"].values() for d in bu["departments"]}
    return {
        "performance_rating": _write_temporal(
            base, "ref_performance_rating_mapping", "performance_rating",
            [("2016-01-01", "2020-12-31", PERFORMANCE_LEGACY),
             ("2021-01-01", "", PERFORMANCE_CURRENT)]),
        "gender": _write(base, "ref_gender_mapping", "gender", GENDER),
        "country": _write(base, "ref_country_mapping", "country", COUNTRY),
        "job_level": _write(base, "ref_job_level_mapping", "job_level", {**levels, **JOB_LEVEL_EXTRA}),
        "department": _write(base, "ref_department_mapping", "department", {**departments, **DEPARTMENT_EXTRA}),
    }


if __name__ == "__main__":
    from generator import config
    for k, p in seed(config.load()).items():
        print(k, "->", p)
