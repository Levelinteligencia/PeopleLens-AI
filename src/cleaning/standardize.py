"""Camada L1: padronizacao de FORMA.

O que esta camada faz: encoding, espaco, vazio, data e numero.
O que ela NAO faz: traduzir significado. `RH` sai daqui como `RH`.

Duas regras inegociaveis (exigencia da Sam na F3):

1. **nenhuma correcao silenciosa**: todo valor alterado vai para o
   `transformation_log` com valor original, sistema de origem e regra aplicada;
2. **falha nao vira nulo**: uma data impossivel e preservada como estava e a
   linha recebe marca de falha. Transformar erro em ausencia e a forma mais
   comum de fazer um problema desaparecer sem resolver.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from pathlib import Path

import polars as pl
import yaml

from generator.config import Config

MOJIBAKE_MARK = re.compile(r"[ÃÂ][\x80-\xBF]")
WS = re.compile(r"\s{2,}")


def load_rules(cfg: Config) -> dict:
    with open(Path(cfg.root) / "config" / "standardization.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# --------------------------------------------------------------------------- #
def repair_encoding(value: str) -> str:
    """Desfaz latin-1 lido como utf-8, quando o texto traz a marca do dano."""
    if not value or not MOJIBAKE_MARK.search(value):
        return value
    try:
        fixed = value.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return value
    # so aceita o reparo se ele de fato produzir texto valido
    return fixed if fixed.isprintable() else value


def parse_date(value: str, formats: list[str], rules: dict) -> tuple[str | None, str, bool]:
    """Devolve (data ISO ou None, motivo, ambiguidade_latente).

    Motivos: ok, vazio, formato_desconhecido, fora_da_janela.

    Sobre ambiguidade: `03/04/2019` e valido em `%d/%m/%Y` e em `%m/%d/%Y`, e
    as duas leituras dao datas diferentes. O sistema DECLARA seu formato em
    `sources.yaml`, entao a declaracao vence e o valor e convertido. Mas a
    ambiguidade nao desaparece: ela e registrada como `ambiguidade_latente`,
    vira um check de qualidade de severidade WARNING, e passa a ser visivel.

    Tratar isso como falha de parse seria reprovar quase toda data brasileira;
    tratar como se nao existisse seria esconder que a conversao depende de uma
    declaracao que pode estar errada. O meio-termo honesto e converter e avisar.
    """
    if value is None or value == "":
        return None, "vazio", False
    parsed: list[tuple[str, date]] = []
    for fmt in formats:
        try:
            parsed.append((fmt, datetime.strptime(value, fmt).date()))
        except ValueError:
            continue
    if not parsed:
        return None, "formato_desconhecido", False

    ambiguo = len({d for _, d in parsed}) > 1 and bool(rules["date_parse"].get("flag_ambiguous_day_month"))
    d = parsed[0][1]          # o primeiro formato e sempre o declarado pelo sistema
    minimo = rules["date_parse"]["min_year"]
    maximo = date.today().year + rules["date_parse"]["max_year_offset"]
    if d.year < minimo or d.year > maximo:
        return None, "fora_da_janela", ambiguo
    return d.isoformat(), "ok", ambiguo


def parse_decimal_br(value: str) -> tuple[float | None, str]:
    if value is None or value == "":
        return None, "vazio"
    v = value.strip()
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+(,\d+)?", v) or re.fullmatch(r"-?\d+,\d+", v):
        v = v.replace(".", "").replace(",", ".")
    try:
        return float(v), "ok"
    except ValueError:
        return None, "nao_numerico"


# --------------------------------------------------------------------------- #
def standardize_dataset(cfg: Config, rules: dict, system: str, dataset: str,
                        df: pl.DataFrame, lineage) -> pl.DataFrame:
    spec = rules["datasets"].get(f"{system}.{dataset}", {})
    sys_fmt = cfg.sources["systems"][system].get("date_format")
    formats = ([sys_fmt] if sys_fmt else []) + [f for f in rules["date_parse"]["fallback_formats"] if f != sys_fmt]

    date_cols = set(spec.get("date_columns", []))
    dec_cols = set(spec.get("decimal_columns", []))
    out = df.to_dicts()
    flags: list[dict] = []

    for row in out:
        rid = row["_row_id"]
        for col, raw in list(row.items()):
            if col.startswith("_") or raw is None:
                continue
            original = raw
            v = raw

            if isinstance(v, str):
                if v == "":
                    row[col] = None
                    lineage.value("L1", system, dataset, rid, col, original, None, "STD_EMPTY_TO_NULL")
                    continue
                s = v.strip()
                if s != v:
                    lineage.value("L1", system, dataset, rid, col, v, s, "STD_TRIM")
                    v = s
                s = WS.sub(" ", v)
                if s != v:
                    lineage.value("L1", system, dataset, rid, col, v, s, "STD_COLLAPSE_WS")
                    v = s
                s = repair_encoding(v)
                if s != v:
                    lineage.value("L1", system, dataset, rid, col, v, s, "STD_ENCODING_REPAIR")
                    v = s
                row[col] = v

            if col in date_cols:
                iso, motivo, ambiguo = parse_date(row[col], formats, rules)
                row[f"{col}__iso"] = iso
                row[f"{col}__parse"] = motivo
                row[f"{col}__ambiguous"] = ambiguo
                if iso is not None and iso != original:
                    lineage.value("L1", system, dataset, rid, col, original, iso, "STD_DATE_PARSE")
                if motivo not in ("ok", "vazio"):
                    flags.append(dict(row_id=rid, column=col, value=original, reason=motivo))
            elif col in dec_cols:
                num, motivo = parse_decimal_br(row[col])
                row[f"{col}__num"] = num
                row[f"{col}__parse"] = motivo
                if num is not None and str(num) != str(original):
                    lineage.value("L1", system, dataset, rid, col, original, num, "STD_DECIMAL_BR")
                if motivo not in ("ok", "vazio"):
                    flags.append(dict(row_id=rid, column=col, value=original, reason=motivo))

    std = pl.DataFrame(out, infer_schema_length=None)
    lineage.object("dataset", f"standardized.{system}.{dataset}", "dataset",
                   f"staged.{system}.{dataset}",
                   "padronizacao de forma: encoding, espaco, vazio, data e numero", rows=std.height)
    std = std.with_columns(pl.lit(system).alias("_system"), pl.lit(dataset).alias("_dataset"))
    return std


def standardize_all(cfg: Config, staged: dict[tuple[str, str], pl.DataFrame], lineage
                    ) -> tuple[dict[tuple[str, str], pl.DataFrame], pl.DataFrame]:
    rules = load_rules(cfg)
    out, all_flags = {}, []
    for (system, dataset), df in staged.items():
        std = standardize_dataset(cfg, rules, system, dataset, df, lineage)
        out[(system, dataset)] = std
        for c in std.columns:
            if c.endswith("__parse"):
                base = c[:-7]
                bad = std.filter(~pl.col(c).is_in(["ok", "vazio"]))
                for r in bad.select(["_row_id", c, base]).to_dicts():
                    all_flags.append(dict(source_system=system, dataset=dataset, row_id=r["_row_id"],
                                          column=base, value=r[base], reason=r[c]))
    flags = pl.DataFrame(all_flags, infer_schema_length=None) if all_flags else pl.DataFrame(
        schema={"source_system": pl.Utf8, "dataset": pl.Utf8, "row_id": pl.Utf8,
                "column": pl.Utf8, "value": pl.Utf8, "reason": pl.Utf8})
    return out, flags


def write(cfg: Config, std: dict[tuple[str, str], pl.DataFrame]) -> Path:
    base = Path(cfg.root) / "data" / "processed" / "standardized"
    for (system, dataset), df in std.items():
        d = base / system
        d.mkdir(parents=True, exist_ok=True)
        df.write_parquet(d / f"{dataset}.parquet", compression="zstd")
    return base
