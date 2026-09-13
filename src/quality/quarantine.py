"""Quarentena: desvio lateral, nao filtro destrutivo (ADR-0003).

O registro reprovado por check BLOCKER nao entra no analitico e **nao e
apagado**. Ele fica em `data_quarantine` com a regra que o reprovou anexada, e
continua existindo intacto no RAW.

A diferenca importa: filtrar destroi a evidencia do problema, e sem evidencia
ninguem corrige a fonte. Desviar preserva.
"""
from __future__ import annotations

import polars as pl


def split(frames: dict[tuple[str, str], pl.DataFrame], quarantine: pl.DataFrame
          ) -> tuple[dict[tuple[str, str], pl.DataFrame], dict]:
    """Separa as linhas quarentenadas das que seguem para o analitico."""
    if quarantine.is_empty():
        return frames, {"quarantined_rows": 0, "by_dataset": {}}

    blocked: dict[tuple[str, str], set[str]] = {}
    for r in quarantine.select(["source_system", "dataset", "record_id"]).to_dicts():
        blocked.setdefault((r["source_system"], r["dataset"]), set()).add(r["record_id"])

    out, by_dataset = {}, {}
    for key, df in frames.items():
        ids = blocked.get(key)
        if not ids or "_row_id" not in df.columns:
            out[key] = df
            continue
        clean = df.filter(~pl.col("_row_id").is_in(list(ids)))
        out[key] = clean
        by_dataset[f"{key[0]}.{key[1]}"] = {
            "total": df.height, "quarentenados": df.height - clean.height,
            "taxa": round((df.height - clean.height) / df.height, 5) if df.height else 0.0,
        }
    return out, {"quarantined_rows": int(quarantine.height), "by_dataset": by_dataset}


def summary(results: pl.DataFrame, quarantine: pl.DataFrame) -> dict:
    if results.is_empty():
        return {}
    out = {
        "checks_no_catalogo": results.height,
        "checks_executados": results.filter(pl.col("status") != "NOT_RUN").height,
        "checks_nao_executados": results.filter(pl.col("status") == "NOT_RUN").height,
        "pass": results.filter(pl.col("status") == "PASS").height,
        "fail": results.filter(pl.col("status") == "FAIL").height,
        "por_dimensao": {},
        "por_severidade": {},
        "por_classe_de_achado": {},
        "falhas": [],
    }
    for dim in sorted(results["dimension"].unique().to_list()):
        sub = results.filter(pl.col("dimension") == dim)
        out["por_dimensao"][dim] = {"total": sub.height,
                                    "fail": sub.filter(pl.col("status") == "FAIL").height}
    for sev in sorted(results["severity"].unique().to_list()):
        sub = results.filter(pl.col("severity") == sev)
        out["por_severidade"][sev] = {"total": sub.height,
                                      "fail": sub.filter(pl.col("status") == "FAIL").height}
    if "finding_class" in results.columns:
        for cls in sorted(results["finding_class"].unique().to_list()):
            sub = results.filter(pl.col("finding_class") == cls)
            out["por_classe_de_achado"][cls] = {
                "total": sub.height, "fail": sub.filter(pl.col("status") == "FAIL").height}
    for r in results.filter(pl.col("status") == "FAIL").to_dicts():
        out["falhas"].append({"check_id": r["check_id"], "name": r["name"], "dataset": r["dataset"],
                              "severity": r["severity"],
                              "finding_class": r.get("finding_class"),
                              "failure_rate": r["failure_rate"],
                              "threshold": r["threshold"], "records_failed": r["records_failed"]})
    out["quarentena"] = int(quarantine.height)
    if not quarantine.is_empty() and "finding_class" in quarantine.columns:
        out["quarentena_por_classe"] = {
            r["finding_class"]: r["len"]
            for r in quarantine.group_by("finding_class").len().to_dicts()}
        out["quarentena_por_regra"] = {
            r["failed_rule"]: r["len"]
            for r in quarantine.group_by("failed_rule").len().sort("len", descending=True).to_dicts()}
    return out
