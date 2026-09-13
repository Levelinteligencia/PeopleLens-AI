"""Perfilamento da camada staged.

ADR-0003: profiling OBSERVA, nao transforma. Este modulo nao e dono de nenhuma
camada de dados; ele le a staged e escreve apenas metadados.

O que se procura aqui nao e "quantos nulos existem", e sim ONDE eles se
concentram. Um nulo distribuido por igual nao ensina nada; um nulo que comeca
numa data especifica conta a historia de um sistema que entrou ou saiu.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import polars as pl

DATE_PATTERNS = {
    "ISO": r"^\d{4}-\d{2}-\d{2}$",
    "DMY4": r"^\d{2}/\d{2}/\d{4}$",
    "DMY2": r"^\d{2}/\d{2}/\d{2}$",
    "MDY4": r"^\d{2}/\d{2}/\d{4}$",
    "COMPACT": r"^\d{8}$",
    "ISO_TS": r"^\d{4}-\d{2}-\d{2}T",
}
NUMERIC_BR = r"^-?\d{1,3}(\.\d{3})*(,\d+)?$|^-?\d+,\d+$"
NUMERIC_EN = r"^-?\d+(\.\d+)?$"
MOJIBAKE = r"[ÃÂ][\x80-\xBF]"


def _pattern_share(s: pl.Series, pattern: str) -> float:
    nn = s.drop_nulls()
    if nn.len() == 0:
        return 0.0
    return float(nn.str.contains(pattern).sum()) / nn.len()


def profile_column(system: str, dataset: str, col: str, s: pl.Series, rows: int) -> dict:
    nn = s.drop_nulls().filter(s.drop_nulls() != "")
    top = (
        pl.DataFrame({col: nn}).group_by(col).len().sort("len", descending=True).head(5)
        if nn.len() else pl.DataFrame()
    )
    top_values = [{"value": r[0], "n": r[1]} for r in top.iter_rows()] if top.height else []
    lengths = nn.str.len_chars() if nn.len() else None

    fmts = {name: _pattern_share(nn, pat) for name, pat in DATE_PATTERNS.items()} if nn.len() else {}
    best_fmt = max(fmts, key=fmts.get) if fmts and max(fmts.values()) > 0.5 else None

    return dict(
        source_system=system, dataset=dataset, column=col,
        rows=rows, non_null=int(nn.len()),
        null_rate=round(1 - nn.len() / rows, 5) if rows else None,
        distinct=int(nn.n_unique()) if nn.len() else 0,
        distinct_rate=round(nn.n_unique() / nn.len(), 5) if nn.len() else None,
        min_len=int(lengths.min()) if lengths is not None and lengths.len() else None,
        max_len=int(lengths.max()) if lengths is not None and lengths.len() else None,
        top_values=str(top_values),
        date_format_candidate=best_fmt,
        date_like_share=round(max(fmts.values()), 4) if fmts else 0.0,
        numeric_br_share=round(_pattern_share(nn, NUMERIC_BR), 4) if nn.len() else 0.0,
        numeric_en_share=round(_pattern_share(nn, NUMERIC_EN), 4) if nn.len() else 0.0,
        mojibake_share=round(_pattern_share(nn, MOJIBAKE), 4) if nn.len() else 0.0,
        leading_trailing_space_share=round(_pattern_share(nn, r"^\s|\s$"), 4) if nn.len() else 0.0,
        case_mixed=bool(nn.len() and _pattern_share(nn, r"^[A-ZÀ-Ý ]+$") > 0.02
                        and _pattern_share(nn, r"^[a-zà-ÿ ]+$") > 0.02),
        profiled_at=datetime.utcnow().isoformat(timespec="seconds"),
    )


def profile_all(staged: dict[tuple[str, str], pl.DataFrame], lineage) -> pl.DataFrame:
    rows: list[dict] = []
    for (system, dataset), df in staged.items():
        for col in df.columns:
            if col.startswith("_"):
                continue
            rows.append(profile_column(system, dataset, col, df[col], df.height))
        lineage.object("metadata", f"profiling.{system}.{dataset}", "dataset",
                       f"staged.{system}.{dataset}", "perfilamento por coluna, sem transformacao",
                       rows=df.width)
    return pl.DataFrame(rows, infer_schema_length=None)


def findings(prof: pl.DataFrame) -> list[dict]:
    """Achados que o perfilamento levanta sozinho, antes de qualquer regra.

    Sao pistas, nao vereditos: cada uma vira ou um check de qualidade, ou uma
    entrada de DE/PARA, ou nada. O valor esta em terem sido encontradas sem
    ninguem dizer onde procurar.
    """
    out = []
    for r in prof.to_dicts():
        who = f"{r['source_system']}.{r['dataset']}.{r['column']}"
        if r["null_rate"] and r["null_rate"] > 0.20:
            out.append({"tipo": "alta_taxa_de_nulos", "onde": who, "detalhe": f"{r['null_rate']:.1%}"})
        if r["mojibake_share"] > 0.01:
            out.append({"tipo": "encoding_suspeito", "onde": who, "detalhe": f"{r['mojibake_share']:.1%} com marca de latin-1"})
        if r["date_like_share"] > 0.5 and r["date_format_candidate"] not in (None, "ISO"):
            out.append({"tipo": "data_fora_do_iso", "onde": who, "detalhe": f"formato aparente {r['date_format_candidate']}"})
        if r["numeric_br_share"] > 0.5 and r["numeric_en_share"] < 0.5:
            out.append({"tipo": "decimal_com_virgula", "onde": who, "detalhe": f"{r['numeric_br_share']:.1%}"})
        if r["leading_trailing_space_share"] > 0.01:
            out.append({"tipo": "espaco_nas_pontas", "onde": who, "detalhe": f"{r['leading_trailing_space_share']:.1%}"})
        if r["case_mixed"]:
            out.append({"tipo": "caixa_inconsistente", "onde": who, "detalhe": "convivem maiuscula e minuscula puras"})
        if r["distinct"] and 1 < r["distinct"] <= 30 and r["column"].lower() in (
                "sexo", "gender", "situacao", "employment_status", "nivel", "job_level", "pais", "country",
                "departamento", "department", "depto", "moeda", "currency", "status"):
            out.append({"tipo": "dominio_candidato_a_depara", "onde": who,
                        "detalhe": f"{r['distinct']} valores distintos"})
    return out


def write(root: Path, prof: pl.DataFrame) -> Path:
    base = Path(root) / "data" / "processed" / "metadata"
    base.mkdir(parents=True, exist_ok=True)
    prof.write_parquet(base / "profiling_results.parquet", compression="zstd")
    return base / "profiling_results.parquet"
