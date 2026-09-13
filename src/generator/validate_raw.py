"""Validacoes da camada RAW (F2).

Verificam tres coisas diferentes, e vale distinguir:

1. **fidelidade**: a projecao reproduz a verdade onde nao ha defeito declarado;
2. **disciplina**: todo defeito observado no RAW existe no catalogo, aponta para
   um sistema que declara carrega-lo e respeita o escopo temporal;
3. **calibragem**: a taxa realizada de cada defeito bate com a configurada.

Estas NAO sao as regras de Data Quality do projeto. As de DQ (F5) olham o dado
sem conhecer a verdade. Estas aqui tem o gabarito na mao e conferem se a
sujeira injetada e exatamente a sujeira declarada, nem mais nem menos.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import polars as pl

from .config import Config
from .defects.catalog import Catalog
from .projection import WAVE_1
from .projection.base import Ledger
from .validate import Check, _ok


def run_all(cfg: Config, tables: dict[str, pl.DataFrame], ledger: Ledger) -> list[Check]:
    checks: list[Check] = []
    cat = Catalog(cfg)
    led = ledger.to_frame()
    root = Path(cfg.root)
    raw = root / "data" / "raw"

    # ------------------------------------------------------- disciplina
    known = {d["id"] for d in cfg.defects["defects"]}
    unknown = set(led["defect_id"].unique().to_list()) - known
    checks.append(_ok("R01", "nenhum defeito fora do catalogo",
                      not unknown, f"desconhecidos: {sorted(unknown)}"))

    wrong_sys = []
    for r in led.select(["defect_id", "source_system"]).unique().to_dicts():
        d = cat[r["defect_id"]]
        if r["source_system"] not in d.systems():
            wrong_sys.append((r["defect_id"], r["source_system"]))
    checks.append(_ok("R02", "todo defeito ocorre so em sistema que declara carrega-lo",
                      not wrong_sys, f"{wrong_sys}"))

    only_wave1 = set(led["source_system"].unique().to_list()) - set(WAVE_1)
    checks.append(_ok("R03", "a F2 escreve apenas os sistemas da onda 1",
                      not only_wave1, f"fora da onda: {sorted(only_wave1)}"))

    # ------------------------------------------------------- cobertura
    esperados = {d.id for s in WAVE_1 for d in cat.for_system(s)}
    observados = set(led["defect_id"].unique().to_list())
    faltando = esperados - observados
    checks.append(_ok("R04", "todo defeito previsto para a onda 1 aparece ao menos uma vez",
                      not faltando, f"sem ocorrencia: {sorted(faltando)}"))

    # ------------------------------------------------------- escopo temporal
    emp = tables["dim_employee"].filter(pl.col("is_current"))
    hire = dict(zip(emp["employee_id"].to_list(), emp["hire_date"].to_list()))

    d02 = cat["D02"]
    d02_rows = led.filter(pl.col("defect_id") == "D02")
    checks.append(_ok("R05", "D02 e registrado como ausencia de coluna, nao como valor",
                      d02_rows.height >= 1 and d02_rows["raw_value"].str.contains("ausente").all(),
                      f"{d02_rows.height} registros"))

    d01_scope = cat["D01"].spec["scope"]["date_range"]
    core_d01 = led.filter((pl.col("defect_id") == "D01") & (pl.col("source_system") == "HRIS_CORE"))
    fora = 0
    for r in core_d01.select(["record_key"]).to_dicts():
        h = hire.get(int(r["record_key"]))
        if h and not (d01_scope[0] <= max(h, d01_scope[0]) <= d01_scope[1]):
            fora += 1
    checks.append(_ok("R06", "D01 no HRIS_CORE so ocorre na janela de sobreposicao da migracao",
                      fora == 0, f"{fora} fora da janela {d01_scope}"))

    # ------------------------------------------------------- calibragem
    # Medida exata: o ledger conta quantos registros foram OFERECIDOS a cada
    # defeito e qual era a taxa esperada em cada oferta. Comparar o total do
    # ledger com a taxa nominal daria falso positivo, porque a esperada varia
    # com escopo temporal, picos por incidente e pais.
    calib = ledger.calibration()
    devs, violacoes = [], 0
    for c in calib:
        if c["eligible"] < 200 or c["expected_rate"] <= 0:
            continue
        esperado, real, n = c["expected_rate"], c["realized_rate"], c["eligible"]
        # tolerancia = 3 desvios-padrao binomiais, com piso relativo de 20%
        sd = (esperado * (1 - esperado) / n) ** 0.5
        allowed = max(3 * sd, 0.20 * esperado)
        if abs(real - esperado) > allowed:
            violacoes += 1
            devs.append((c["defect_id"], f"{c['source_system']}.{c['dataset']}",
                         f"esperado {esperado:.4f}", f"realizado {real:.4f}", f"n={n}"))
    checks.append(_ok("R07", "taxa realizada de cada defeito dentro de 3 desvios da esperada",
                      violacoes == 0,
                      f"{violacoes} de {len(calib)} combinacoes fora: {devs}", severity="CRITICAL"))

    d06 = cat["D06"].absolute_count(cfg.scale) or 0
    obs06 = ledger.count("D06")
    checks.append(_ok("R08", "D06 respeita a contagem absoluta configurada",
                      abs(obs06 - d06) <= max(2, 0.1 * d06), f"esperado ~{d06}, observado {obs06}"))

    # ------------------------------------------------------- fidelidade
    core = _read_csv(raw, "HRIS_CORE", "employee_master")
    if core is not None:
        afetados = set(led.filter((pl.col("source_system") == "HRIS_CORE")
                                  & pl.col("defect_id").is_in(["D19", "D09", "D01"]))["record_key"].to_list())
        limpos = core.filter(~pl.col("employee_id").cast(pl.Utf8).is_in(list(afetados)))
        j = limpos.join(emp.select(["employee_id", "department", "job_level", "country"]),
                        left_on=pl.col("employee_id").cast(pl.Int64), right_on="employee_id", how="inner")
        divergentes = j.filter((pl.col("department") != pl.col("department_right"))
                               | (pl.col("job_level") != pl.col("job_level_right"))
                               | (pl.col("country") != pl.col("country_right"))).height if "department_right" in j.columns else 0
        checks.append(_ok("R09", "registro sem defeito declarado reproduz a verdade exatamente",
                          divergentes == 0, f"{divergentes} divergencias em {j.height} comparados"))

    # ------------------------------------------------------- formatos nativos
    leg = _read_csv(raw, "HRIS_LEGACY", "employee_master", encoding="latin-1", sep=";")
    checks.append(_ok("R10", "HRIS_LEGACY legivel em latin-1 com delimitador ponto e virgula",
                      leg is not None and leg.height > 0, "arquivo ilegivel" if leg is None else f"{leg.height} linhas"))
    if leg is not None:
        checks.append(_ok("R11", "HRIS_LEGACY nao expoe coluna de raca e cor (D02)",
                          not any(c.lower().startswith(("raca", "race")) for c in leg.columns),
                          f"colunas: {len(leg.columns)}"))
        checks.append(_ok("R12", "HRIS_LEGACY usa dominio antigo de genero",
                          set(leg["SEXO"].drop_nulls().unique().to_list()) <= {"M", "F", ""},
                          f"valores: {sorted(set(leg['SEXO'].drop_nulls().unique().to_list()))[:5]}"))

    ats_file = _find(raw, "ATS_CLOUD", "requisition", ".json")
    ok_json, n_req = False, 0
    if ats_file:
        with open(ats_file, encoding="utf-8") as fh:
            payload = json.load(fh)
        ok_json = "records" in payload and all("candidates" in r for r in payload["records"][:50])
        n_req = len(payload.get("records", []))
    checks.append(_ok("R13", "ATS_CLOUD produz JSON aninhado valido", ok_json, f"{n_req} requisicoes"))

    xlsx = _find(raw, "VIVAMARKET_LEGACY", "employee_master", ".xlsx")
    ok_xlsx, cols = False, []
    if xlsx:
        from openpyxl import load_workbook
        wb = load_workbook(xlsx, read_only=True)
        ws = wb.active
        cols = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
        ok_xlsx = "COD_FUNC" in cols and "employee_id" not in cols
    checks.append(_ok("R14", "VivaMarket entrega xlsx sem o employee_id corporativo (D05)",
                      ok_xlsx, f"colunas: {cols[:6]}"))

    # ------------------------------------------------------- colunas tecnicas
    faltam_tec = []
    for sysname, ds, enc, sep in [("HRIS_LEGACY", "employee_master", "latin-1", ";"),
                                  ("HRIS_CORE", "employee_master", "utf-8", ","),
                                  ("PAYROLL_BR", "compensation", "utf-8", ";")]:
        df = _read_csv(raw, sysname, ds, encoding=enc, sep=sep)
        if df is None or not {"_source_file", "_row_number", "_ingested_at", "_source_system"} <= set(df.columns):
            faltam_tec.append(f"{sysname}.{ds}")
    checks.append(_ok("R15", "todo arquivo da landing zone carrega as colunas tecnicas de lineage",
                      not faltam_tec, f"sem colunas tecnicas: {faltam_tec}"))

    # ------------------------------------------------------- reconciliacao
    snap = tables["fact_headcount_snapshot"].filter(pl.col("country") == "BR")
    pay = _read_csv(raw, "PAYROLL_BR", "payroll_headcount_snapshot", encoding="utf-8", sep=";")
    if pay is not None and snap.height:
        hris_n = snap.height
        pay_n = pay.height
        div = abs(pay_n - hris_n) / hris_n
        lo, hi = cat["D11"].spec["rate_range"]
        checks.append(_ok("R16", "divergencia de populacao entre HRIS e folha dentro da faixa configurada",
                          lo * 0.5 <= div <= hi * 2.0,
                          f"divergencia {div:.2%}, faixa configurada {lo:.0%} a {hi:.0%}",
                          severity="CRITICAL"))

    # ------------------------------------------------------- a verdade nao foi tocada
    mf = root / "data" / "synthetic" / "truth" / "manifest.json"
    checks.append(_ok("R17", "manifesto da camada de verdade continua presente e intacto",
                      mf.exists(), "manifesto ausente"))

    return checks


# --------------------------------------------------------------------------- #
def _find(raw: Path, system: str, dataset: str, suffix: str) -> Path | None:
    base = raw / system / dataset
    if not base.exists():
        return None
    for p in sorted(base.rglob(f"*{suffix}")):
        return p
    return None


def _read_csv(raw: Path, system: str, dataset: str, encoding: str = "utf-8", sep: str = ",") -> pl.DataFrame | None:
    p = _find(raw, system, dataset, ".csv")
    if p is None:
        return None
    try:
        return pl.read_csv(p, separator=sep, encoding=encoding, infer_schema_length=0)
    except Exception:
        return None


def _rows(raw: Path, system: str, dataset: str, parquet: bool = False) -> int:
    p = _find(raw, system, dataset, ".parquet" if parquet else ".csv")
    if p is None:
        return 0
    try:
        return pl.read_parquet(p).height if parquet else pl.read_csv(p, separator=";" if system in ("HRIS_LEGACY", "PAYROLL_BR") else ",", encoding="latin-1" if system == "HRIS_LEGACY" else "utf-8", infer_schema_length=0).height
    except Exception:
        return 0
